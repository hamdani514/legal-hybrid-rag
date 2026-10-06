from datetime import datetime, timezone
import hashlib
import asyncio
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from loguru import logger

from app.database import db
from app.ingestion.detector import detect_pdf_type
from app.ingestion.extractor import extract
from app.ingestion.parser import parse_sections
from app.vectorstore.chroma_store import chroma_store
from app.services.email_service import send_contact_notification, send_contact_acknowledgement

router = APIRouter(prefix="/api/admin", tags=["admin"])

UPLOADS_DIR = Path(__file__).resolve().parents[2] / "uploads"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

# The node -> vector index lives in MongoDB (embedding_mappings); the old
# app/connection/*.json mirror is no longer written, so nothing recreates that
# folder here. The delete path below still clears files left by older runs.


ACTIVE_INGESTION_TASKS: dict[str, asyncio.Task] = {}

# ── Single-upload ingestion ──────────────────────────────────────────────────
# An upload walks the same chain as bulk ingest (app/ingestion/bulk):
#   extract -> parse -> tree -> dense -> card -> FTS -> card vector [-> Drive]
# with three rules that the earlier version broke:
#   * nothing CPU-heavy runs on the event loop: extraction/OCR, validation and
#     embedding go to worker threads, so an upload never freezes searches;
#   * every store write is recorded on documents.index_status and the job
#     status names the stage that failed (extraction_failed, parse_failed,
#     tree_failed, embedding_failed, index_failed) — an embedding error is no
#     longer reported as a parse failure;
#   * a failed or stuck upload (server restarted mid-ingest) can be resumed from
#     its last good store: POST /jobs/{id}/retry, or simply uploading the same
#     PDF again. Finished stages are cached (uploads/{id}.txt, _sections.json,
#     the tree), so a retry repeats only what is missing.
# The case card is built here (one LLM call); if it is rate-limited the
# judgment is still searchable ("searchable"), and the card wave completes it.

# ── Several uploads at once ──────────────────────────────────────────────────
# The Cases page can send many PDFs; each is its own request and its own
# judgment. Isolation is by construction: every judgment gets a fresh uuid4
# pdf_id, and everything it writes is keyed by it (uploads/{pdf_id}.*, nodes
# with uuid4 node ids, vectors "{node_id}::{chunk}" with file_id=pdf_id,
# keyword rows deleted and re-inserted per judgment_id, the card by
# judgment_id). No stage reads another judgment's data.
#
# What concurrency does need is a bound, so the queue below:
#   * at most ADMIN_INGEST_CONCURRENCY judgments past the queue at a time
#     (extraction/OCR and the parse are the CPU- and LLM-heavy stages);
#   * the index stage (embedding, case card, keyword index, card vector) one
#     judgment at a time — the shape bulk ingest uses (its embed semaphore of
#     1), so Chroma and SQLite writes never interleave and the embedding model
#     is not shared between two judgments mid-write;
#   * two copies of the same PDF in one batch: the hash is reserved before the
#     first is saved, so the second is rejected as a duplicate instead of both
#     passing the duplicate check.
# The queue lives in this process: a server restart drops waiting uploads,
# which then show as stalled and resume with Retry (or by uploading again).

_queue_state: dict = {"loop": None}
_PENDING_HASHES: set[str] = set()


def _queue() -> dict:
    """The semaphore and locks, created on (and bound to) the running loop."""
    loop = asyncio.get_running_loop()
    if _queue_state["loop"] is not loop:
        from app.config import settings

        _queue_state.update(
            loop=loop,
            slots=asyncio.Semaphore(max(1, int(getattr(settings, "ADMIN_INGEST_CONCURRENCY", 2) or 2))),
            index=asyncio.Lock(),
            register=asyncio.Lock(),
        )
    return _queue_state


def _remove_upload_files(pdf_id: str, suffixes=(".pdf", ".txt", "_sections.json", "_summary.md")) -> None:
    for suffix in suffixes:
        f_path = UPLOADS_DIR / f"{pdf_id}{suffix}"
        if f_path.exists():
            try:
                f_path.unlink()
            except Exception:
                pass


_FAILED_JOB_STATUS = {"extract": "extraction_failed", "parse": "parse_failed",
                      "tree": "tree_failed", "dense": "embedding_failed",
                      "index": "embedding_failed", "fts": "index_failed"}


async def _job_set(pdf_id: str, **fields) -> None:
    await db.jobs.update_one({"job_id": pdf_id},
                             {"$set": {**fields, "updated_at": datetime.now(timezone.utc)}})


async def _mark_ingest_failed(pdf_id: str, stage: str, reason: str) -> None:
    from app.indexing.sync import record_index_status

    now = datetime.now(timezone.utc)
    await db.jobs.update_one({"job_id": pdf_id}, {"$set": {
        "status": _FAILED_JOB_STATUS.get(stage, f"{stage}_failed"), "error": reason,
        "failed_stage": stage, "failed_at": now, "updated_at": now}})
    await db.documents.update_one({"pdf_id": pdf_id}, {"$set": {"status": "failed"}})
    error = reason if reason.startswith(f"{stage}:") else f"{stage}: {reason}"
    await record_index_status(pdf_id, error=error, failed=True)


async def run_extraction(pdf_id: str, pdf_path: str, detected_type: str) -> None:
    """Queue one judgment, then run the whole chain for it (_run_pipeline)."""
    try:
        if db.jobs is not None:
            await _job_set(pdf_id, status="queued", queued_at=datetime.now(timezone.utc))
        async with _queue()["slots"]:
            await _run_pipeline(pdf_id, pdf_path, detected_type)
    except asyncio.CancelledError:
        # Deleted while waiting or running: leave no files behind.
        logger.warning(f"[{pdf_id}] Ingestion task was explicitly cancelled by user.")
        _remove_upload_files(pdf_id)
    finally:
        ACTIVE_INGESTION_TASKS.pop(pdf_id, None)


