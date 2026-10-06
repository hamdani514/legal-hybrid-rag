"""
Cross-store audit (and repair) of every judgment's search stores.

    python -m app.indexing.check                       # read-only report
    python -m app.indexing.check --pdf-id <id>         # one judgment
    python -m app.indexing.check --repair              # fill missing stores (no LLM)
    python -m app.indexing.check --repair --with-cards # ... and build missing cards (LLM)
    python -m app.indexing.check --prune-orphans       # delete entries with no document
    python -m app.indexing.check --json out.json       # machine-readable report

Why this exists
---------------
A judgment is searchable only when five stores agree (tree, dense, fts, card,
card_vector; see app/indexing/sync.py). They are written by different code at
different times — bulk ingest, the admin upload, the card wave, reindex — and
any of them can be interrupted: a kill mid-embedding, a 429 on the card call, a
restart mid-upload. documents.index_status records what the writers believe;
this tool checks what is ACTUALLY in each store, so a gap can be found and
filled after every batch instead of discovered as "my case doesn't come up".

What "present" means (per judgment, pdf_id = J)
-----------------------------------------------
tree         document_trees has J, and its tree_id has nodes in `nodes`
dense        every node of that tree has an embedding_mappings row, no mapping
             points at a node outside it, and the live Chroma collection holds
             exactly sum(chunk_count) vectors with file_id J. (embedding_mappings
             IS the index app.retrieval.index_loader reads; the old
             connection/*.json mirror is no longer written or required.)
fts          chunks_fts has rows for J, and cards_fts has J's card if a card exists
card         case_cards has J with card_status "complete" (metadata_only = gap)
card_vector  the card collection has id J, built from the card's current
             card_status (a vector made from a metadata-only card is stale)

Orphans: entries in any store whose judgment has no `documents` row (nodes,
trees, mappings, live vectors, connection files, FTS rows, cards, card vectors,
jobs). They are reported; --prune-orphans removes them (refused on the
production DB without --allow-main-db).

Exit code: 0 when every document has every required store (tree, dense, fts)
and there are no orphans; 1 otherwise; 2 when MongoDB is unreachable. Missing
cards are reported but only fail the run with --require-cards, because cards
arrive in their own wave.

Read-only unless --repair / --prune-orphans. The audit loads each store once
(one Chroma metadata read per collection, one SQL GROUP BY), so a 3,000-judgment
archive is checked in seconds.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from loguru import logger

from app.config import settings
from app.database import db
from app.retrieval.contracts import INDEX_REQUIRED_FOR_SEARCH, INDEX_STORES

PROTECTED_DB = "legal_rag"


# ── loading the stores ───────────────────────────────────────────────────────

def _live_collection():
    from app.vectorstore.chroma_store import chroma_store

    return chroma_store.collection


def _card_collection():
    from app.indexing.sync import _existing_collection
    from app.retrieval.dense_cards import collection_name

    return _existing_collection(collection_name())


def _chroma_by_file(coll, pdf_id: str | None) -> dict[str, int]:
    if coll is None:
        return {}
    got = coll.get(where={"file_id": pdf_id}, include=["metadatas"]) if pdf_id \
        else coll.get(include=["metadatas"])
    out: dict[str, int] = defaultdict(int)
    for m in got.get("metadatas") or []:
        out[(m or {}).get("file_id", "")] += 1
    return dict(out)


def _card_vectors(pdf_id: str | None) -> dict[str, dict]:
    coll = _card_collection()
    if coll is None:
        return {}
    got = coll.get(ids=[pdf_id], include=["metadatas"]) if pdf_id else coll.get(include=["metadatas"])
    return {i: (m or {}) for i, m in zip(got.get("ids") or [], got.get("metadatas") or [])}


def _fts(pdf_id: str | None) -> tuple[dict[str, int], set[str]]:
    from app.indexing.fts_index import db_path

    path = db_path()
    if not Path(path).exists():
        return {}, set()
    con = sqlite3.connect(str(path), timeout=10)
    try:
        try:
            if pdf_id:
                n = con.execute("SELECT count(*) FROM chunks_fts WHERE judgment_id = ?", (pdf_id,)).fetchone()[0]
                chunks = {pdf_id: n} if n else {}
                cards = {r[0] for r in con.execute("SELECT judgment_id FROM cards_fts WHERE judgment_id = ?", (pdf_id,))}
            else:
                chunks = dict(con.execute("SELECT judgment_id, count(*) FROM chunks_fts GROUP BY judgment_id"))
                cards = {r[0] for r in con.execute("SELECT judgment_id FROM cards_fts")}
        except sqlite3.OperationalError:  # tables not created yet
            return {}, set()
    finally:
        con.close()
    return chunks, cards


def _connection_files(pdf_id: str | None) -> dict[str, int]:
    """pdf_id -> number of entries in its connection JSON (-1 if unreadable)."""
    from app.ingestion.embedding_pipeline import connection_dir

    root = connection_dir()
    out: dict[str, int] = {}
    if not root.is_dir():
        return out
    names = [f"{pdf_id}_mappings.json"] if pdf_id else [n for n in os.listdir(root) if n.endswith("_mappings.json")]
    for name in names:
        p = root / name
        if not p.exists():
            continue
        try:
            out[name[: -len("_mappings.json")]] = len(json.loads(p.read_text(encoding="utf-8")))
        except Exception:  # noqa: BLE001
            out[name[: -len("_mappings.json")]] = -1
    return out


async def load_snapshot(pdf_id: str | None = None) -> dict:
    d = db.database
    q = {"pdf_id": pdf_id} if pdf_id else {}
    fq = {"file_id": pdf_id} if pdf_id else {}
    jq = {"judgment_id": pdf_id} if pdf_id else {}
    snap: dict = {
        "docs": {x["pdf_id"]: x async for x in d.documents.find(q, {
            "_id": 0, "pdf_id": 1, "status": 1, "filename": 1, "tree_id": 1, "index_status": 1})},
        "jobs": {x.get("pdf_id") or x.get("job_id") async for x in d.jobs.find(q if pdf_id else {}, {"pdf_id": 1, "job_id": 1})},
        "trees": defaultdict(list),
        "nodes": defaultdict(lambda: defaultdict(set)),
        "mappings": defaultdict(dict),
        "cards": {},
    }
    async for t in d.document_trees.find(q, {"_id": 0, "pdf_id": 1, "tree_id": 1}):
        snap["trees"][t["pdf_id"]].append(t["tree_id"])
    async for n in d.nodes.find(q, {"_id": 0, "pdf_id": 1, "tree_id": 1, "node_id": 1}):
        snap["nodes"][n.get("pdf_id")][n.get("tree_id")].add(n["node_id"])
    async for m in d.embedding_mappings.find(fq, {"_id": 0, "file_id": 1, "node_id": 1, "chunk_count": 1}):
        snap["mappings"][m.get("file_id")][m["node_id"]] = int(m.get("chunk_count") or 0)
    async for c in d.case_cards.find(jq, {"_id": 0, "judgment_id": 1, "card_status": 1}):
        snap["cards"][c["judgment_id"]] = c
    # Synchronous store reads (Chroma, SQLite, files) off the event loop.
    snap["live"] = await asyncio.to_thread(_chroma_by_file, _live_collection(), pdf_id)
    snap["card_vectors"] = await asyncio.to_thread(_card_vectors, pdf_id)
    snap["fts_chunks"], snap["fts_cards"] = await asyncio.to_thread(_fts, pdf_id)
    snap["conn"] = await asyncio.to_thread(_connection_files, pdf_id)
    return snap


# ── evaluation ───────────────────────────────────────────────────────────────

def evaluate(pdf_id: str, snap: dict) -> dict:
    """Which stores are present for one judgment, with a note per gap."""
    notes: list[str] = []
    trees = snap["trees"].get(pdf_id, [])
    nodes_by_tree = snap["nodes"].get(pdf_id, {})
    tree_nodes: set[str] = set()
    tree_id = None
    for t in trees:
        if nodes_by_tree.get(t):
            tree_id, tree_nodes = t, set(nodes_by_tree[t])
            break
    tree = bool(tree_nodes)
    if len(trees) > 1:
        notes.append(f"{len(trees)} trees")
    if not trees:
        notes.append("no tree")
    elif not tree:
        notes.append("tree has no nodes")
    stray_nodes = sum(len(v) for k, v in nodes_by_tree.items() if k != tree_id)
    if stray_nodes:
        notes.append(f"{stray_nodes} nodes outside the tree")

    mapped = snap["mappings"].get(pdf_id, {})
    expected_vectors = sum(mapped.values())
    live = snap["live"].get(pdf_id, 0)
    dense = tree and set(mapped) == tree_nodes and live == expected_vectors > 0
    if tree and not dense:
        if not mapped:
            notes.append("no vectors")
        else:
            if set(mapped) != tree_nodes:
                notes.append(f"mappings {len(set(mapped) & tree_nodes)}/{len(tree_nodes)} nodes"
                             + (f" +{len(set(mapped) - tree_nodes)} stale" if set(mapped) - tree_nodes else ""))
            if live != expected_vectors:
                notes.append(f"live vectors {live}/{expected_vectors}")

    card_doc = snap["cards"].get(pdf_id)
    card = bool(card_doc) and card_doc.get("card_status") == "complete"
    if card_doc and not card:
        notes.append(f"card {card_doc.get('card_status')}")
    elif not card_doc:
        notes.append("no card")

    fts_rows = snap["fts_chunks"].get(pdf_id, 0)
    fts = fts_rows > 0 and (not card_doc or pdf_id in snap["fts_cards"])
    if tree and not fts:
        notes.append("no FTS rows" if not fts_rows else "FTS card row missing")

    vec = snap["card_vectors"].get(pdf_id)
    card_vector = vec is not None and bool(card_doc) and (
        "card_status" not in vec or vec.get("card_status") == card_doc.get("card_status"))
    if card_doc and vec is None:
        notes.append("no card vector")
    elif card_doc and not card_vector:
        notes.append("card vector stale")

    flags = {"tree": tree, "dense": bool(dense), "fts": fts, "card": card, "card_vector": card_vector}
    doc = snap["docs"].get(pdf_id) or {}
    recorded = doc.get("index_status") or {}
    return {
        "pdf_id": pdf_id, **flags,
        "card_present": bool(card_doc),
        "status": doc.get("status"),
        "filename": doc.get("filename", ""),
        "required_ok": all(flags[s] for s in INDEX_REQUIRED_FOR_SEARCH),
        "recorded_mismatch": [s for s in INDEX_STORES if s in recorded and bool(recorded[s]) != flags[s]],
        "notes": ", ".join(notes),
    }


def find_orphans(snap: dict) -> dict[str, list[str]]:
    docs = set(snap["docs"])
    out = {
        "nodes": sorted(k for k in snap["nodes"] if k not in docs),
        "document_trees": sorted(k for k in snap["trees"] if k not in docs),
        "embedding_mappings": sorted(k for k in snap["mappings"] if k not in docs),
        "live_vectors": sorted(k for k in snap["live"] if k not in docs),
        "connection_json": sorted(k for k in snap["conn"] if k not in docs),
        "fts": sorted(k for k in set(snap["fts_chunks"]) | snap["fts_cards"] if k not in docs),
        "case_cards": sorted(k for k in snap["cards"] if k not in docs),
        "card_vectors": sorted(k for k in snap["card_vectors"] if k not in docs),
        "jobs": sorted(k for k in snap["jobs"] if k and k not in docs),
    }
    return {k: v for k, v in out.items() if v}


async def inspect_one(pdf_id: str) -> dict:
    """Actual store presence for one judgment (used by sync.complete_judgment)."""
    return evaluate(pdf_id, await load_snapshot(pdf_id))


async def audit(pdf_id: str | None = None) -> dict:
    snap = await load_snapshot(pdf_id)
    rows = [evaluate(j, snap) for j in sorted(snap["docs"])]
    orphans = {} if pdf_id else find_orphans(snap)
    gaps = {s: sum(1 for r in rows if not r[s]) for s in INDEX_STORES}
    by_status: dict[str, int] = defaultdict(int)
    for r in rows:
        by_status[str(r["status"])] += 1
    return {
        "db": db.database.name,
        "collections": {"live": settings.CHROMA_COLLECTION, "cards": _card_coll_name()},
        "documents": len(rows),
        "searchable": sum(1 for r in rows if r["required_ok"]),
        "complete": sum(1 for r in rows if all(r[s] for s in INDEX_STORES)),
        "gaps": gaps,
        "required_gaps": sum(1 for r in rows if not r["required_ok"]),
        "by_status": dict(sorted(by_status.items())),
        "orphans": orphans,
        "rows": rows,
    }


def _card_coll_name() -> str:
    from app.retrieval.dense_cards import collection_name

    return collection_name()


# ── repair / prune ───────────────────────────────────────────────────────────

async def prune_orphans(orphans: dict[str, list[str]]) -> dict:
    """Remove every store entry whose judgment has no document."""
    from app.indexing.sync import unindex_judgment
    from app.ingestion.embedding_pipeline import connection_dir
    from app.vectorstore.chroma_store import chroma_store

    ids = sorted({j for v in orphans.values() for j in v})
    d = db.database
    for j in ids:
        await d.nodes.delete_many({"pdf_id": j})
        await d.document_trees.delete_many({"pdf_id": j})
        await d.embedding_mappings.delete_many({"file_id": j})
        await d.jobs.delete_many({"$or": [{"pdf_id": j}, {"job_id": j}]})
        await asyncio.to_thread(chroma_store.delete_by_file_id, j)
        f = connection_dir() / f"{j}_mappings.json"
        if f.exists():
            f.unlink()
        await unindex_judgment(j)
    return {"pruned": len(ids)}


def render(rep: dict, show_all: bool = False) -> str:
    cols = ("tree", "dense", "fts", "card", "card_vector")
    lines = [
        f"db={rep['db']}  live={rep['collections']['live']}  cards={rep['collections']['cards']}",
        f"documents {rep['documents']}  searchable {rep['searchable']}  complete {rep['complete']}  "
        f"required gaps {rep['required_gaps']}",
        "missing per store: " + "  ".join(f"{s}={rep['gaps'][s]}" for s in cols),
        "status: " + "  ".join(f"{k}={v}" for k, v in rep["by_status"].items()),
        "",
        f"{'pdf_id':<10} {'status':<11} " + " ".join(f"{c[:5]:>5}" for c in cols) + "  notes",
    ]
    shown = 0
    for r in rep["rows"]:
        if not show_all and all(r[c] for c in cols) and not r["recorded_mismatch"]:
            continue
        shown += 1
        marks = " ".join(f"{'ok' if r[c] else '--':>5}" for c in cols)
        extra = f"  [recorded != actual: {','.join(r['recorded_mismatch'])}]" if r["recorded_mismatch"] else ""
        lines.append(f"{r['pdf_id'][:8]:<10} {str(r['status'])[:11]:<11} {marks}  {r['notes']}{extra}")
    if not shown:
        lines.append("(every judgment has every store)")
    if rep["orphans"]:
        lines.append("")
        lines.append("orphans (store entries with no document):")
        for k, v in rep["orphans"].items():
            lines.append(f"  {k:<20} {len(v):>5}  e.g. {', '.join(x[:8] for x in v[:3])}")
    return "\n".join(lines)


def exit_code(rep: dict, require_cards: bool = False) -> int:
    bad = rep["required_gaps"] > 0 or bool(rep["orphans"])
    if require_cards:
        bad = bad or rep["gaps"]["card"] > 0 or rep["gaps"]["card_vector"] > 0
    return 1 if bad else 0


async def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Audit (and repair) every judgment's search stores.")
    p.add_argument("--pdf-id")
    p.add_argument("--repair", action="store_true", help="fill missing stores (no LLM call)")
    p.add_argument("--with-cards", action="store_true", help="with --repair: also build missing cards (LLM)")
    p.add_argument("--prune-orphans", action="store_true", help="delete store entries with no document")
    p.add_argument("--allow-main-db", action="store_true", help=f"required for --prune-orphans on '{PROTECTED_DB}'")
    p.add_argument("--require-cards", action="store_true", help="missing cards fail the run too")
    p.add_argument("--all-rows", action="store_true", help="print judgments with no gaps as well")
    p.add_argument("--json", type=Path, help="write the full report as JSON")
    args = p.parse_args(argv)

    from app.database import close_db, connect_db

    await connect_db()
    if db.database is None:
        print("MongoDB is not connected (check MONGO_URL).", file=sys.stderr)
        return 2
    protected = db.database.name.lower() == PROTECTED_DB
    try:
        rep = await audit(args.pdf_id)
        if args.repair:
            from app.indexing.sync import repair_judgment

            targets = [r["pdf_id"] for r in rep["rows"]]
            print(f"repairing {len(targets)} judgments in {rep['db']} "
                  f"({'with' if args.with_cards else 'no'} LLM card calls)")
            for j in targets:
                res = await repair_judgment(j, with_cards=args.with_cards,
                                            allow_delete=not protected or args.allow_main_db)
                if res["actions"] != ["none needed"]:
                    print(f"  {j[:8]}  {'ok ' if res['ok'] else 'GAP'}  {'; '.join(res['actions'])}")
        if args.prune_orphans and rep["orphans"]:
            if protected and not args.allow_main_db:
                print(f"refusing --prune-orphans on '{PROTECTED_DB}' without --allow-main-db", file=sys.stderr)
            else:
                print(f"pruned: {await prune_orphans(rep['orphans'])}")
        if args.repair or args.prune_orphans:
            rep = await audit(args.pdf_id)
        print(render(rep, show_all=args.all_rows))
        if args.json:
            args.json.write_text(json.dumps(rep, indent=2, default=str), encoding="utf-8")
        return exit_code(rep, args.require_cards)
    finally:
        await close_db()


def _self_check() -> None:
    """Offline evaluation checks on a synthetic snapshot (no stores touched)."""
    def snap(**over):
        base = {
            "docs": {"J": {"pdf_id": "J", "status": "searchable"}}, "jobs": {"J"},
            "trees": {"J": ["T"]}, "nodes": {"J": {"T": {"a", "b"}}},
            "mappings": {"J": {"a": 1, "b": 2}}, "live": {"J": 3}, "conn": {"J": 2},
            "fts_chunks": {"J": 2}, "fts_cards": {"J"},
            "cards": {"J": {"judgment_id": "J", "card_status": "complete"}},
            "card_vectors": {"J": {"card_status": "complete"}},
        }
        base.update(over)
        return base

    r = evaluate("J", snap())
    assert all(r[s] for s in INDEX_STORES) and r["required_ok"], r
    assert not evaluate("J", snap(live={"J": 2}))["dense"]            # a chunk missing in Chroma
    assert evaluate("J", snap(conn={}))["dense"]   # the JSON mirror is gone: dense must not depend on it
    assert not evaluate("J", snap(mappings={"J": {"a": 1}}, live={"J": 1}))["dense"]  # node unmapped
    assert not evaluate("J", snap(trees={}))["tree"]
    r = evaluate("J", snap(cards={"J": {"card_status": "metadata_only"}},
                           card_vectors={"J": {"card_status": "metadata_only"}}))
    assert r["required_ok"] and not r["card"] and r["card_vector"], r   # searchable, card pending
    assert not evaluate("J", snap(card_vectors={"J": {"card_status": "metadata_only"}}))["card_vector"]
    assert not evaluate("J", snap(fts_cards=set()))["fts"]              # card row missing from FTS
    r = evaluate("J", snap(cards={}, card_vectors={}, fts_cards=set()))
    assert r["fts"] and not r["card"] and not r["card_vector"] and r["required_ok"]
    o = find_orphans(snap(live={"J": 3, "X": 4}, conn={"J": 2, "Y": 1}, jobs={"J", "Z"}))
    assert o == {"live_vectors": ["X"], "connection_json": ["Y"], "jobs": ["Z"]}, o
    rep = {"required_gaps": 0, "orphans": {}, "gaps": {"card": 1, "card_vector": 1}}
    assert exit_code(rep) == 0 and exit_code(rep, require_cards=True) == 1
    print("check self-check OK")


if __name__ == "__main__":
    if "--self-check" in sys.argv:
        _self_check()
        raise SystemExit(0)
    logger.remove()
    logger.add(sys.stderr, level=os.environ.get("CHECK_LOG_LEVEL", "WARNING"))
    raise SystemExit(asyncio.run(main()))
