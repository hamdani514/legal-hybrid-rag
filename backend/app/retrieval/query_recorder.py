"""
Persistence of query-side retrieval artefacts.

Writes one JSON file per user query into backend/app/query/, capturing the
three things produced by retrieval steps 1 and 2:

  * the original query, exactly as the user typed it
  * the preprocessed (cleaned) query plus its extracted intent
  * the embedding vector generated from the cleaned query

This mirrors the ingestion side's backend/app/connection/*_vectors.json dumps
and exists for inspection and debugging. It is a side-channel: nothing in the
retrieval path should depend on these files.
"""

import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

# Allow `python app/retrieval/query_recorder.py` in addition to
# `python -m app.retrieval.query_recorder`.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np
from loguru import logger

from app.retrieval.query_embedder import EMBEDDING_DIM, MODEL_NAME, embed_query
from app.retrieval.query_preprocessor import preprocess

# backend/app/query — sibling of the ingestion-side `connection` dump folder.
QUERY_DIR = Path(__file__).resolve().parents[1] / "query"


def _timestamped_query_id() -> str:
    """Build a sortable, collision-resistant id for a single query record."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    return f"{stamp}_{uuid.uuid4().hex[:8]}"


def record_query(
    original_query: str,
    cleaned_query: str,
    intent: dict,
    embedding: np.ndarray,
    query_id: str | None = None,
    extra: dict | None = None,
) -> Path | None:
    """Write a single query record to backend/app/query/<query_id>.json.

    Args:
        original_query: The raw query as typed by the user.
        cleaned_query: The output of the preprocessing step.
        intent: The intent dict from the preprocessing step.
        embedding: The query vector from the embedding step.
        query_id: Optional explicit id; a timestamped one is generated if omitted.
        extra: Optional extra fields merged into the record, used by later
            pipeline stages to log their own artefacts alongside the query.

    Returns:
        The path of the file written, or None if the write failed. This folder
        is diagnostic, so a failed dump is logged and swallowed rather than
        being allowed to break a live user query.
    """
    query_id = query_id or _timestamped_query_id()
    QUERY_DIR.mkdir(parents=True, exist_ok=True)

    record = {
        "query_id": query_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "original_query": original_query,
        "preprocessed_query": cleaned_query,
        "intent": intent,
        "model": MODEL_NAME,
        "embedding_dim": int(embedding.shape[0]),
        "embedding": embedding.tolist(),
    }
    if extra:
        record.update(extra)

    file_path = QUERY_DIR / f"{query_id}.json"
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(record, f, indent=2, ensure_ascii=False, default=str)
        logger.info(f"Query record written: {file_path}")
    except Exception as e:
        # A failed dump must never break retrieval — this folder is diagnostic.
        logger.error(f"Failed to write query record to {file_path}: {e}")
        return None

    return file_path


def process_and_record(query: str) -> tuple[str, dict, np.ndarray, Path | None]:
    """Run preprocessing + embedding for a query and persist the result.

    Args:
        query: The raw query as typed by the user.

    Returns:
        A ``(cleaned_query, intent, embedding, file_path)`` tuple, where
        ``file_path`` is None if the diagnostic dump could not be written.
    """
    cleaned, intent = preprocess(query)
    embedding = embed_query(cleaned)
    file_path = record_query(query, cleaned, intent, embedding)
    return cleaned, intent, embedding, file_path


if __name__ == "__main__":
    test_query = "Case where accused got bail in a murder case 2019, bail was granted"
    cleaned, intent, embedding, file_path = process_and_record(test_query)

    print(f"Original:     {test_query}")
    print(f"Preprocessed: {cleaned}")
    print(f"Intent:       {intent}")
    print(f"Embedding:    shape={embedding.shape} dtype={embedding.dtype}")
    print(f"Saved to:     {file_path}")

    assert embedding.shape == (EMBEDDING_DIM,), f"expected ({EMBEDDING_DIM},)"
    assert file_path.exists(), "query record was not written"
    print("OK: query record persisted.")
