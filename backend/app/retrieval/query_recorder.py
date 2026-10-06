"""
Persistence of query-side retrieval artefacts.

Writes one JSON file per user query into backend/app/query/. The folder is the
only record of how users actually ask (the evaluation's real-query labelling
reads ``original_query`` from it), and a side-channel for debugging: nothing in
the retrieval path depends on these files.

Why it changed
--------------
The original recorder wrote every query's 768-float embedding plus the full
expanded and assembled contexts of every result: ~94 KB per query, 490 files
and 46 MB at the time of the multi-user audit, unbounded, and serialised with
a synchronous ``json.dump`` on the event loop — every search stalled every
other request while its record was written.

Now:

* ``QUERY_RECORDER_ENABLED`` turns recording off entirely.
* ``QUERY_RECORDER_SLIM`` (default) keeps what the record is for — the query,
  its intent, the pipeline, the returned judgment ids and scores, the timings
  and answer statuses — and drops the embedding vector and the full contexts
  (a slim record is ~2-4 KB). The full form is still available for a
  debugging session.
* ``record_query_async`` writes in a worker thread, fire-and-forget, so the
  search response never waits for the disk.
* ``QUERY_RECORDER_MAX_FILES`` caps the folder: when a write takes it over the
  cap, the oldest *slim* records (marked ``"slim": true``) are removed. Records
  written by the old full recorder are never deleted here — the evaluation and
  the owner use them — so the cap bounds growth from now on.
* An optional ``user_id`` is stored once authentication supplies one.
"""

import asyncio
import json
import sys
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

# Allow `python app/retrieval/query_recorder.py` in addition to
# `python -m app.retrieval.query_recorder`.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from loguru import logger

from app.config import settings

# backend/app/query — sibling of the ingestion-side `connection` dump folder.
QUERY_DIR = Path(__file__).resolve().parents[1] / "query"

DEFAULT_MAX_FILES = 5000

# Keys of a pipeline record that hold bulk (contexts, per-section payloads,
# the answer text);
# a slim record leaves them out.
BULKY_KEYS = ("stage2_sections", "expanded_context", "assembled_contexts", "embedding", "answer")

# Fields of each stage-1 judgment worth keeping in a slim record.
SLIM_JUDGMENT_FIELDS = ("judgment_id", "score", "confidence")

# Strong references to in-flight background writes (asyncio keeps only weak ones).
_pending: set[asyncio.Task] = set()
_prune_lock = threading.Lock()


