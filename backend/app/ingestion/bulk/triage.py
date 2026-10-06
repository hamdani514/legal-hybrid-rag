"""
Triage: decide what every PDF in the input folder needs, without an LLM call.

Runs workers.triage_one over the folder in a process pool (hashing 3,000 files
plus a PyMuPDF open each is I/O + CPU, seconds in parallel), then classifies
each file against the database and the local state:

    corrupt              unreadable, empty, encrypted, or not a PDF
    duplicate_in_folder  same file_hash as an earlier file in this folder
    duplicate            file_hash already in `documents`, status searchable or
                         complete, AND index_status says every store needed
                         for search (tree, dense, fts) is written
    incomplete           in `documents` but not searchable: a run died mid-file,
                         or an older run stopped after the tree (status
                         "complete" with no vectors / keyword rows). Resumed
                         automatically; a file whose tree exists resumes at
                         the missing stores without re-parsing
    failed               in `documents` with status failed; resumed only with
                         --retry-failed, otherwise reported and skipped
    rejected             not a Supreme Court judgment (validator); no DB record,
                         same as upload_pdf's 400
    digital / scanned    new files, routed to the two queues

file_hash is sha256 over the whole file, exactly what upload_pdf computes, so a
file uploaded through the admin UI is recognised here and vice versa.
"""
from __future__ import annotations

import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from loguru import logger

from app.ingestion.bulk.workers import pool_kwargs, triage_one
from app.retrieval.contracts import INDEX_REQUIRED_FOR_SEARCH

TO_PROCESS = ("digital", "scanned", "incomplete", "failed")


def list_pdfs(input_dir: Path, recursive: bool = False) -> list[Path]:
    it = input_dir.rglob("*") if recursive else input_dir.glob("*")
    return sorted(p for p in it if p.is_file() and p.suffix.lower() == ".pdf")


