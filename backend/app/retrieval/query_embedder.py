"""
Query-side embedding generation for the Legal RAG retrieval pipeline.

STEP 2 of retrieval: turns a cleaned query string into a dense vector that is
directly comparable to the document vectors written by the ingestion pipeline.

This module has ONE job. No database calls, no file I/O, no ChromaDB.

Consistency with ingestion
--------------------------
The document side (app/ingestion/embedding_pipeline.py) embeds via the
EmbeddingGenerator singleton, which reads settings.EMBEDDING_MODEL. This module
reuses that same singleton, so the model is loaded exactly once per process and
the query/document vectors can never drift apart.

Two BGE-specific details:
  * Queries get an instruction prefix; documents do not.
  * Vectors are L2-normalised. The BGE models ship a Normalize module in
    their sentence-transformers config, so the stored document vectors already
    have norm 1.0; passing normalize_embeddings=True here is the explicit,
    idempotent form of the same guarantee.
"""

import sys
from pathlib import Path

# Allow `python app/retrieval/query_embedder.py` in addition to
# `python -m app.retrieval.query_embedder` by putting the backend root
# (the parent of the `app` package) on sys.path.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np
from loguru import logger

from app.config import settings
from app.embeddings.embedding_generator import EmbeddingGenerator

# BGE models expect this instruction prefix on the QUERY side only.
QUERY_INSTRUCTION_PREFIX = "Represent this sentence for searching relevant passages: "

# Read from settings so the query side can never drift from the document side.
MODEL_NAME = settings.EMBEDDING_MODEL
EMBEDDING_DIM = settings.EMBEDDING_DIM

_generator = EmbeddingGenerator()


def embed_query(query: str) -> np.ndarray:
    """Embed a single query string into the shared retrieval vector space.

    Args:
        query: The cleaned query string produced by
            :func:`app.retrieval.query_preprocessor.preprocess`.

    Returns:
        An L2-normalised float32 vector of shape ``(384,)``.
    """
    prefixed = QUERY_INSTRUCTION_PREFIX + query

    # `.model` lazily loads (and caches) the singleton's SentenceTransformer,
    # picking cuda when available — the same instance ingestion uses.
    vector = _generator.model.encode(prefixed, normalize_embeddings=True)

    logger.debug(f"Query embedded. Shape: {vector.shape}")
    return vector


if __name__ == "__main__":
    vec = embed_query("bail granted despite murder charges")
    print(f"Shape: {vec.shape}")
    print(f"Dtype: {vec.dtype}")
    print(f"Norm:  {np.linalg.norm(vec):.4f}")

    assert vec.shape == (EMBEDDING_DIM,), f"expected ({EMBEDDING_DIM},), got {vec.shape}"
    assert np.isclose(np.linalg.norm(vec), 1.0, atol=1e-4), "query vector is not L2-normalised"
    print("OK: query vector matches the ingestion vector space.")
