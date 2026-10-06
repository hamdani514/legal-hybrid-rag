"""
The bulk ingestion driver: triage, then two queues feeding one bounded LLM stage.

Why this shape:

* OCR is synchronous, CPU-bound and single-threaded per page (Tesseract), so
  scanned files go to a ProcessPoolExecutor and run in parallel across cores.
  Digital extraction is milliseconds of PyMuPDF and runs on a thread.
* LLM parsing is async and limited by the provider quota, not by us, so it is
  gated by LLMGuard's semaphore with backoff on 429 (see llm_guard.py).
* Each file walks the full chain the admin upload walks, calling the same
  functions: extract -> parse_sections -> ensure_tree -> (sync.complete_judgment:)
  dense embedding -> FTS -> card vector if a card exists [-> Drive]. It writes
  the same `jobs` / `documents` fields and per-store index_status, so a
  bulk-ingested judgment is indistinguishable from an uploaded one and is
  SEARCHABLE as soon as its file finishes. Additions live on `jobs` only
  (ingest_source, source_path, embedding_status, bulk_timings).
* No LLM call after the parse: the case card (one Gemini call) comes in the
  card wave (python -m app.ingestion.case_card --all), which moves documents
  from "searchable" to "complete". --tree-only restores the old stop-after-tree
  behaviour. Drive upload is OFF by default.
* Embedding is CPU-bound: it runs in a worker thread (embedding_pipeline uses
  asyncio.to_thread) behind a 1-slot semaphore, so it neither blocks the event
  loop that drives the LLM parses nor thrashes the cores the OCR pool uses.

Resume semantics (all driven by triage on the next run):
  searchable/complete with every required store recorded -> skipped as duplicate
  in-flight in DB -> resumed; a file whose tree exists skips extract/parse and
                     only fills the missing stores (complete_judgment inspects
                     what is actually present, so nothing is re-embedded twice);
                     otherwise extract() and parse_sections() find their cached
                     uploads/{pdf_id}.txt / _sections.json, so finished stages
                     cost nothing; the tree step is idempotent (ensure_tree)
  failed in DB    -> resumed only with --retry-failed (same rules)
  killed mid-OCR  -> no DB record yet; the pdf_id is reused from state.jsonl
Ctrl-C cancels in-flight tasks and still writes the report; files caught
mid-flight keep their in-flight status and are resumed next run.
"""
from __future__ import annotations

import asyncio
import os
import shutil
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from loguru import logger

from app.ingestion.bulk import report as rpt
from app.ingestion.bulk.llm_guard import LLMGuard
from app.ingestion.bulk.state import StateStore
from app.ingestion.bulk.triage import TO_PROCESS, triage
from app.ingestion.bulk.workers import ocr_one, pool_kwargs

BACKEND_DIR = Path(__file__).resolve().parents[3]
UPLOADS_DIR = BACKEND_DIR / "uploads"

# The production database. Any run that WRITES to it must pass
# --allow-main-db, and every delete/cleanup path below re-checks the guard,
# so a pilot or a test cleanup can only ever touch a scratch database.
PROTECTED_DB = "legal_rag"


class MainDBGuardError(RuntimeError):
    pass


def is_protected(db_name: str, protected: str = PROTECTED_DB) -> bool:
    return (db_name or "").strip().lower() == protected.strip().lower()


