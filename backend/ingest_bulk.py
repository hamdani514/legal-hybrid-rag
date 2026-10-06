"""
Bulk-ingest a folder of Supreme Court judgment PDFs (digital and scanned).

Why this exists: the admin upload path ingests one PDF per HTTP request, with
no OCR parallelism, no bound on concurrent LLM calls, no backoff when the
Gemini quota runs out (the parser swallows 429s and silently degrades), and no
resume. The 3,000+ judgment corpus needs all four. This CLI reuses the same
stage functions and writes the same MongoDB records as upload_pdf /
run_extraction; see app/ingestion/bulk/ for the design.

Usage (from backend/):
    python ingest_bulk.py --input DIR --triage-only           # manifest only, no writes
    python ingest_bulk.py --input DIR --pilot 50              # first 50 new files
    python ingest_bulk.py --input DIR                         # everything; re-run to resume
    python ingest_bulk.py --input DIR --retry-failed          # also retry failed files
    DB_NAME=legal_rag_bulktest python ingest_bulk.py ...      # any test database
    python ingest_bulk.py --input DIR --allow-main-db         # production (legal_rag) writes

Every finished file is SEARCHABLE: the chain is extract -> parse -> tree ->
dense embedding -> keyword (FTS) index (+ card vector if a card exists), with
per-store status on documents.index_status. Case cards (one Gemini call each)
come afterwards in the card wave; then check the stores:

    python -m app.indexing.check --repair      # after every batch; 0 gaps expected
    python -m app.ingestion.case_card --all    # card wave; re-run daily until done

Options: --llm-concurrency N (3)  --ocr-workers N (cpu-4, RAM-capped)
         --tree-only (stop after the tree, the old behaviour)  --drive (off)
         --recursive  --max-attempts N (5)  --backoff-base S (5)
         --parse-timeout S (600)  --report-dir DIR (backend/ingest_reports)

Outputs: <report-dir>/<run>_<db>/{manifest.json, report.json, report.txt, ingest.log}
and <report-dir>/state_<db>.jsonl (resume state).

Note for maintainers: keep this module free of top-level `app.*` imports.
Windows spawns pool workers by re-importing the main script; an app import
here would load easyocr + torch (~260 MB) into every OCR worker.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path


def _defer_easyocr() -> None:
    """Same deferral the pool workers use (see bulk/workers.py BOOTSTRAP_SRC):
    the parent process only needs easyocr if a digital file falls back to OCR."""
    import importlib
    import types

    if "easyocr" in sys.modules:
        return
    stub = types.ModuleType("easyocr")
    stub.__spec__ = None

    def _load(name):
        if name.startswith("__"):
            raise AttributeError(name)
        if sys.modules.get("easyocr") is stub:
            del sys.modules["easyocr"]
        return getattr(importlib.import_module("easyocr"), name)

    stub.__getattr__ = _load
    sys.modules["easyocr"] = stub


def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--input", required=True, type=Path, help="folder of PDFs")
    p.add_argument("--triage-only", action="store_true", help="hash/dedupe/detect, write manifest, stop")
    p.add_argument("--pilot", type=int, default=None, help="process only the first N files needing work")
    p.add_argument("--llm-concurrency", type=int, default=None)
    p.add_argument("--ocr-workers", type=int, default=None)
    p.add_argument("--retry-failed", action="store_true")
    p.add_argument("--embed", action="store_true",
                   help="(default now; kept for old command lines) embed + index to searchable")
    p.add_argument("--tree-only", action="store_true",
                   help="stop after the tree: no vectors, no keyword index (not searchable)")
    p.add_argument("--drive", action="store_true", help="also upload originals to Google Drive")
    p.add_argument("--recursive", action="store_true")
    p.add_argument("--max-attempts", type=int, default=None)
    p.add_argument("--backoff-base", type=float, default=None)
    p.add_argument("--parse-timeout", type=float, default=None)
    p.add_argument("--report-dir", type=Path, default=None)
    p.add_argument("--allow-main-db", action="store_true",
                   help="required to write to the production DB (legal_rag); pilots use DB_NAME=<scratch>")
    p.add_argument("--log-level", default="INFO")
    return p.parse_args(argv)


async def _amain(args: argparse.Namespace) -> int:
    from loguru import logger

    from app.config import settings
    from app.database import close_db, connect_db, db
    from app.ingestion.bulk.pipeline import (BACKEND_DIR, BulkIngester, MainDBGuardError, Options,
                                             default_ocr_workers)

    g = lambda name, default: getattr(settings, name, default)  # noqa: E731
    opts = Options(
        input_dir=args.input.resolve(),
        triage_only=args.triage_only,
        pilot=args.pilot,
        llm_concurrency=args.llm_concurrency or g("BULK_LLM_CONCURRENCY", 3),
        ocr_workers=args.ocr_workers or g("BULK_OCR_WORKERS", 0) or default_ocr_workers(),
        retry_failed=args.retry_failed,
        embed=not args.tree_only,
        drive=args.drive,
        recursive=args.recursive,
        max_attempts=args.max_attempts or g("BULK_MAX_ATTEMPTS", 5),
        backoff_base=args.backoff_base or g("BULK_BACKOFF_BASE_S", 5.0),
        parse_timeout=args.parse_timeout or g("BULK_PARSE_TIMEOUT_S", 600.0),
        allow_main_db=args.allow_main_db,
        report_dir=(args.report_dir or Path(g("BULK_REPORT_DIR", "") or BACKEND_DIR / "ingest_reports")).resolve(),
    )
    if not opts.input_dir.is_dir():
        print(f"--input is not a directory: {opts.input_dir}", file=sys.stderr)
        return 2

    await connect_db()
    if db.database is None:
        print("MongoDB is not connected (check MONGO_URL).", file=sys.stderr)
        return 2
    db_name = db.database.name  # what we are ACTUALLY connected to, not what we meant
    if db_name != settings.DB_NAME:
        print(f"Connected DB '{db_name}' != settings.DB_NAME '{settings.DB_NAME}'", file=sys.stderr)
        return 2
    try:
        ing = BulkIngester(opts, db, db_name)
    except MainDBGuardError as e:
        print(str(e), file=sys.stderr)
        await close_db()
        return 3
    ing.run_dir.mkdir(parents=True, exist_ok=True)
    logger.add(ing.run_dir / "ingest.log", level="DEBUG", enqueue=False)
    mode = "TRIAGE ONLY (read-only)" if opts.triage_only else "INGEST"
    logger.info(f"Bulk ingest {mode}: db={db_name} input={opts.input_dir} "
                f"ocr_workers={opts.ocr_workers} llm_concurrency={opts.llm_concurrency} "
                f"embed={opts.embed} drive={opts.drive} pilot={opts.pilot}")
    try:
        rep = await ing.run()
    finally:
        await close_db()
    if opts.triage_only:
        return 0
    return 0 if not rep.get("failures") else 1


def main(argv=None) -> int:
    args = parse_args(argv)
    _defer_easyocr()
    from loguru import logger

    logger.remove()
    logger.add(sys.stderr, level=args.log_level.upper())
    try:
        return asyncio.run(_amain(args))
    except KeyboardInterrupt:
        print("\nInterrupted. In-flight files keep their status and resume on the next run.",
              file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