def run_triage_pool(paths: list[Path], workers: int) -> list[dict]:
    results: list[dict] = []
    if not paths:
        return results
    with ProcessPoolExecutor(max_workers=max(1, min(workers, len(paths))),
                             **pool_kwargs("ERROR")) as pool:
        # chunksize amortises pickling across thousands of small tasks
        chunk = max(1, len(paths) // (workers * 8) or 1)
        for i, r in enumerate(pool.map(triage_one, [str(p) for p in paths], chunksize=chunk), 1):
            results.append(r)
            if i % 250 == 0:
                logger.info(f"Triage: {i}/{len(paths)} files")
    return results


async def lookup_db(database, hashes: list[str]) -> dict[str, dict]:
    """file_hash -> {pdf_id, status, filename, detected_type} from `documents`."""
    found: dict[str, dict] = {}
    uniq = sorted({h for h in hashes if h})
    for i in range(0, len(uniq), 500):
        cur = database.documents.find(
            {"file_hash": {"$in": uniq[i:i + 500]}},
            {"_id": 0, "pdf_id": 1, "status": 1, "filename": 1, "index_status": 1,
             "detected_type": 1, "file_hash": 1, "quality_passed": 1},
        )
        async for d in cur:
            found.setdefault(d["file_hash"], d)
    return found


def classify(results: list[dict], in_db: dict[str, dict], state, retry_failed: bool) -> list[dict]:
    seen: dict[str, str] = {}
    entries: list[dict] = []
    for r in results:
        e = {**r, "category": "", "pdf_id": None, "db_status": None, "dup_of": None}
        h = r.get("file_hash")
        if r.get("error"):
            e["category"], e["reason"] = "corrupt", r["error"]
        elif h in seen:
            e["category"], e["dup_of"] = "duplicate_in_folder", seen[h]
            e["reason"] = f"same content as {Path(seen[h]).name}"
        elif h in in_db:
            d = in_db[h]
            e["pdf_id"], e["db_status"] = d.get("pdf_id"), d.get("status")
            e["detected_type"] = d.get("detected_type") or r.get("detected_type")
            ix = d.get("index_status") or {}
            missing = [s for s in INDEX_REQUIRED_FOR_SEARCH if not ix.get(s)]
            if d.get("status") in ("searchable", "complete") and not missing:
                e["category"] = "duplicate"
                e["reason"] = f"already ingested as '{d.get('filename', '?')}' ({d.get('pdf_id')})"
            elif d.get("status") == "failed":
                e["category"] = "failed"
                e["reason"] = "failed in an earlier run" + ("" if retry_failed else " (use --retry-failed)")
            elif d.get("status") in ("searchable", "complete"):
                e["category"] = "incomplete"
                e["reason"] = f"status '{d.get('status')}' but not recorded in: {', '.join(missing)}"
            else:
                e["category"] = "incomplete"
                e["reason"] = f"interrupted at status '{d.get('status')}'"
        elif r.get("detected_type") == "text" and r.get("valid") is False:
            e["category"] = "rejected"
        elif state.get(h).get("status") == "rejected" and not retry_failed:
            e["category"], e["reason"] = "rejected", state.get(h).get("error", "rejected earlier")
        else:
            e["category"] = "digital" if r.get("detected_type") == "text" else "scanned"
            e["pdf_id"] = state.get(h).get("pdf_id")  # reuse an id from a killed run
        if h and h not in seen and e["category"] != "corrupt":
            seen[h] = r["path"]
        entries.append(e)
    return entries


def summarize(entries: list[dict], seconds: float) -> dict:
    cats: dict[str, int] = {}
    for e in entries:
        cats[e["category"]] = cats.get(e["category"], 0) + 1
    pages = {"digital": 0, "scanned": 0}
    for e in entries:
        if e["category"] in ("digital", "scanned") and e.get("pages"):
            pages[e["category"]] += e["pages"]
    return {
        "files": len(entries),
        "by_category": dict(sorted(cats.items())),
        "detected": {
            "text": sum(1 for e in entries if e.get("detected_type") == "text"),
            "scanned": sum(1 for e in entries if e.get("detected_type") == "scanned"),
        },
        "total_pages": sum(e.get("pages") or 0 for e in entries),
        "pages_to_process": pages,
        "seconds": round(seconds, 2),
    }


async def triage(input_dir: Path, database, state, workers: int,
                 retry_failed: bool = False, recursive: bool = False) -> tuple[list[dict], dict]:
    t0 = time.perf_counter()
    paths = list_pdfs(input_dir, recursive)
    logger.info(f"Triage: {len(paths)} PDFs in {input_dir} ({workers} workers)")
    results = run_triage_pool(paths, workers)
    in_db = await lookup_db(database, [r.get("file_hash") for r in results])
    entries = classify(results, in_db, state, retry_failed)
    return entries, summarize(entries, time.perf_counter() - t0)


if __name__ == "__main__":
    # Pure classification self-check (no DB, no pool).
    class _S:
        def __init__(self, d): self.d = d
        def get(self, h): return self.d.get(h, {})

    rs = [
        {"path": "a.pdf", "file_hash": "A", "detected_type": "text", "valid": True, "error": ""},
        {"path": "b.pdf", "file_hash": "A", "detected_type": "text", "valid": True, "error": ""},
        {"path": "c.pdf", "file_hash": None, "error": "not a PDF (missing %PDF header)"},
        {"path": "d.pdf", "file_hash": "D", "detected_type": "scanned", "valid": None, "error": ""},
        {"path": "e.pdf", "file_hash": "E", "detected_type": "text", "valid": True, "error": ""},
        {"path": "f.pdf", "file_hash": "F", "detected_type": "text", "valid": False,
         "reason": "not a judgment", "error": ""},
        {"path": "g.pdf", "file_hash": "G", "detected_type": "scanned", "error": ""},
        {"path": "h.pdf", "file_hash": "H", "detected_type": "scanned", "error": ""},
        {"path": "i.pdf", "file_hash": "I", "detected_type": "text", "valid": True, "error": ""},
        {"path": "j.pdf", "file_hash": "J", "detected_type": "text", "valid": True, "error": ""},
        {"path": "k.pdf", "file_hash": "K", "detected_type": "text", "valid": True, "error": ""},
    ]
    full = {"tree": True, "dense": True, "fts": True}
    db_hits = {"E": {"pdf_id": "pe", "status": "searchable", "filename": "e.pdf", "index_status": full},
               "J": {"pdf_id": "pj", "status": "complete", "filename": "j.pdf",
                     "index_status": {"tree": True}},   # old bulk run: tree only
               "K": {"pdf_id": "pk", "status": "complete", "filename": "k.pdf"},  # no index_status
               "G": {"pdf_id": "pg", "status": "parsing"},
               "I": {"pdf_id": "pi", "status": "failed"}}
    st = _S({"H": {"status": "rejected", "error": "nope"}, "D": {"pdf_id": "pd", "status": "assigned"}})
    got = {e["path"]: e["category"] for e in classify(rs, db_hits, st, retry_failed=False)}
    assert got == {"a.pdf": "digital", "b.pdf": "duplicate_in_folder", "c.pdf": "corrupt",
                   "d.pdf": "scanned", "e.pdf": "duplicate", "f.pdf": "rejected",
                   "g.pdf": "incomplete", "h.pdf": "rejected", "i.pdf": "failed",
                   "j.pdf": "incomplete", "k.pdf": "incomplete"}, got
    ents = classify(rs, db_hits, st, retry_failed=True)
    assert next(e for e in ents if e["path"] == "d.pdf")["pdf_id"] == "pd"
    assert next(e for e in ents if e["path"] == "h.pdf")["category"] == "scanned"
    print("triage self-check OK")