def default_ocr_workers() -> int:
    """cpu_count - 4, capped by free RAM.

    A worker is ~130 MB idle (easyocr deferred) and peaks around ~450 MB while
    preprocessing a 300-DPI page (upscale + fastNlMeansDenoising on a
    ~5000x7000 grayscale image). On a 16 GB machine that is already busy, the
    CPU-based default alone can exhaust memory, so it is capped.
    """
    cpu = os.cpu_count() or 4
    n = max(1, cpu - 4)
    try:
        import psutil

        avail = psutil.virtual_memory().available
        n = min(n, max(1, int(avail // (450 * 1024 * 1024))))
    except Exception:  # noqa: BLE001
        pass
    return n


@dataclass
class Options:
    input_dir: Path
    triage_only: bool = False
    pilot: int | None = None
    llm_concurrency: int = 3
    ocr_workers: int = field(default_factory=default_ocr_workers)
    retry_failed: bool = False
    embed: bool = True          # full chain to "searchable"; False = stop after the tree
    drive: bool = False
    recursive: bool = False
    max_attempts: int = 5
    backoff_base: float = 5.0
    parse_timeout: float = 600.0
    report_dir: Path = BACKEND_DIR / "ingest_reports"
    allow_main_db: bool = False
    protected_db: str = PROTECTED_DB


class BulkIngester:
    def __init__(self, opts: Options, db_proxy, db_name: str):
        self.o = opts
        self.db = db_proxy
        self.db_name = db_name
        self.protected = is_protected(db_name, opts.protected_db)
        # Deletes (orphan nodes, degraded parse caches) are allowed only on a
        # non-production database, or on production with an explicit flag.
        self.destructive_ok = (not self.protected) or opts.allow_main_db
        if self.protected and not opts.triage_only and not opts.allow_main_db:
            raise MainDBGuardError(
                f"Refusing to ingest into the production database '{db_name}' without "
                f"--allow-main-db. Use DB_NAME=<scratch db> for pilots and tests.")
        self.run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
        self.run_dir = opts.report_dir / f"{self.run_id}_{db_name}"
        # One state file per database: a test run must never leak pdf_ids or
        # rejections into a production run.
        self.state = StateStore(opts.report_dir / f"state_{db_name}.jsonl")
        self.guard = LLMGuard(concurrency=opts.llm_concurrency, max_attempts=opts.max_attempts,
                              base_delay=opts.backoff_base, parse_timeout=opts.parse_timeout,
                              uploads_dir=UPLOADS_DIR, allow_cleanup=self.destructive_ok)
        # Bounds how many files hold DB records + text in memory at once, so
        # 2,000 digital files do not all flip to "uploaded" in the first second.
        self.admission = asyncio.Semaphore(max(4, opts.llm_concurrency * 4))
        self.embed_sem = asyncio.Semaphore(1)
        self.results: list[dict] = []
        self.t_start = 0.0
        self.loop_lag = {"max_s": 0.0, "stalls_over_1s": 0}

    async def _watch_loop(self) -> None:
        """Measure event-loop stalls. Everything async here (LLM calls, Mongo,
        backoff timers) shares one loop, so synchronous work inside a stage
        (parse_sections' CPU passes, imports, client construction) delays all
        in-flight files at once; this makes such stalls visible in the report."""
        while True:
            t = time.perf_counter()
            await asyncio.sleep(0.25)
            lag = time.perf_counter() - t - 0.25
            if lag > self.loop_lag["max_s"]:
                self.loop_lag["max_s"] = round(lag, 3)
            if lag > 1.0:
                self.loop_lag["stalls_over_1s"] += 1
                logger.debug(f"bulk: event loop stalled {lag:.2f}s")

    # ── entry ──────────────────────────────────────────────────────────
    async def run(self) -> dict:
        o = self.o
        entries, summary = await triage(o.input_dir, self.db.database, self.state,
                                        workers=o.ocr_workers, retry_failed=o.retry_failed,
                                        recursive=o.recursive)
        rpt.write_json(self.run_dir / "manifest.json", {"summary": summary, "files": entries})
        print(rpt.render_triage(summary, entries))
        print(f"manifest: {self.run_dir / 'manifest.json'}")
        if o.triage_only:
            return {"triage": summary}

        work = [e for e in entries if e["category"] in TO_PROCESS
                and (e["category"] != "failed" or o.retry_failed)]
        if o.pilot:
            work = work[:o.pilot]
        logger.info(f"Processing {len(work)} files: "
                    f"{sum(1 for e in work if e.get('detected_type') == 'scanned')} scanned, "
                    f"OCR workers {o.ocr_workers}, LLM concurrency {o.llm_concurrency}")

        self.guard.install()
        # LLM worker processes: see workers.parse_one for the measured reason.
        llm_pool = (ProcessPoolExecutor(max_workers=max(1, o.llm_concurrency), **pool_kwargs("WARNING"))
                    if work else None)
        self.guard.pool = llm_pool
        pool = ProcessPoolExecutor(max_workers=max(1, o.ocr_workers), **pool_kwargs("WARNING")) \
            if any(e.get("detected_type") == "scanned" for e in work) else None
        if work and o.embed:
            # torch / chromadb imports take seconds; never on the event loop.
            from app.indexing.sync import warm_imports
            await warm_imports()
        self.t_start = time.perf_counter()
        watcher = asyncio.create_task(self._watch_loop())
        tasks = [asyncio.create_task(self._process(e, pool)) for e in work]
        interrupted = False
        try:
            await asyncio.gather(*tasks)
        except (asyncio.CancelledError, KeyboardInterrupt):
            interrupted = True
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
        finally:
            watcher.cancel()
            if llm_pool is not None:
                llm_pool.shutdown(wait=not interrupted, cancel_futures=True)
            if pool is not None:
                pool.shutdown(wait=not interrupted, cancel_futures=True)
            self.guard.uninstall()
            wall = time.perf_counter() - self.t_start
            rep = rpt.build_report(run_id=self.run_id, db_name=self.db_name,
                                   options={k: str(v) for k, v in asdict(o).items()},
                                   triage_summary=summary, results=self.results,
                                   processing_wall_s=wall, llm_stats={**asdict(self.guard.stats), "event_loop_lag": self.loop_lag},
                                   interrupted=interrupted)
            rpt.write_json(self.run_dir / "report.json", rep)
            text = rpt.render_report(rep)
            (self.run_dir / "report.txt").write_text(text, encoding="utf-8")
            print(text)
            print(f"report: {self.run_dir / 'report.json'}")
        if interrupted:
            raise asyncio.CancelledError
        return rep

    # ── per file ───────────────────────────────────────────────────────
    async def _process(self, e: dict, pool) -> None:
        t0 = time.perf_counter()
        h = e["file_hash"]
        queue = "scanned" if e.get("detected_type") == "scanned" else "digital"
        has_record = e["category"] in ("incomplete", "failed")
        pdf_id = e.get("pdf_id") or str(uuid4())
        filename = Path(e["path"]).name
        r = {"filename": filename, "path": e["path"], "pdf_id": pdf_id, "queue": queue,
             "category_in": e["category"], "pages": e.get("pages"), "outcome": "",
             "stage": "", "error": "", "timings": {}}
        if not has_record:
            self.state.record(h, pdf_id=pdf_id, path=e["path"], status="assigned")
        txt_cached = (UPLOADS_DIR / f"{pdf_id}.txt").exists()
        try:
            # 1. OCR (scanned, not yet extracted). No DB record until it passes.
            has_tree = has_record and bool(await self.db.database.document_trees.find_one(
                {"pdf_id": pdf_id}, {"_id": 1}))
            if queue == "scanned" and not txt_cached and not has_tree:
                r["stage"] = "ocr"
                src = self._pdf_path(pdf_id, e["path"])
                loop = asyncio.get_running_loop()
                ocr = await loop.run_in_executor(pool, ocr_one, src, pdf_id, not has_record)
                r["timings"]["validate"] = ocr["validate_s"]
                if not ocr["valid"]:
                    self.state.record(h, status="rejected", error=ocr["reason"])
                    r.update(outcome="rejected", error=ocr["reason"])
                    return
                r["timings"]["ocr"] = ocr["extract_s"]
                r["pages"] = ocr["pages"] or r["pages"]
                if ocr["error"]:
                    async with self.admission:
                        if not has_record:
                            await self._create_records(pdf_id, filename, h, "scanned", e["path"])
                        raise RuntimeError(ocr["error"])

            async with self.admission:
                if not has_record:
                    r["stage"] = "records"
                    await self._create_records(pdf_id, filename, h, e.get("detected_type") or "text",
                                               e["path"])
                await self._run_chain(pdf_id, e, r)
            self.state.record(h, status="done")
            r["outcome"] = "done"
        except asyncio.CancelledError:
            r.update(outcome="interrupted", error=f"interrupted during {r['stage']}")
            raise
        except Exception as ex:  # noqa: BLE001
            reason = f"{type(ex).__name__}: {ex}" if not isinstance(ex, RuntimeError) else str(ex)
            if isinstance(ex, asyncio.TimeoutError):
                reason = f"timed out during {r['stage']}"
            r.update(outcome="failed", error=reason)
            self.state.record(h, status="failed", error=reason)
            await self._mark_failed(pdf_id, reason, r["stage"])
            logger.error(f"[{pdf_id}] {filename} failed at {r['stage']}: {reason}")
        finally:
            r["total_s"] = round(time.perf_counter() - t0, 3)
            r["timings"]["total"] = r["total_s"]
            r["finished_offset_s"] = round(time.perf_counter() - self.t_start, 3)
            self.results.append(r)

    async def _run_chain(self, pdf_id: str, e: dict, r: dict) -> None:
        from app.ingestion.extractor import extract

        jobs, docs = self.db.jobs, self.db.documents
        dtype = e.get("detected_type") or "text"
        pdf_path = self._pdf_path(pdf_id, e["path"])
        now = lambda: datetime.now(timezone.utc)  # noqa: E731

        # Resume at the missing stores when an earlier run already built the
        # tree: re-extracting and re-parsing would cost time and, if the parse
        # cache is gone, a Gemini call, for a tree we already have.
        has_tree = await self.db.database.document_trees.find_one({"pdf_id": pdf_id}, {"_id": 1})
        if has_tree:
            r["resumed_at"] = "index"
            r["stage"] = "tree"
            await self._ensure_tree(pdf_id, None)
            prev = await docs.find_one({"pdf_id": pdf_id}, {"quality_passed": 1, "confidence": 1,
                                                            "quality_issues": 1, "parse_mode": 1})
            prev = prev or {}
            r.update(parse_mode=prev.get("parse_mode", ""), confidence=prev.get("confidence"),
                     quality_passed=prev.get("quality_passed"), quality_issues=prev.get("quality_issues"))
        else:
            # 2. Extract (digital: PyMuPDF; scanned: returns the cached OCR text).
            r["stage"] = "extract"
            await jobs.update_one({"job_id": pdf_id}, {"$set": {"status": "extracting", "updated_at": now()}})
            t = time.perf_counter()
            text = await asyncio.to_thread(extract, pdf_path=pdf_path, pdf_id=pdf_id, detected_type=dtype)
            if "ocr" not in r["timings"]:
                r["timings"]["extract"] = round(time.perf_counter() - t, 3)
            await jobs.update_one({"job_id": pdf_id}, {"$set": {
                "status": "extracted", "char_count": len(text), "extracted_at": now(), "updated_at": now()}})
            await docs.update_one({"pdf_id": pdf_id}, {"$set": {"status": "extracted"}})

            # 3. Parse, bounded + retried.
            r["stage"] = "parse"
            await jobs.update_one({"job_id": pdf_id}, {"$set": {"status": "parsing", "updated_at": now()}})
            final, info = await self.guard.parse(pdf_id, text)
            r["timings"]["parse_llm"] = round(info["llm_seconds"], 3)
            r["parse_attempts"] = info["attempts"]
            quality = {
                "parse_mode": final.get("parse_mode", ""),
                "confidence": float(final.get("confidence_score", 0.0) or 0.0),
                "quality_passed": bool(final.get("quality_passed", True)),
                "quality_issues": final.get("quality_issues", []),
            }
            await jobs.update_one({"job_id": pdf_id}, {"$set": {
                "status": "parsed", "parsed_at": now(), "updated_at": now(), **quality}})
            await docs.update_one({"pdf_id": pdf_id}, {"$set": {"status": "parsed", **quality}})
            r.update(parse_mode=quality["parse_mode"], confidence=quality["confidence"],
                     quality_passed=quality["quality_passed"], quality_issues=quality["quality_issues"])
            if not quality["quality_passed"]:
                logger.warning(f"[{pdf_id}] Parse flagged for review "
                               f"(confidence {quality['confidence']:.2f}): {quality['quality_issues']}")

            # 4. Tree (documents.status -> "indexing", index_status.tree).
            r["stage"] = "tree"
            t = time.perf_counter()
            await jobs.update_one({"job_id": pdf_id}, {"$set": {"status": "tree", "updated_at": now()}})
            await self._ensure_tree(pdf_id, final)
            r["timings"]["tree"] = round(time.perf_counter() - t, 3)

        # 5. Dense + FTS (+ card vector if a card already exists): searchable.
        embedding_status = "pending"
        if self.o.embed:
            from app.indexing.sync import complete_judgment

            r["stage"] = "index"
            await jobs.update_one({"job_id": pdf_id}, {"$set": {"status": "embedding", "updated_at": now()}})
            t = time.perf_counter()
            async with self.embed_sem:
                res = await complete_judgment(pdf_id, build_card=False)
            r["timings"]["index"] = round(time.perf_counter() - t, 3)
            r["index"] = {"dense": res["dense"], "stores": res["stores"]}
            embedding_status = "done"

        # 6. Optional Drive upload, same record shape as run_extraction.
        drive_fields: dict = {"drive_status": "skipped"}
        if self.o.drive:
            r["stage"] = "drive"
            t = time.perf_counter()
            try:
                drive_fields = await self._upload_drive(pdf_id, pdf_path, Path(e["path"]).name)
            except Exception as ex:  # noqa: BLE001 - the judgment is searchable; Drive is a copy
                drive_fields = {"drive_status": f"failed: {ex}"}
                logger.error(f"[{pdf_id}] Drive upload failed: {ex}")
            r["timings"]["drive"] = round(time.perf_counter() - t, 3)

        doc = await docs.find_one({"pdf_id": pdf_id}, {"status": 1})
        r["doc_status"] = (doc or {}).get("status")
        await jobs.update_one({"job_id": pdf_id}, {"$set": {
            "status": r["doc_status"] if self.o.embed else "tree_done",
            "completed_at": now(), "updated_at": now(),
            "embedding_status": embedding_status, "bulk_timings": r["timings"], **drive_fields}})
        r["stage"] = "done"

    # ── helpers ────────────────────────────────────────────────────────
    @staticmethod
    def _pdf_path(pdf_id: str, source: str) -> str:
        local = UPLOADS_DIR / f"{pdf_id}.pdf"
        return str(local) if local.exists() else source

    async def _create_records(self, pdf_id: str, filename: str, file_hash: str,
                              detected_type: str, source_path: str) -> None:
        """Mirror upload_pdf: copy to uploads/{pdf_id}.pdf, insert jobs + documents."""
        dest = UPLOADS_DIR / f"{pdf_id}.pdf"
        if not dest.exists():
            await asyncio.to_thread(shutil.copyfile, source_path, dest)
        now = datetime.now(timezone.utc)
        await self.db.jobs.insert_one({
            "job_id": pdf_id, "pdf_id": pdf_id, "filename": filename,
            "detected_type": detected_type, "status": "uploaded", "created_at": now,
            "file_hash": file_hash,
            "ingest_source": "bulk", "source_path": source_path, "bulk_run_id": self.run_id,
        })
        await self.db.documents.insert_one({
            "pdf_id": pdf_id, "filename": filename, "detected_type": detected_type,
            "status": "uploaded", "upload_date": now, "total_nodes": 0, "file_hash": file_hash,
        })

    async def _ensure_tree(self, pdf_id: str, final: dict | None) -> None:
        """tree_builder.ensure_tree, behind this run's production-DB guard.

        ensure_tree is idempotent: an existing tree is finalised, never built
        twice; orphan nodes from a build killed half-way are removed first,
        which counts as a delete and so needs --allow-main-db on production.
        """
        from app.ingestion.tree_builder import ensure_tree

        if self.db.database.name != self.db_name:  # proxy must point where we think
            raise MainDBGuardError(f"connected to '{self.db.database.name}', expected '{self.db_name}'")
        try:
            await ensure_tree(pdf_id, final, allow_delete=self.destructive_ok)
        except RuntimeError as ex:
            if "orphan nodes" in str(ex):
                raise MainDBGuardError(f"{ex} (require --allow-main-db on '{self.db_name}')") from ex
            raise

    # jobs.status per failed stage; documents.status is "failed" for all of them.
    FAILED_JOB_STATUS = {"ocr": "extraction_failed", "extract": "extraction_failed",
                         "records": "extraction_failed", "parse": "parse_failed",
                         "tree": "tree_failed", "index": "embedding_failed"}

    async def _mark_failed(self, pdf_id: str, reason: str, stage: str = "parse") -> None:
        """Failure fields named after the stage that failed (if records exist yet)."""
        try:
            from app.indexing.sync import record_index_status

            job_status = self.FAILED_JOB_STATUS.get(stage, f"{stage}_failed")
            if stage == "index" and reason.startswith("fts:"):
                job_status = "index_failed"
            now = datetime.now(timezone.utc)
            await self.db.jobs.update_one({"job_id": pdf_id}, {"$set": {
                "status": job_status, "error": reason, "failed_stage": stage,
                "failed_at": now, "updated_at": now}})
            await self.db.documents.update_one({"pdf_id": pdf_id}, {"$set": {"status": "failed"}})
            error = reason if reason.startswith(f"{stage}:") or ": " in reason[:14] else f"{stage}: {reason}"
            await record_index_status(pdf_id, error=error, failed=True)
        except Exception as ex:  # noqa: BLE001
            logger.error(f"[{pdf_id}] could not record failure: {ex}")

    async def _upload_drive(self, pdf_id: str, pdf_path: str, original_name: str) -> dict:
        from app.services.google_drive_service import google_drive_service

        res = await google_drive_service.upload_file(file_path=pdf_path, original_filename=original_name,
                                                     mime_type="application/pdf")
        now = datetime.now(timezone.utc)
        # No status here: Drive is a copy of the PDF, not a search store.
        await self.db.documents.update_one({"pdf_id": pdf_id}, {"$set": {
            "drive": {
                "file_id": res.get("file_id"), "file_name": res.get("file_name", original_name),
                "mime_type": res.get("mime_type", "application/pdf"),
                "web_view_link": res.get("web_view_link"), "web_content_link": res.get("web_content_link"),
                "uploaded_at": now, "account": google_drive_service.target_email,
                "status": res.get("status"),
            },
        }})
        return {"drive_file_id": res.get("file_id"), "drive_status": res.get("status")}