def _timestamped_query_id() -> str:
    """Build a sortable, collision-resistant id for a single query record."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    return f"{stamp}_{uuid.uuid4().hex[:8]}"


def is_enabled() -> bool:
    return bool(getattr(settings, "QUERY_RECORDER_ENABLED", True))


def is_slim() -> bool:
    return bool(getattr(settings, "QUERY_RECORDER_SLIM", True))


def _max_files() -> int:
    """QUERY_RECORDER_MAX_FILES (proposed key); 0 disables the cap."""
    return int(getattr(settings, "QUERY_RECORDER_MAX_FILES", DEFAULT_MAX_FILES) or 0)


def _slim_extra(extra: dict) -> dict:
    """Drop bulky payloads; shrink the judgment list to ids, scores, labels."""
    slim = {k: v for k, v in extra.items() if k not in BULKY_KEYS}
    if isinstance(slim.get("stage1_judgments"), list):
        slim["stage1_judgments"] = [
            {f: j.get(f) for f in SLIM_JUDGMENT_FIELDS if f in j}
            for j in slim["stage1_judgments"] if isinstance(j, dict)
        ]
    return slim


def _prune(directory: Path, max_files: int) -> int:
    """Remove the oldest slim records beyond ``max_files``. Returns how many."""
    if max_files <= 0:
        return 0
    with _prune_lock:
        files = sorted(directory.glob("*.json"))  # ids start with a UTC timestamp
        excess = len(files) - max_files
        removed = 0
        for path in files:
            if removed >= excess:
                break
            try:
                with open(path, encoding="utf-8") as f:
                    head = f.read(512)
                if '"slim": true' not in head:
                    continue  # a full legacy record: never deleted here
                path.unlink()
                removed += 1
            except OSError:
                continue
        return removed


def record_query(
    original_query: str,
    cleaned_query: str,
    intent: dict,
    embedding=None,
    query_id: str | None = None,
    extra: dict | None = None,
    user_id: str | None = None,
) -> Path | None:
    """Write a single query record to backend/app/query/<query_id>.json (blocking).

    Args:
        original_query: The raw query as typed by the user.
        cleaned_query: The output of the preprocessing step.
        intent: The intent dict from the preprocessing step.
        embedding: The query vector, if one was computed. Stored only in the
            full (non-slim) form.
        query_id: Optional explicit id; a timestamped one is generated if omitted.
        extra: Optional extra fields merged into the record, used by later
            pipeline stages to log their own artefacts alongside the query.
        user_id: The authenticated user, when there is one.

    Returns:
        The path written, or None when recording is off or the write failed.
        This folder is diagnostic, so a failed dump is logged and swallowed
        rather than being allowed to break a live user query.
    """
    if not is_enabled():
        return None

    slim = is_slim()
    query_id = query_id or _timestamped_query_id()
    directory = QUERY_DIR

    # "slim" is written first so pruning can recognise a slim record from the
    # first few hundred bytes without parsing the file.
    record: dict = {"slim": slim, "query_id": query_id,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "original_query": original_query, "preprocessed_query": cleaned_query,
                    "intent": intent, "model": settings.EMBEDDING_MODEL}
    if user_id:
        record["user_id"] = user_id
    if not slim and embedding is not None:
        record["embedding_dim"] = int(len(embedding))
        record["embedding"] = [float(x) for x in embedding]
    if extra:
        record.update(_slim_extra(extra) if slim else extra)

    file_path = directory / f"{query_id}.json"
    try:
        directory.mkdir(parents=True, exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(record, f, indent=None if slim else 2, ensure_ascii=False, default=str)
        logger.debug(f"Query record written: {file_path}")
    except Exception as e:
        logger.error(f"Failed to write query record to {file_path}: {e}")
        return None

    if slim:
        max_files = _max_files()
        try:
            removed = _prune(directory, max_files)
            if removed:
                logger.info(f"Query log over {max_files} files; removed {removed} oldest slim record(s)")
        except Exception as e:
            logger.warning(f"Query log pruning failed: {e}")
    return file_path


def record_query_async(*args, **kwargs) -> asyncio.Task | None:
    """Schedule :func:`record_query` in a worker thread; never blocks the event loop.

    Must be called from a running event loop. Returns the task (callers do not
    need to await it) or None when recording is off.
    """
    if not is_enabled():
        return None
    task = asyncio.get_running_loop().create_task(asyncio.to_thread(record_query, *args, **kwargs))
    _pending.add(task)
    task.add_done_callback(_pending.discard)
    return task


if __name__ == "__main__":
    import tempfile

    import numpy as np

    async def main() -> None:
        global QUERY_DIR
        original_dir = QUERY_DIR
        with tempfile.TemporaryDirectory() as tmp:
            QUERY_DIR = Path(tmp)
            extra = {
                "pipeline": "v2", "mode": "answer",
                "stage1_judgments": [{"judgment_id": "j1", "score": 0.9, "confidence": "high",
                                      "mongo_doc_id": "x", "heading": "long heading"}],
                "expanded_context": [{"text": "x" * 50_000}],
                "assembled_contexts": [{"context": "y" * 50_000}],
                "stage2_sections": {"j1": [{"text": "z" * 10_000}]},
                "timings_ms": {"embed": 12.0},
            }
            vec = np.ones(768, dtype=np.float32)

            # Slim (default): no vector, no contexts, written off the loop.
            settings.QUERY_RECORDER_SLIM = True
            task = record_query_async("raw q", "clean q", {"k": 1}, vec, extra=extra, user_id="u42")
            path = await task  # type: ignore[misc]
            data = json.loads(path.read_text(encoding="utf-8"))
            assert data["slim"] is True and data["user_id"] == "u42"
            assert data["original_query"] == "raw q" and data["pipeline"] == "v2"
            assert "embedding" not in data and not any(k in data for k in BULKY_KEYS)
            assert data["stage1_judgments"] == [{"judgment_id": "j1", "score": 0.9, "confidence": "high"}]
            size = path.stat().st_size
            assert size < 4096, size

            # Full form still available.
            settings.QUERY_RECORDER_SLIM = False
            full = record_query("raw q", "clean q", {}, vec, extra=extra)
            full_data = json.loads(full.read_text(encoding="utf-8"))
            assert full_data["slim"] is False and len(full_data["embedding"]) == 768
            assert "assembled_contexts" in full_data
            settings.QUERY_RECORDER_SLIM = True

            # Cap: slim records beyond the cap are pruned; the full one survives.
            globals()["_max_files"] = lambda: 5
            for i in range(8):
                record_query(f"q{i}", f"q{i}", {}, query_id=f"20990101T0000{i:02d}_slim")
            files = sorted(QUERY_DIR.glob("*.json"))
            assert len(files) == 5, [f.name for f in files]
            assert full in files, "a full record was pruned"

            # Disabled: nothing written.
            settings.QUERY_RECORDER_ENABLED = False
            assert record_query("q", "q", {}) is None and record_query_async("q", "q", {}) is None
            settings.QUERY_RECORDER_ENABLED = True
            print(f"OK: slim record {size} B (full {full.stat().st_size} B), cap honoured, "
                  f"full records kept, disabled writes nothing.")
        QUERY_DIR = original_dir

    asyncio.run(main())