async def _run_pipeline(pdf_id: str, pdf_path: str, detected_type: str) -> None:
    stage = "extract"
    try:
        if db.jobs is None or db.documents is None:
            logger.error(f"[{pdf_id}] Skipping extraction: database is not connected")
            return

        async def is_cancelled() -> bool:
            if pdf_id not in ACTIVE_INGESTION_TASKS:
                return True
            job = await db.jobs.find_one({"job_id": pdf_id})
            return job is None

        if await is_cancelled():
            logger.info(f"[{pdf_id}] Ingestion cancelled before starting extraction.")
            return

        from app.indexing.sync import complete_judgment, warm_imports
        from app.ingestion.tree_builder import ensure_tree

        await warm_imports()  # no-op once torch/chromadb are loaded

        # A retry of a judgment whose tree exists resumes at the missing stores.
        has_tree = await db.database.document_trees.find_one({"pdf_id": pdf_id}, {"_id": 1})
        if has_tree:
            stage = "tree"
            logger.info(f"[{pdf_id}] Tree already built; resuming at the search stores")
            await _job_set(pdf_id, status="tree")
            await ensure_tree(pdf_id, None)
        else:
            logger.info(f"[{pdf_id}] Extraction started")
            await _job_set(pdf_id, status="extracting")
            # OCR is seconds per page of synchronous CPU: in a thread.
            text = await asyncio.to_thread(extract, pdf_path=pdf_path, pdf_id=pdf_id,
                                           detected_type=detected_type)
            if await is_cancelled():
                logger.info(f"[{pdf_id}] Ingestion cancelled after text extraction.")
                return

            now = datetime.now(timezone.utc)
            await _job_set(pdf_id, status="extracted", char_count=len(text), extracted_at=now)
            await db.documents.update_one({"pdf_id": pdf_id}, {"$set": {"status": "extracted"}})
            logger.info(f"[{pdf_id}] Extraction completed (chars={len(text)})")

            if await is_cancelled():
                logger.info(f"[{pdf_id}] Ingestion cancelled before parsing.")
                return

            stage = "parse"
            await _job_set(pdf_id, status="parsing")
            logger.info(f"[{pdf_id}] Parsing started")
            final = await asyncio.wait_for(
                parse_sections(pdf_id=pdf_id, extracted_text=text),
                timeout=600,
            )

            if await is_cancelled():
                logger.info(f"[{pdf_id}] Ingestion cancelled after parsing.")
                for suffix in ["_sections.json", "_summary.md"]:
                    f_path = UPLOADS_DIR / f"{pdf_id}{suffix}"
                    if f_path.exists():
                        f_path.unlink()
                return

            # Carry the parse-quality verdict onto both records, so a bad parse is
            # findable later by query rather than only by reading the logs.
            quality = {
                "parse_mode": final.get("parse_mode", ""),
                "confidence": float(final.get("confidence_score", 0.0) or 0.0),
                "quality_passed": bool(final.get("quality_passed", True)),
                "quality_issues": final.get("quality_issues", []),
            }
            await _job_set(pdf_id, status="parsed", parsed_at=datetime.now(timezone.utc), **quality)
            await db.documents.update_one({"pdf_id": pdf_id}, {"$set": {"status": "parsed", **quality}})
            if not quality["quality_passed"]:
                logger.warning(
                    f"[{pdf_id}] Parse flagged for review "
                    f"(confidence {quality['confidence']:.2f}): {quality['quality_issues']}"
                )
            logger.info(f"[{pdf_id}] Parsing completed")

            if await is_cancelled():
                logger.info(f"[{pdf_id}] Ingestion cancelled before building tree.")
                return

            stage = "tree"
            await _job_set(pdf_id, status="tree")
            await ensure_tree(pdf_id, final)

        if await is_cancelled():
            logger.info(f"[{pdf_id}] Ingestion cancelled before embedding generation.")
            return

        # Dense vectors (worker thread), case card (one LLM call), BM25 rows,
        # card vector; each recorded on index_status. Raises StoreError if a
        # store needed for search fails; a failed card does not fail the job.
        stage = "index"
        await _job_set(pdf_id, status="embedding")
        logger.info(f"[{pdf_id}] Tree ready. Building the search stores...")
        # One judgment at a time through the index stage (see the queue notes).
        async with _queue()["index"]:
            if await is_cancelled():
                logger.info(f"[{pdf_id}] Ingestion cancelled while waiting for the index stage.")
                return
            result = await complete_judgment(pdf_id, build_card=True)
        await _job_set(pdf_id, embedding_status="done", index_report=result.get("report", {}))
        logger.info(f"[{pdf_id}] Search stores written: {result.get('stores')}")

        if await is_cancelled():
            logger.info(f"[{pdf_id}] Ingestion cancelled before Google Drive upload.")
            return

        # The original PDF goes to Google Drive. A copy, not a search store: a
        # Drive failure leaves the judgment searchable and is recorded as such.
        stage = "drive"
        drive_fields: dict = {}
        doc = await db.documents.find_one({"pdf_id": pdf_id}, {"drive": 1})
        if (doc or {}).get("drive", {}).get("file_id"):
            drive_fields = {"drive_status": "already_uploaded"}
        else:
            try:
                from app.services.google_drive_service import google_drive_service

                job_doc = await db.jobs.find_one({"job_id": pdf_id})
                original_name = job_doc.get("filename") if job_doc else Path(pdf_path).name
                drive_res = await google_drive_service.upload_file(
                    file_path=pdf_path,
                    original_filename=original_name,
                    mime_type="application/pdf",
                )
                now = datetime.now(timezone.utc)
                await db.documents.update_one({"pdf_id": pdf_id}, {"$set": {
                    "drive": {
                        "file_id": drive_res.get("file_id"),
                        "file_name": drive_res.get("file_name", original_name),
                        "mime_type": drive_res.get("mime_type", "application/pdf"),
                        "web_view_link": drive_res.get("web_view_link"),
                        "web_content_link": drive_res.get("web_content_link"),
                        "uploaded_at": now,
                        "account": google_drive_service.target_email,
                        "status": drive_res.get("status"),
                    },
                    "completed_at": now,
                }})
                drive_fields = {"drive_file_id": drive_res.get("file_id"),
                                "drive_status": drive_res.get("status")}
            except Exception as e:  # noqa: BLE001
                logger.error(f"[{pdf_id}] Google Drive upload failed (judgment stays searchable): {e}")
                drive_fields = {"drive_status": f"failed: {e}"}

        doc = await db.documents.find_one({"pdf_id": pdf_id}, {"status": 1})
        final_status = (doc or {}).get("status") or "searchable"
        await _job_set(pdf_id, status=final_status, completed_at=datetime.now(timezone.utc), **drive_fields)
        logger.info(f"[{pdf_id}] Ingestion finished: {final_status} ({drive_fields})")

        # The judgment is indexed and its original is on Drive: drop the local
        # working copy so a deployed server does not accumulate every PDF.
        from app.indexing.sync import prune_local_copies

        await prune_local_copies(pdf_id)

    except asyncio.TimeoutError:
        error_message = "Parsing timed out after 600 seconds."
        await _mark_ingest_failed(pdf_id, "parse", error_message)
        logger.error(f"[{pdf_id}] {error_message}")
    except Exception as e:
        from app.indexing.sync import StoreError

        failed_stage = e.store if isinstance(e, StoreError) else stage
        try:
            await _mark_ingest_failed(pdf_id, failed_stage, str(e))
        except Exception as ex:  # noqa: BLE001
            logger.error(f"[{pdf_id}] could not record the failure: {ex}")
        logger.exception(f"[{pdf_id}] Ingestion failed at {failed_stage}: {e}")


def _ingestion_running(pdf_id: str) -> bool:
    task = ACTIVE_INGESTION_TASKS.get(pdf_id)
    return task is not None and not task.done()


async def _resume_point(pdf_id: str) -> str:
    """The first stage a retry will actually redo."""
    from app.indexing.check import inspect_one
    from app.indexing.sync import load_cached_parse

    state = await inspect_one(pdf_id)
    if state["tree"]:
        for store in ("dense", "fts", "card", "card_vector"):
            if not state[store]:
                return store
        return "none"
    if load_cached_parse(pdf_id) is not None:
        return "tree"
    if (UPLOADS_DIR / f"{pdf_id}.txt").exists():
        return "parse"
    return "extract"


