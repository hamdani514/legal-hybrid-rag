"""
Can search actually run right now?

Search needs two models (the embedding model and the reranker) and two
indexes (ChromaDB vectors and the SQLite keyword index). Each part used to fail
quietly: a model that could not load made its retriever return nothing, so a
server whose models had not downloaded answered every search "No relevant case
is available", reported itself healthy, and still counted the search against
the user's daily limit.

Now:
* ``problems()`` lists what is missing ([] when search is ready).
* The search routes call ``ensure_ready()`` BEFORE counting the search; when
  something is missing the user is told search is temporarily unavailable
  (503), and nothing is counted.
* ``/api/health`` reports the same, with 503 until search is ready, so a host
  or orchestrator sees a broken server instead of a green one.

Once everything has loaded the answer is cached: models stay in memory. While
something is missing, loading is retried at most once per RETRY_S, so a broken
server does not try (and log) a failed load on every request.
"""

from __future__ import annotations

import asyncio
import threading
import time
from pathlib import Path

from fastapi import HTTPException
from loguru import logger

from app.config import settings

RETRY_S = 60.0
UNAVAILABLE_MESSAGE = ("Search is temporarily unavailable while the server finishes starting. "
                       "Please try again in a minute. This search was not counted.")

_lock = threading.Lock()
_ready = False
_problems: list[str] = ["not checked yet"]
_last_attempt = 0.0


def _check() -> list[str]:
    """Load what is missing and list what still is. Slow on first call; run in a thread."""
    found: list[str] = []

    try:
        from app.embeddings.embedding_generator import EmbeddingGenerator
        EmbeddingGenerator().model.encode("readiness", normalize_embeddings=True)
    except Exception as e:  # noqa: BLE001
        found.append(f"embedding model {settings.EMBEDDING_MODEL!r} could not load ({_short(e)})")

    if getattr(settings, "RERANK_ENABLED", True):
        try:
            from app.retrieval import reranker as rr
            r = rr.Reranker()
            r._unavailable = False  # the reranker latches a failed load; allow this retry
            if getattr(rr, "_onnx", None) is not None and rr.backend() == "onnx":
                rr._onnx._unavailable = False
            if r.score("readiness", ["readiness"]) is None:
                found.append(f"reranker {settings.RERANKER_MODEL!r} could not load")
        except Exception as e:  # noqa: BLE001
            found.append(f"reranker could not load ({_short(e)})")

    try:
        from app.retrieval.chroma_client import collection
        if collection is None or collection.count() == 0:
            found.append("the vector index (chroma_db) is missing or empty")
    except Exception as e:  # noqa: BLE001
        found.append(f"the vector index (chroma_db) could not be opened ({_short(e)})")

    try:
        from app.indexing import fts_index
        path = Path(fts_index.db_path())
        if not path.exists() or path.stat().st_size == 0:
            found.append(f"the keyword index ({path.name}) is missing")
        else:
            conn = fts_index.connect(path)
            try:
                conn.execute("SELECT 1 FROM chunks_fts LIMIT 1").fetchall()
            finally:
                conn.close()
    except Exception as e:  # noqa: BLE001
        found.append(f"the keyword index could not be opened ({_short(e)})")

    return found


def _short(error: Exception) -> str:
    return str(error).splitlines()[0][:160] if str(error) else type(error).__name__


def check_now(force: bool = False) -> list[str]:
    """Synchronous: [] when ready. Retries a failed check at most once per RETRY_S."""
    global _ready, _problems, _last_attempt
    if _ready:
        return []
    with _lock:
        if _ready:
            return []
        if not force and _last_attempt and time.monotonic() - _last_attempt < RETRY_S:
            return list(_problems)
        _last_attempt = time.monotonic()
        started = time.perf_counter()
        found = _check()
        _problems = found
        _ready = not found
        if _ready:
            logger.info(f"Search is ready ({time.perf_counter() - started:.1f}s to check and load).")
        else:
            logger.error("Search is NOT ready: " + "; ".join(found))
        return list(found)


async def problems() -> list[str]:
    if _ready:
        return []
    return await asyncio.to_thread(check_now)


def is_ready() -> bool:
    return _ready


async def ensure_ready() -> None:
    """503 (not counted) when search cannot run; call before the plan check."""
    missing = await problems()
    if missing:
        raise HTTPException(status_code=503, detail=UNAVAILABLE_MESSAGE, headers={"Retry-After": str(int(RETRY_S))})


def reset_for_tests() -> None:
    global _ready, _problems, _last_attempt
    with _lock:
        _ready, _problems, _last_attempt = False, ["not checked yet"], 0.0
