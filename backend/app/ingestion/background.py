"""
Keep case uploads from slowing down searches.

Uploads are processed inside the server process, next to search. Two things
made a batch of uploads expensive for the people searching:

* OCR of scanned PDFs: seconds of full CPU per page, run in a thread of the
  server, with the OCR model's memory (hundreds of MB) kept afterwards.
* The index stage: the same embedding model searches use, at full speed.

So:

* ``extract_in_background`` runs a scanned PDF's text extraction in a separate
  process at low OS priority. The operating system then gives searches the CPU
  first, and the process exits after each document, so the OCR model's memory
  is returned instead of kept. A digital PDF (a text layer, no OCR) is quick
  and stays in a thread.
* ``yield_to_searches`` makes an upload wait, before each heavy stage, while
  searches are running or queued (app/api/search_slots.py). The wait is capped
  (INGEST_YIELD_MAX_S) so a busy site still finishes its uploads.
"""

from __future__ import annotations

import asyncio
import multiprocessing
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from functools import partial

from loguru import logger

from app.config import settings

_pool: ProcessPoolExecutor | None = None


def _lower_priority() -> None:
    """Runs first in the OCR process: lowest-but-one OS priority, fewer threads."""
    try:
        import psutil
        p = psutil.Process()
        p.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS if sys.platform == "win32" else 10)
    except Exception:  # noqa: BLE001 - priority is an optimisation, never a failure
        pass
    threads = str(max(1, (os.cpu_count() or 2) // 2))
    for var in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS"):
        os.environ.setdefault(var, threads)


def _get_pool() -> ProcessPoolExecutor:
    global _pool
    if _pool is None:
        # spawn, not fork: the server has threads and torch loaded, which a
        # forked child would inherit in an unknown state. One task per process,
        # so each document's OCR memory is returned when it finishes.
        _pool = ProcessPoolExecutor(
            max_workers=max(1, int(getattr(settings, "INGEST_OCR_PROCESSES", 1) or 1)),
            mp_context=multiprocessing.get_context("spawn"),
            initializer=_lower_priority,
            max_tasks_per_child=1,
        )
    return _pool


async def extract_in_background(pdf_path: str, pdf_id: str, detected_type: str) -> str:
    from app.ingestion.extractor import extract

    if detected_type == "text":
        return await asyncio.to_thread(extract, pdf_path=pdf_path, pdf_id=pdf_id, detected_type=detected_type)
    global _pool
    loop = asyncio.get_running_loop()
    try:
        return await loop.run_in_executor(_get_pool(), partial(extract, pdf_path=pdf_path, pdf_id=pdf_id,
                                                                detected_type=detected_type))
    except BrokenProcessPool:
        # The OCR process died (out of memory, killed). Start a fresh pool next
        # time; this judgment's extraction fails and can be retried.
        _pool = None
        raise RuntimeError("The text-extraction process stopped unexpectedly (possibly out of memory).") from None


async def yield_to_searches(stage: str, pdf_id: str) -> float:
    """Wait while searches are running or queued; at most INGEST_YIELD_MAX_S. Returns seconds waited."""
    from app.api.search_slots import search_slots

    max_wait = float(getattr(settings, "INGEST_YIELD_MAX_S", 60) or 0)
    slots = search_slots()
    started = time.monotonic()
    while (slots.running or slots.waiting) and time.monotonic() - started < max_wait:
        await asyncio.sleep(0.5)
    waited = time.monotonic() - started
    if waited >= 1:
        logger.info(f"[{pdf_id}] {stage}: waited {waited:.0f}s for searches to finish")
    return waited


def shutdown() -> None:
    global _pool
    if _pool is not None:
        _pool.shutdown(wait=False, cancel_futures=True)
        _pool = None