async def _start_ingestion(pdf_id: str, reason: str) -> str:
    """(Re)launch run_extraction for an existing document. Returns the resume point.

    Raises HTTPException 409 when it is already running, 410 when the work
    cannot be resumed because the original PDF is gone.
    """
    if _ingestion_running(pdf_id):
        raise HTTPException(status_code=409, detail="This judgment is already being processed.")
    doc = await db.documents.find_one({"pdf_id": pdf_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Judgment not found.")
    resume_from = await _resume_point(pdf_id)
    pdf_path = UPLOADS_DIR / f"{pdf_id}.pdf"
    if resume_from == "extract" and not pdf_path.exists():
        raise HTTPException(status_code=410, detail="The original PDF is no longer on the server; "
                                                    "delete this record and upload the PDF again.")
    now = datetime.now(timezone.utc)
    await db.jobs.update_one({"job_id": pdf_id}, {
        "$set": {"status": "queued", "retried_at": now, "updated_at": now, "resume_from": resume_from,
                 "retry_reason": reason},
        "$unset": {"error": "", "failed_at": "", "failed_stage": ""},
        "$inc": {"retry_count": 1},
    }, upsert=False)
    if doc.get("status") == "failed":
        await db.documents.update_one({"pdf_id": pdf_id}, {"$set": {"status": "uploaded"}})
    task = asyncio.create_task(run_extraction(pdf_id, str(pdf_path), doc.get("detected_type") or "text"))
    ACTIVE_INGESTION_TASKS[pdf_id] = task
    logger.info(f"[{pdf_id}] Ingestion (re)started from '{resume_from}' ({reason})")
    return resume_from


def _uploader(name: str, admin_id: str) -> dict | None:
    """The admin who uploaded, as stored on the job/document (None if unknown).

    Sent by the admin page from the signed-in admin (auth is currently off, so
    the server cannot derive it from a token yet). Kept small: a display name
    and the admin id (usually the email), both already non-secret.
    """
    name, admin_id = (name or "").strip(), (admin_id or "").strip()
    if not name and not admin_id:
        return None
    return {"name": name, "id": admin_id}


@router.post("/upload")
async def upload_pdf(
    file: UploadFile = File(...),
    uploaded_by: str = Form(""),
    uploaded_by_id: str = Form(""),
):
    original_filename = file.filename or "uploaded.pdf"
    if not original_filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed.")

    pdf_id = str(uuid4())
    filename = original_filename
    saved_path = UPLOADS_DIR / f"{pdf_id}.pdf"

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    if not file_bytes.startswith(b"%PDF"):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed.")

    file_hash = hashlib.sha256(file_bytes).hexdigest()

    if db.jobs is None or db.documents is None:
        raise HTTPException(status_code=503, detail="Database is not connected.")

    uploader = _uploader(uploaded_by, uploaded_by_id)

    # The duplicate check and the hash reservation happen under one lock, so two
    # copies of a PDF in the same batch cannot both pass the check.
    async with _queue()["register"]:
        existing_doc = await db.documents.find_one(
            {"file_hash": file_hash},
            {"_id": 0, "pdf_id": 1, "filename": 1, "status": 1},
        )
        if existing_doc:
            return await _upload_of_known_pdf(existing_doc, file_bytes, filename, uploader)
        if file_hash in _PENDING_HASHES:
            raise HTTPException(status_code=409, detail=(
                "Duplicate PDF detected: the same file is already being uploaded in this batch."))
        _PENDING_HASHES.add(file_hash)

    try:
        return await _register_new_upload(pdf_id, filename, saved_path, file_bytes, file_hash, uploader)
    finally:
        _PENDING_HASHES.discard(file_hash)


async def _upload_of_known_pdf(existing_doc: dict, file_bytes: bytes, filename: str,
                               uploader: dict | None = None) -> dict:
    """The PDF's hash is already on record: resume it if it failed or stalled, else 409.

    Called under the registration lock, so two re-uploads of the same failed
    PDF cannot both start a task for it.
    """
    if existing_doc:
        from app.indexing.sync import IN_FLIGHT_STATUSES

        existing_id = existing_doc.get("pdf_id")
        existing_status = existing_doc.get("status")
        stuck = existing_status in IN_FLIGHT_STATUSES and not _ingestion_running(existing_id)
        if existing_id and (existing_status == "failed" or stuck):
            # The same PDF failed (or was interrupted) before: resume that
            # record instead of refusing, and instead of creating a second one.
            old_pdf = UPLOADS_DIR / f"{existing_id}.pdf"
            if not old_pdf.exists():
                await asyncio.to_thread(old_pdf.write_bytes, file_bytes)
            if uploader:
                # Record who re-uploaded, keeping the original uploader if set.
                await db.jobs.update_one({"job_id": existing_id, "uploaded_by": {"$in": [None, {}]}},
                                         {"$set": {"uploaded_by": uploader}})
                await db.documents.update_one({"pdf_id": existing_id, "uploaded_by": {"$in": [None, {}]}},
                                              {"$set": {"uploaded_by": uploader}})
            resume_from = await _start_ingestion(existing_id, reason="re-uploaded")
            return {
                "pdf_id": existing_id,
                "filename": existing_doc.get("filename", filename),
                "job_id": existing_id,
                "status": "queued",
                "resumed": True,
                "resume_from": resume_from,
                "message": f"This PDF was uploaded before and {'failed' if existing_status == 'failed' else 'was interrupted'}; "
                           f"resuming it from '{resume_from}'. Use job_id to track progress.",
            }
        if existing_id and _ingestion_running(existing_id):
            raise HTTPException(status_code=409, detail=(
                f"This PDF is already being processed as '{existing_doc.get('filename', 'unknown')}'."))
        raise HTTPException(
            status_code=409,
            detail=f"Duplicate PDF detected. Already uploaded as '{existing_doc.get('filename', 'unknown')}'"
                   f" (status: {existing_status}).",
        )


async def _register_new_upload(pdf_id: str, filename: str, saved_path: Path, file_bytes: bytes,
                               file_hash: str, uploader: dict | None = None) -> dict:
    """Save, validate and record a new PDF, then queue its ingestion."""
    job_id = pdf_id
    await asyncio.to_thread(saved_path.write_bytes, file_bytes)

    from app.ingestion.validator import validate_judgment
    # Validation OCRs page 1 of a scanned PDF: seconds of CPU, so in a thread.
    is_valid, validation_msg = await asyncio.to_thread(validate_judgment, str(saved_path))
    if not is_valid:
        if saved_path.exists():
            saved_path.unlink()
        raise HTTPException(status_code=400, detail=validation_msg)

    detected_type = await asyncio.to_thread(detect_pdf_type, str(saved_path))
    now = datetime.now(timezone.utc)

    await db.jobs.insert_one(
        {
            "job_id": job_id,
            "pdf_id": pdf_id,
            "filename": filename,
            "detected_type": detected_type,
            "status": "uploaded",
            "created_at": now,
            "updated_at": now,
            "file_hash": file_hash,
            "uploaded_by": uploader,
        }
    )

    await db.documents.insert_one(
        {
            "pdf_id": pdf_id,
            "filename": filename,
            "detected_type": detected_type,
            "status": "uploaded",
            "upload_date": now,
            "total_nodes": 0,
            "file_hash": file_hash,
            "index_status": {},
            "uploaded_by": uploader,
        }
    )
    task = asyncio.create_task(run_extraction(pdf_id, str(saved_path), detected_type))
    ACTIVE_INGESTION_TASKS[pdf_id] = task
    ACTIVE_INGESTION_TASKS[job_id] = task
    logger.info(f"[{pdf_id}] Upload saved and extraction task launched")

    return {
        "pdf_id": pdf_id,
        "filename": filename,
        "detected_type": detected_type,
        "job_id": job_id,
        "status": "uploaded",
        "message": "PDF received. Use job_id to track progress.",
    }


@router.post("/jobs/{job_id}/retry")
async def retry_job(job_id: str):
    """Resume a failed or stuck ingestion from its last good store.

    Stuck = an in-flight status with no running task (the server restarted
    mid-ingest). A "searchable" judgment can be retried too: that builds its
    missing card (one LLM call). A "complete" one has nothing to retry.
    """
    if db.jobs is None or db.documents is None:
        raise HTTPException(status_code=503, detail="Database is not connected.")
    job = await db.jobs.find_one({"$or": [{"job_id": job_id}, {"pdf_id": job_id}]})
    pdf_id = (job or {}).get("pdf_id") or job_id
    doc = await db.documents.find_one({"pdf_id": pdf_id}, {"status": 1})
    if not doc:
        raise HTTPException(status_code=404, detail="Judgment not found.")
    if _ingestion_running(pdf_id):
        raise HTTPException(status_code=409, detail="This judgment is already being processed.")
    previous = doc.get("status")
    if previous == "complete" and await _resume_point(pdf_id) == "none":
        return {"job_id": pdf_id, "pdf_id": pdf_id, "status": "complete", "resume_from": "none",
                "message": "Every store is already written; nothing to retry."}
    resume_from = await _start_ingestion(pdf_id, reason="retry")
    return {"job_id": pdf_id, "pdf_id": pdf_id, "status": "queued", "previous_status": previous,
            "resume_from": resume_from, "message": f"Resuming from '{resume_from}'."}


@router.get("/jobs/{job_id}")
async def get_job(job_id: str):
    if db.jobs is None:
        raise HTTPException(status_code=503, detail="Database is not connected.")

    job = await db.jobs.find_one({"job_id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")

    return _with_activity(job)


def _with_activity(job: dict) -> dict:
    """Mark whether a task is alive for this job (waiting in the queue or running).

    The Cases page treats a job whose status has not moved for 15 minutes as
    stalled (the server restarted mid-ingest). A judgment waiting behind a
    batch of uploads is not stalled; `active` tells the two apart.
    """
    job["active"] = _ingestion_running(job.get("pdf_id") or job.get("job_id") or "")
    return job


@router.get("/jobs")
async def list_jobs():
    if db.jobs is None:
        raise HTTPException(status_code=503, detail="Database is not connected.")

    cursor = db.jobs.find({}, {"_id": 0}).sort("created_at", -1)
    jobs = await cursor.to_list(length=None)
    return {"jobs": [_with_activity(j) for j in jobs]}


class JobLookup(BaseModel):
    job_ids: list[str]


MAX_LOOKUP_IDS = 500


@router.post("/jobs/lookup")
async def lookup_jobs(body: JobLookup):
    """The current state of the given jobs only — what a multi-file upload polls.

    GET /jobs returns every job ever uploaded (thousands at full corpus); a
    batch only needs its own few dozen, every few seconds.
    """
    if db.jobs is None:
        raise HTTPException(status_code=503, detail="Database is not connected.")
    ids = list(dict.fromkeys(i for i in body.job_ids if i))[:MAX_LOOKUP_IDS]
    if not ids:
        return {"jobs": []}
    cursor = db.jobs.find({"job_id": {"$in": ids}},
                          {"_id": 0, "job_id": 1, "pdf_id": 1, "filename": 1, "status": 1, "error": 1,
                           "failed_stage": 1, "updated_at": 1, "created_at": 1, "quality_passed": 1,
                           "uploaded_by": 1})
    return {"jobs": [_with_activity(j) async for j in cursor]}


@router.get("/extracted/{pdf_id}")
async def get_extracted(pdf_id: str):
    txt_path = UPLOADS_DIR / f"{pdf_id}.txt"
    if not txt_path.exists():
        raise HTTPException(status_code=404, detail="Extracted text not found.")

    text = txt_path.read_text(encoding="utf-8", errors="ignore")
    return {"pdf_id": pdf_id, "char_count": len(text), "preview": text[:500]}


@router.get("/parsed/{pdf_id}")
async def get_parsed(pdf_id: str):
    parsed_path = UPLOADS_DIR / f"{pdf_id}_sections.json"
    if not parsed_path.exists():
        raise HTTPException(status_code=404, detail="Parsed sections not found.")

    import json

    parsed = json.loads(parsed_path.read_text(encoding="utf-8", errors="ignore"))
    sections = []
    for section in parsed.get("sections", []):
        text = section.get("text", "") or ""
        sections.append(
            {
                "section_type": section.get("section_type"),
                "heading_found": section.get("heading_found"),
                "char_count": len(text),
                "confidence": section.get("confidence", 0.0),
                "preview": text[:300],
            }
        )

    return {
        "pdf_id": pdf_id,
        "parse_mode": parsed.get("parse_mode", "unknown"),
        "context_heading": parsed.get("context_heading", ""),
        "context_summary": parsed.get("context_summary", ""),
        "sections": sections,
    }


@router.get("/tree/{pdf_id}")
async def get_tree(pdf_id: str):
    if db.database is None:
        raise HTTPException(status_code=503, detail="Database is not connected.")

    tree = await db.database.document_trees.find_one({"pdf_id": pdf_id}, {"_id": 0})
    if not tree:
        raise HTTPException(status_code=404, detail="Tree structure not found for this PDF.")

    return tree


@router.get("/judgments/{judgment_id}/download")
async def download_judgment(judgment_id: str):
    """
    Downloads the original PDF judgment from Google Drive (or local fallback).
    Streams binary content directly with appropriate Content-Disposition header.
    """
    if db.documents is None:
        raise HTTPException(status_code=503, detail="Database is not connected.")

    # Find document in MongoDB
    doc = await db.documents.find_one({"$or": [{"pdf_id": judgment_id}, {"job_id": judgment_id}]})
    if not doc and db.jobs is not None:
        doc = await db.jobs.find_one({"$or": [{"job_id": judgment_id}, {"pdf_id": judgment_id}]})

    if not doc:
        # Fallback check if file exists on disk
        local_path = UPLOADS_DIR / f"{judgment_id}.pdf"
        if local_path.exists():
            from fastapi.responses import FileResponse
            return FileResponse(
                path=str(local_path),
                filename=f"{judgment_id}.pdf",
                media_type="application/pdf",
            )
        raise HTTPException(status_code=404, detail="Judgment not found.")

    drive_meta = doc.get("drive") if isinstance(doc.get("drive"), dict) else {}
    drive_file_id = drive_meta.get("file_id") or doc.get("drive_file_id") or f"local_{judgment_id}"
    filename = drive_meta.get("file_name") or doc.get("filename") or f"{judgment_id}.pdf"

    if not filename.lower().endswith(".pdf"):
        filename = f"{filename}.pdf"

    try:
        from app.services.google_drive_service import google_drive_service
        stream, remote_name, mime_type = await google_drive_service.download_file_stream(
            file_id=drive_file_id,
            fallback_filename=filename,
        )

        from fastapi.responses import StreamingResponse
        headers = {
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Access-Control-Expose-Headers": "Content-Disposition",
        }
        return StreamingResponse(
            stream,
            media_type=mime_type or "application/pdf",
            headers=headers,
        )
    except Exception as e:
        logger.error(f"Error downloading judgment {judgment_id}: {e}")
        local_path = UPLOADS_DIR / f"{judgment_id}.pdf"
        if local_path.exists():
            from fastapi.responses import FileResponse
            return FileResponse(
                path=str(local_path),
                filename=filename,
                media_type="application/pdf",
            )
        raise HTTPException(status_code=500, detail=f"Failed to download PDF: {str(e)}")


async def _perform_delete_job(job_id: str) -> dict:
    """Internal helper to clean up all traces of a single judgment/job."""
    # Try finding job by job_id or pdf_id
    job = await db.jobs.find_one({"$or": [{"job_id": job_id}, {"pdf_id": job_id}]})
    doc = None
    if not job:
        doc = await db.documents.find_one({"$or": [{"pdf_id": job_id}, {"job_id": job_id}]})
    else:
        doc = await db.documents.find_one({"$or": [{"pdf_id": job.get("pdf_id")}, {"job_id": job.get("job_id")}]})

    if not job and not doc:
        pdf_id = job_id
        actual_job_id = job_id
    else:
        pdf_id = (job or doc).get("pdf_id") or job_id
        actual_job_id = (job or doc).get("job_id") or job_id

    drive_file_id = None
    if doc and isinstance(doc.get("drive"), dict) and doc.get("drive", {}).get("file_id"):
        drive_file_id = doc.get("drive", {}).get("file_id")
    elif doc and doc.get("drive_file_id"):
        drive_file_id = doc.get("drive_file_id")
    elif job and isinstance(job.get("drive"), dict) and job.get("drive", {}).get("file_id"):
        drive_file_id = job.get("drive", {}).get("file_id")
    elif job and job.get("drive_file_id"):
        drive_file_id = job.get("drive_file_id")

    filename = (
        (doc.get("drive", {}).get("file_name") if (doc and isinstance(doc.get("drive"), dict)) else None)
        or (doc.get("filename") if doc else None)
        or (job.get("filename") if job else None)
        or f"{pdf_id}.pdf"
    )

    # 0. Cancel active background task immediately if running
    for key in [job_id, pdf_id, actual_job_id]:
        if key and key in ACTIVE_INGESTION_TASKS:
            t = ACTIVE_INGESTION_TASKS.pop(key, None)
            if t and not t.done():
                logger.info(f"Explicitly cancelling running extraction task for {key}")
                t.cancel()

    # Heavy modules (torch, chromadb) are imported in a thread if this process
    # has not loaded them yet, so the cleanup below never stalls the loop.
    try:
        from app.indexing.sync import warm_imports
        await warm_imports()
    except Exception as e:
        logger.warning(f"Notice while preloading index modules: {e}")

    # 1. MongoDB Collections Cleanup
    deleted_counts = {}
    try:
        res_docs = await db.documents.delete_many({"$or": [{"pdf_id": pdf_id}, {"job_id": actual_job_id}]})
        deleted_counts["documents"] = res_docs.deleted_count

        res_jobs = await db.jobs.delete_many({"$or": [{"pdf_id": pdf_id}, {"job_id": actual_job_id}]})
        deleted_counts["jobs"] = res_jobs.deleted_count

        # Cleanup nodes collection
        deleted_nodes_count = 0
        if db.nodes is not None:
            res_nodes = await db.nodes.delete_many({"$or": [{"pdf_id": pdf_id}, {"file_id": pdf_id}]})
            deleted_nodes_count += res_nodes.deleted_count
        
        if db.database is not None:
            if hasattr(db.database, "nodes"):
                res_db_nodes = await db.database.nodes.delete_many({"$or": [{"pdf_id": pdf_id}, {"file_id": pdf_id}]})
                deleted_nodes_count += res_db_nodes.deleted_count
            # Cleanup document trees collection
            res_trees = await db.database.document_trees.delete_many({"$or": [{"pdf_id": pdf_id}, {"file_id": pdf_id}]})
            deleted_counts["document_trees"] = res_trees.deleted_count
            # Cleanup embedding mappings collection
            res_mappings = await db.database.embedding_mappings.delete_many({"$or": [{"file_id": pdf_id}, {"pdf_id": pdf_id}, {"doc_id": pdf_id}]})
            deleted_counts["embedding_mappings"] = res_mappings.deleted_count
            
        deleted_counts["nodes"] = deleted_nodes_count
        logger.info(f"MongoDB records purged for {pdf_id}: {deleted_counts}")
    except Exception as e:
        logger.error(f"Error purging MongoDB collections for {pdf_id}: {e}")

    # 2. ChromaDB Vectors Cleanup (a synchronous SQLite write: in a thread)
    try:
        await asyncio.to_thread(chroma_store.delete_by_file_id, pdf_id)
        logger.info(f"ChromaDB vectors purged for file_id: {pdf_id}")
    except Exception as e:
        logger.warning(f"Notice during ChromaDB vector purge for {pdf_id}: {e}")

    # 2b. Precision-v2 stores. Without this a deleted judgment lingers in the
    # case cards, the BM25 index and the card/contextual collections, and exact
    # match or keyword search can return a case whose PDF no longer exists.
    try:
        from app.indexing.sync import unindex_judgment
        await unindex_judgment(pdf_id)
    except Exception as e:
        logger.warning(f"Notice during v2 index purge for {pdf_id}: {e}")

    # 3. Connection JSON Files Cleanup (backend/app/connection, or CONNECTION_DIR)
    try:
        from app.ingestion.embedding_pipeline import connection_dir
        conn_dir = connection_dir()
        if conn_dir.exists():
            for conn_file in list(conn_dir.glob(f"{pdf_id}_*")):
                try:
                    conn_file.unlink()
                    logger.info(f"Deleted connection file: {conn_file.name}")
                except Exception as ex:
                    logger.error(f"Error removing connection file {conn_file}: {ex}")
    except Exception as e:
        logger.error(f"Error cleaning connection files for {pdf_id}: {e}")

    # 4. Uploads Files Cleanup (backend/uploads)
    try:
        if UPLOADS_DIR.exists():
            for upload_file in list(UPLOADS_DIR.glob(f"{pdf_id}*")):
                try:
                    upload_file.unlink()
                    logger.info(f"Deleted upload file: {upload_file.name}")
                except Exception as ex:
                    logger.error(f"Error removing upload file {upload_file}: {ex}")
    except Exception as e:
        logger.error(f"Error cleaning upload files for {pdf_id}: {e}")

    # The in-memory node index must forget the judgment now, not at restart.
    try:
        from app.retrieval import index_loader
        await asyncio.to_thread(index_loader.reload_index)
    except Exception as e:
        logger.warning(f"Notice during index reload after deleting {pdf_id}: {e}")

    # 5. Google Drive File Cleanup — ONLY by the file id stored at upload.
    # There is deliberately no filename fallback: Drive names are not unique
    # (thousands of judgments, many named "judgment.pdf" or "CA_12.pdf"), and
    # delete_file_by_name permanently removed every match, i.e. other
    # judgments' PDFs. Without a stored id the Drive copy is left alone.
    drive_deleted = False
    drive_action = "none"
    try:
        if drive_file_id:
            from app.services.google_drive_service import google_drive_service
            drive_deleted = await google_drive_service.delete_file(drive_file_id)
            drive_action = "deleted_by_id" if drive_deleted else "failed"
            if drive_deleted:
                logger.info(f"Google Drive file {drive_file_id} successfully deleted from cloud storage.")
            else:
                logger.warning(f"Google Drive deletion returned False for file {drive_file_id}.")
        else:
            drive_action = "skipped_no_file_id"
            logger.info(f"No Drive file id stored for {pdf_id} ('{filename}'); Drive left untouched.")
    except Exception as ex:
        drive_action = f"error: {str(ex)}"
        logger.warning(f"Notice during Google Drive delete for {drive_file_id}: {ex}")

    return {
        "message": (
            "Judgment, node tree, Chroma vectors, and Google Drive cloud file deleted successfully."
            if drive_deleted
            else "Judgment, node tree, Chroma vectors, and local files deleted successfully."
        ),
        "job_id": actual_job_id,
        "pdf_id": pdf_id,
        "drive_deleted": drive_deleted,
        "drive_file_id": drive_file_id,
        "drive_action": drive_action,
    }


@router.delete("/jobs/{job_id}")
async def delete_job(job_id: str):
    if db.jobs is None or db.documents is None:
        raise HTTPException(status_code=503, detail="Database is not connected.")
    return await _perform_delete_job(job_id)


class BatchDeleteJobsRequest(BaseModel):
    job_ids: list[str]


@router.post("/jobs/batch-delete")
async def batch_delete_jobs(body: BatchDeleteJobsRequest):
    if db.jobs is None or db.documents is None:
        raise HTTPException(status_code=503, detail="Database is not connected.")

    job_ids = list(dict.fromkeys(j for j in body.job_ids if j))
    if not job_ids:
        return {"success": True, "deleted_count": 0, "results": []}

    results = []
    deleted_count = 0
    failed_count = 0

    for jid in job_ids:
        try:
            res = await _perform_delete_job(jid)
            results.append({"job_id": jid, "success": True, "details": res})
            deleted_count += 1
        except Exception as e:
            logger.error(f"Failed to delete job {jid} during batch delete: {e}")
            results.append({"job_id": jid, "success": False, "error": str(e)})
            failed_count += 1

    return {
        "success": True,
        "deleted_count": deleted_count,
        "failed_count": failed_count,
        "results": results,
    }


@router.get("/status")
async def admin_status():
    if db.documents is None or db.jobs is None:
        raise HTTPException(status_code=503, detail="Database is not connected.")

    total_documents = await db.documents.count_documents({})

    # "searchable" (findable, card pending) and "indexing" (tree written,
    # search stores not yet) come from app.indexing.sync's per-store status.
    statuses = ["complete", "searchable", "indexing", "parsed", "failed", "uploaded", "processing"]
    by_status = {}
    for status in statuses:
        by_status[status] = await db.documents.count_documents({"status": status})

    cursor = db.jobs.find({}, {"_id": 0}).sort("created_at", -1)
    all_jobs = [_with_activity(j) for j in await cursor.to_list(length=None)]

    return {
        "total_documents": total_documents,
        "by_status": by_status,
        "recent_jobs": all_jobs[:5],
        "all_jobs": all_jobs,
    }


# ----------------------------
# User Management Integration
# ----------------------------
from pydantic import BaseModel

class UserCreate(BaseModel):
    username: str
    email: str
    name: str
    org: str
    plan: str
    password: str
    dob: str
    gender: str = "Male"
    phone_no: str = ""
    created_at: str = None


class UserUpdate(BaseModel):
    username: str
    email: str
    name: str
    org: str
    plan: str
    password: str = ""  # blank keeps the current password
    dob: str
    gender: str = "Male"
    phone_no: str = ""


def validate_password_strength(password: str) -> None:
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters long.")
    if not re.search(r"[A-Z]", password):
        raise ValueError("Password must contain at least one capital letter.")
    if not re.search(r"[a-z]", password):
        raise ValueError("Password must contain at least one small letter.")
    if not re.search(r"\d", password):
        raise ValueError("Password must contain at least one number.")
    if not re.search(r"[!@#$%^&*()_+\[\]{}|;:',.<>?/`~\"\\-]", password):
        raise ValueError("Password must contain at least one special character.")


def validate_email_domain(email: str) -> None:
    if not email.strip().lower().endswith("@gmail.com"):
        raise ValueError("Email must be a @gmail.com domain.")


def validate_age_limit(dob_str: str, reg_date: datetime) -> None:
    try:
        dob_date = datetime.strptime(dob_str, "%Y-%m-%d")
    except ValueError:
        raise ValueError("DOB must be in YYYY-MM-DD format.")
    
    reg_date_val = reg_date.date() if isinstance(reg_date, datetime) else reg_date
    dob_date_val = dob_date.date() if isinstance(dob_date, datetime) else dob_date
    
    age = reg_date_val.year - dob_date_val.year - ((reg_date_val.month, reg_date_val.day) < (dob_date_val.month, dob_date_val.day))
    if age < 16:
        raise ValueError("User must be older than 16 years from the registration date.")


async def validate_human_name(username: str) -> bool:
    from app.ingestion.parser import call_ollama, clean_json_response
    import json
    
    base_name = re.sub(r'[\d_.-]', '', username).strip()
    if not base_name:
        return False
        
    prompt = (
        f"Answer YES or NO if the following string is a reasonable human name or is based on a human name:\n"
        f"String: {base_name}\n"
        f"If the string represents an animal (e.g. cat, dog, lion), a non-living object (e.g. table, chair, window, computer), "
        f"a general dictionary noun/verb (e.g. run, beautiful, system), or random gibberish, answer NO.\n"
        f"Format your response as a JSON object with keys:\n"
        f"{{\"is_human_name\": true/false, \"reason\": \"explanation\"}}"
    )
    system = "You are a database validator helper. Respond in JSON only."
    try:
        raw = await call_ollama(prompt, system)
        cleaned = clean_json_response(raw)
        parsed = json.loads(cleaned)
        return bool(parsed.get("is_human_name", False))
    except Exception as e:
        logger.error(f"Ollama human name validation failed: {e}")
        obvious_no = {"table", "chair", "desk", "computer", "phone", "window", "door", "car", "dog", "cat", "bird", "fish", "lion", "tiger", "cow", "sheep"}
        if base_name.lower() in obvious_no:
            return False
        return True


# Import re for regex validation
import re

from app.api.security import hash_password

# Account documents store a bcrypt hash in "password" (older ones may still
# hold plain text until their next login upgrades them). Neither ever leaves
# the server: every response below goes through _without_secrets or a
# projection that drops the field.
SECRET_FIELDS = ("password",)
NO_SECRETS = {"_id": 0, "password": 0}


def _without_secrets(doc: dict) -> dict:
    return {k: v for k, v in doc.items() if k not in SECRET_FIELDS}


def _password_hash(plain: str) -> str:
    """Validate a new password's strength and return its bcrypt hash (400 if unusable)."""
    try:
        validate_password_strength(plain)
        return hash_password(plain)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


def _password_change(plain: str) -> dict:
    """{"password": hash} for a new password, {} for a blank one (keep the current password)."""
    return {"password": _password_hash(plain)} if plain else {}

@router.get("/users")
async def get_users():
    if db.database is None:
        raise HTTPException(status_code=503, detail="Database is not connected.")
    
    cursor = db.database.users.find({}).sort("created_at", -1)
    users = []
    async for doc in cursor:
        doc["_id"] = str(doc["_id"])
        if "created_at" in doc and doc["created_at"]:
            if isinstance(doc["created_at"], datetime):
                doc["created_at"] = doc["created_at"].isoformat()
        users.append(_without_secrets(doc))

    total_users = len(users)
    pro_users = sum(1 for u in users if u.get("plan") == "Pro")
    standard_users = sum(1 for u in users if u.get("plan") == "Standard")
    
    return {
        "users": users,
        "total_users": total_users,
        "pro_users": pro_users,
        "standard_users": standard_users
    }


@router.post("/users")
async def create_user(user: UserCreate):
    if db.database is None:
        raise HTTPException(status_code=503, detail="Database is not connected.")
    
    # 1. Validate Email
    try:
        validate_email_domain(user.email)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
        
    # 2. Validate and hash the password
    password_hash = _password_hash(user.password)

    # 3. Validate DOB
    now= datetime.now(timezone.utc)
    if user.created_at:
        try:
            client_time_str = user.created_at.replace("Z", "+00:00")
            now = datetime.fromisoformat(client_time_str)
        except Exception as e:
            logger.warning(f"Failed to parse user client created_at: {user.created_at}. Error: {e}")
    
    try:
        validate_age_limit(user.dob, now)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
        
    # 4. Validate username with Ollama
    is_human = await validate_human_name(user.username)
    if not is_human:
        raise HTTPException(status_code=400, detail="Username must be a human name (non-living things, animals, etc. are not allowed).")
        
    # Check uniqueness
    existing_user = await db.database.users.find_one({
        "$or": [
            {"username": user.username},
            {"email": user.email}
        ]
    })
    if existing_user:
        if existing_user.get("username") == user.username:
            raise HTTPException(status_code=409, detail="Username is already taken.")
        else:
            raise HTTPException(status_code=409, detail="Email is already registered.")
            
    # Auto-generate next user ID
    user_ids = []
    async for doc in db.database.users.find({}, {"id": 1}):
        val = doc.get("id", "")
        if val.startswith("USr-"):
            try:
                user_ids.append(int(val.split("-")[1]))
            except Exception:
                pass
    next_num = max(user_ids) + 1 if user_ids else 1001
    user_id = f"USr-{next_num}"
    
    plan_color = "bg-[#E9C176] text-[#261900]" if user.plan == "Pro" else "bg-[#E7E8EA] text-[#44474D]"
    
    new_user = {
        "id": user_id,
        "username": user.username,
        "name": user.name,
        "email": user.email,
        "org": user.org,
        "plan": user.plan,
        "planColor": plan_color,
        "status": "Active",
        "statusColor": "bg-[#22C55E]",
        "dob": user.dob,
        "gender": user.gender,
        "password": password_hash,
        "phone_no": user.phone_no,
        "created_at": now
    }
    
    await db.database.users.insert_one(new_user)
    new_user["_id"] = str(new_user["_id"])
    new_user["created_at"] = new_user["created_at"].isoformat()
    return _without_secrets(new_user)


@router.get("/users/check-username")
async def check_username_availability(username: str):
    if db.database is None:
        raise HTTPException(status_code=503, detail="Database is not connected.")
    user = await db.database.users.find_one({"username": username})
    return {"available": user is None}


@router.get("/users/check-email")
async def check_email_availability(email: str):
    if db.database is None:
        raise HTTPException(status_code=503, detail="Database is not connected.")
    user = await db.database.users.find_one({"email": email})
    return {"available": user is None}


@router.put("/users/{user_id}")
async def update_user(user_id: str, user: UserUpdate):
    if db.database is None:
        raise HTTPException(status_code=503, detail="Database is not connected.")
        
    existing_user = await db.database.users.find_one({"id": user_id})
    if not existing_user:
        raise HTTPException(status_code=404, detail="User not found.")
        
    # 1. Validate Email
    try:
        validate_email_domain(user.email)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
        
    # 2. A new password, if one was typed (blank keeps the current one)
    password_change = _password_change(user.password)

    # 3. Validate DOB based on originalregistration date
    reg_date = existing_user.get("created_at") or datetime.now(timezone.utc)
    try:
        validate_age_limit(user.dob, reg_date)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
        
    # 4. Validate username with Ollama
    if user.username != existing_user.get("username"):
        is_human = await validate_human_name(user.username)
        if not is_human:
            raise HTTPException(status_code=400, detail="Username must be a human name (non-living things, animals, etc. are not allowed).")
            
        dup = await db.database.users.find_one({"username": user.username})
        if dup and dup.get("id") != user_id:
            raise HTTPException(status_code=409, detail="Username is already taken.")
            
    if user.email != existing_user.get("email"):
        dup = await db.database.users.find_one({"email": user.email})
        if dup and dup.get("id") != user_id:
            raise HTTPException(status_code=409, detail="Email is already registered.")
            
    plan_color = "bg-[#E9C176] text-[#261900]" if user.plan == "Pro" else "bg-[#E7E8EA] text-[#44474D]"
    
    update_doc = {
        "username": user.username,
        "name": user.name,
        "email": user.email,
        "org": user.org,
        "plan": user.plan,
        "planColor": plan_color,
        "dob": user.dob,
        "gender": user.gender,
        "phone_no": user.phone_no,
        **password_change,
    }

    await db.database.users.update_one({"id": user_id}, {"$set": update_doc})
    
    updated = await db.database.users.find_one({"id": user_id})
    updated["_id"] = str(updated["_id"])
    if "created_at" in updated and updated["created_at"]:
        if isinstance(updated["created_at"], datetime):
            updated["created_at"] = updated["created_at"].isoformat()
    return _without_secrets(updated)


@router.delete("/users/{user_id}")
async def delete_user(user_id: str):
    if db.database is None:
        raise HTTPException(status_code=503, detail="Database is not connected.")
        
    existing_user = await db.database.users.find_one({"id": user_id})
    if not existing_user:
        raise HTTPException(status_code=404, detail="User not found.")
        
    await db.database.users.delete_one({"id": user_id})
    return {"message": "User deleted successfully.", "id": user_id}

class UserPlanUpdate(BaseModel):
    plan: str

@router.put("/users/{user_id}/plan")
async def update_user_plan(user_id: str, body: UserPlanUpdate):
    if db.database is None:
        raise HTTPException(status_code=503, detail="Database is not connected.")
    
    allowed_plans = {"Standard", "Pro"}
    if body.plan not in allowed_plans:
        raise HTTPException(status_code=400, detail=f"Plan must be one of: {', '.join(allowed_plans)}")

    existing_user = await db.database.users.find_one({"id": user_id})
    if not existing_user:
        raise HTTPException(status_code=404, detail="User not found.")

    await db.database.users.update_one(
        {"id": user_id},
        {"$set": {"plan": body.plan}}
    )
    return {"message": "Plan updated successfully.", "id": user_id, "plan": body.plan}


# ----------------------------
# Support Query Management
# ----------------------------

class SupportQueryCreate(BaseModel):
    full_name: str
    email: str
    subject: str
    message: str


class SupportStatusUpdate(BaseModel):
    status: str  # "Urgent", "Pending", "Solved"


@router.post("/support")
async def create_support_query(query: SupportQueryCreate):
    if db.database is None:
        raise HTTPException(status_code=503, detail="Database is not connected.")

    # Validate email domain
    if not query.email.strip().lower().endswith("@gmail.com"):
        raise HTTPException(status_code=400, detail="Email must be a @gmail.com domain.")

    if not query.full_name.strip():
        raise HTTPException(status_code=400, detail="Full name is required.")
    if not query.subject.strip():
        raise HTTPException(status_code=400, detail="Subject is required.")
    if not query.message.strip():
        raise HTTPException(status_code=400, detail="Message is required.")

    now = datetime.now(timezone.utc)

    # Auto-generate query_id
    query_ids = []
    async for doc in db.database.support_queries.find({}, {"query_id": 1}):
        val = doc.get("query_id", "")
        if val.startswith("CQ") or val.startswith("SQ-"):
            try:
                # Handle old 'SQ-XXXX' and new 'CQXXXX'
                if val.startswith("CQ"):
                    query_ids.append(int(val[2:]))
                else:
                    query_ids.append(int(val.split("-")[1]))
            except Exception:
                pass
    next_num = max(query_ids) + 1 if query_ids else 1
    query_id = f"CQ{next_num:04d}"

    new_query = {
        "query_id": query_id,
        "full_name": query.full_name.strip(),
        "email": query.email.strip(),
        "subject": query.subject.strip(),
        "message": query.message.strip(),
        "status": "Pending",
        "created_at": now,
    }

    await db.database.support_queries.insert_one(new_query)
    new_query["_id"] = str(new_query["_id"])
    new_query["created_at"] = new_query["created_at"].isoformat()

    # Dispatch email to admin (verdictaisupport@gmail.com) and user acknowledgement
    try:
        await send_contact_notification(
            name=query.full_name.strip(),
            email=query.email.strip(),
            subject=query.subject.strip(),
            message=query.message.strip(),
            query_id=query_id
        )
    except Exception as e:
        logger.warning(f"Failed to dispatch contact notification to admin: {e}")

    try:
        await send_contact_acknowledgement(
            name=query.full_name.strip(),
            email=query.email.strip(),
            subject=query.subject.strip(),
            query_id=query_id
        )
    except Exception as e:
        logger.warning(f"Failed to dispatch contact acknowledgement to client: {e}")

    return new_query


@router.get("/support")
async def get_support_queries():
    if db.database is None:
        raise HTTPException(status_code=503, detail="Database is not connected.")

    cursor = db.database.support_queries.find({}).sort("created_at", -1)
    queries = []
    async for doc in cursor:
        doc["_id"] = str(doc["_id"])
        if "created_at" in doc and doc["created_at"]:
            if isinstance(doc["created_at"], datetime):
                # Ensure the retrieved naive UTC datetime is made timezone-aware
                # before converting to isoformat so JS parses it as UTC
                aware_dt = doc["created_at"].replace(tzinfo=timezone.utc) if doc["created_at"].tzinfo is None else doc["created_at"]
                doc["created_at"] = aware_dt.isoformat()
        queries.append(doc)

    total = len(queries)
    resolved = sum(1 for q in queries if q.get("status") == "Solved")
    pending = sum(1 for q in queries if q.get("status") == "Pending")
    urgent = sum(1 for q in queries if q.get("status") == "Urgent")

    return {
        "queries": queries,
        "total": total,
        "resolved": resolved,
        "pending": pending,
        "urgent": urgent,
    }


@router.put("/support/{query_id}/status")
async def update_support_status(query_id: str, body: SupportStatusUpdate):
    if db.database is None:
        raise HTTPException(status_code=503, detail="Database is not connected.")

    allowed = {"Urgent", "Pending", "Solved"}
    if body.status not in allowed:
        raise HTTPException(status_code=400, detail=f"Status must be one of: {', '.join(allowed)}")

    existing = await db.database.support_queries.find_one({"query_id": query_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Support query not found.")

    await db.database.support_queries.update_one(
        {"query_id": query_id},
        {"$set": {"status": body.status}},
    )

    return {"message": "Status updated.", "query_id": query_id, "status": body.status}

@router.delete("/support/{query_id}")
async def delete_support_query(query_id: str):
    if db.database is None:
        raise HTTPException(status_code=503, detail="Database is not connected.")

    existing = await db.database.support_queries.find_one({"query_id": query_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Support query not found.")

    await db.database.support_queries.delete_one({"query_id": query_id})
    return {"message": "Support query deleted successfully.", "query_id": query_id}


class AdminProfileUpdate(BaseModel):
    original_adminid: str
    adminid: str
    password: str = ""  # blank keeps the current password
    dob: str
    name: str


@router.put("/profile")
async def update_admin_profile(body: AdminProfileUpdate):
    if db.database is None:
        raise HTTPException(status_code=503, detail="Database is not connected.")
    
    # 1. Validate original admin exists
    admin = await db.database.admins.find_one({"adminid": body.original_adminid})
    if not admin:
        raise HTTPException(status_code=404, detail="Admin account not found.")

    # 2. Check for unique adminid if changed
    if body.adminid != body.original_adminid:
        dup = await db.database.admins.find_one({"adminid": body.adminid})
        if dup:
            raise HTTPException(status_code=409, detail="Admin ID is already taken by another account.")

    # 3. Validate fields are not empty
    if not body.name.strip():
        raise HTTPException(status_code=400, detail="Name cannot be empty.")
    if not body.adminid.strip():
        raise HTTPException(status_code=400, detail="Admin ID cannot be empty.")
    
    # A new password, if one was typed (blank keeps the current one)
    password_change = _password_change(body.password)

    try:
        # Validate DOB format (YYYY-MM-DD)
        datetime.strptime(body.dob, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Date of Birth must be in YYYY-MM-DD format.")

    # 4. Perform update
    await db.database.admins.update_one(
        {"adminid": body.original_adminid},
        {"$set": {
            "adminid": body.adminid.strip(),
            "dob": body.dob,
            "name": body.name.strip(),
            **password_change,
        }}
    )

    # 5. Return updated admin info
    return {
        "adminid": body.adminid.strip(),
        "name": body.name.strip(),
        "dob": body.dob,
        "role": admin.get("role", "admin"),
        "message": "Profile updated successfully."
    }


@router.get("/profile")
async def get_admin_profile(adminid: str):
    if db.database is None:
        raise HTTPException(status_code=503, detail="Database is not connected.")
    
    admin = await db.database.admins.find_one({"adminid": adminid}, NO_SECRETS)
    if not admin:
        raise HTTPException(status_code=404, detail="Admin account not found.")
        
    return admin


class AdminCreate(BaseModel):
    adminid: str
    name: str
    email: str
    role: str
    dob: str
    password: str

class AdminUpdate(BaseModel):
    adminid: str
    name: str
    email: str
    role: str
    dob: str
    password: str = ""  # blank keeps the current password

@router.get("/admins")
async def get_admins():
    if db.database is None:
        raise HTTPException(status_code=503, detail="Database is not connected.")
    
    # Check if the email field exists in any admin documents, if not set it to adminid
    await db.database.admins.update_many(
        {"email": {"$exists": False}},
        [{"$set": {"email": "$adminid"}}]
    )
    
    cursor = db.database.admins.find({}, NO_SECRETS)
    admins = await cursor.to_list(length=None)
    
    total = len(admins)
    super_admins = sum(1 for a in admins if a.get("role") == "super_admin")
    standard_admins = sum(1 for a in admins if a.get("role") == "admin")
    
    return {
        "admins": admins,
        "total": total,
        "super_admins": super_admins,
        "standard_admins": standard_admins
    }

@router.post("/admins")
async def create_admin(body: AdminCreate):
    if db.database is None:
        raise HTTPException(status_code=503, detail="Database is not connected.")
    
    adminid = body.adminid.strip()
    name = body.name.strip()
    email = body.email.strip()
    role = body.role.strip()
    dob = body.dob.strip()
    password = body.password
    
    if not adminid or not name or not email or not role or not dob or not password:
        raise HTTPException(status_code=400, detail="All fields are required.")
        
    # Check uniqueness of adminid
    existing_id = await db.database.admins.find_one({"adminid": adminid})
    if existing_id:
        raise HTTPException(status_code=409, detail="Admin ID is already registered.")
        
    # Check uniqueness of email
    existing_email = await db.database.admins.find_one({"email": email})
    if existing_email:
        raise HTTPException(status_code=409, detail="Email is already registered.")
        
    password_hash = _password_hash(password)

    try:
        # Validate date format (YYYY-MM-DD)
        datetime.strptime(dob, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Date of Birth must be in YYYY-MM-DD format.")
        
    new_admin = {
        "adminid": adminid,
        "name": name,
        "email": email,
        "role": role,
        "dob": dob,
        "password": password_hash,
        "gender": "Male"
    }
    
    await db.database.admins.insert_one(new_admin)
    return {"message": "Admin created successfully."}

@router.put("/admins/{adminid_param}")
async def update_admin(adminid_param: str, body: AdminUpdate):
    if db.database is None:
        raise HTTPException(status_code=503, detail="Database is not connected.")
        
    existing = await db.database.admins.find_one({"adminid": adminid_param})
    if not existing:
        raise HTTPException(status_code=404, detail="Admin account not found.")
        
    adminid = body.adminid.strip()
    name = body.name.strip()
    email = body.email.strip()
    role = body.role.strip()
    dob = body.dob.strip()
    password = body.password
    
    if not adminid or not name or not email or not role or not dob:
        raise HTTPException(status_code=400, detail="All fields except the password are required.")

    # If adminid is changed, check uniqueness
    if adminid != adminid_param:
        dup = await db.database.admins.find_one({"adminid": adminid})
        if dup:
            raise HTTPException(status_code=409, detail="Admin ID is already registered.")
            
    # If email is changed, check uniqueness
    if email != existing.get("email"):
        dup = await db.database.admins.find_one({"email": email})
        if dup:
            raise HTTPException(status_code=409, detail="Email is already registered.")
            
    # A new password, if one was typed (blank keeps the current one)
    password_change = _password_change(password)

    try:
        datetime.strptime(dob, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Date of Birth must be in YYYY-MM-DD format.")
        
    await db.database.admins.update_one(
        {"adminid": adminid_param},
        {"$set": {
            "adminid": adminid,
            "name": name,
            "email": email,
            "role": role,
            "dob": dob,
            **password_change,
        }}
    )
    return {"message": "Admin updated successfully."}

@router.delete("/admins/{adminid_param}")
async def delete_admin(adminid_param: str):
    if db.database is None:
        raise HTTPException(status_code=503, detail="Database is not connected.")
        
    existing = await db.database.admins.find_one({"adminid": adminid_param})
    if not existing:
        raise HTTPException(status_code=404, detail="Admin account not found.")
        
    await db.database.admins.delete_one({"adminid": adminid_param})
    return {"message": "Admin deleted successfully."}



