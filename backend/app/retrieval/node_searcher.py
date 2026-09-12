"""
Stage 2 search — section nodes within a single judgment.

STEP 4 of retrieval: Stage 1 (app.retrieval.chroma_client) narrows the corpus
to a handful of judgments; this module drills into each one and finds its most
relevant sections. No MongoDB calls, no JSON file reads.

It reuses the collection already opened by app.retrieval.chroma_client rather
than creating a second ChromaDB connection.

A note on `section_type`
------------------------
The ingestion pipeline classifies every child node as one of HEADER_CORAM,
LEGAL_ISSUES, ARGUMENTS, FACTS, ANALYSIS_RATIO or FINAL_ORDER, but it stores
that label in MongoDB (nodes.section_type) and does not currently copy it into
the ChromaDB metadata. Since this module may not touch MongoDB, section_type
is read from the Chroma metadata when present and falls back to "" when it is
not. Adding it at ingestion time populates this field with no change here.
"""

import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np
from loguru import logger

from app.retrieval.chroma_client import SECTION_LEVEL, collection

# The section labels the ingestion classifier assigns, for reference by later
# pipeline steps that want to weight or filter by section.
SECTION_TYPES = (
    "HEADER_CORAM",
    "LEGAL_ISSUES",
    "ARGUMENTS",
    "FACTS",
    "ANALYSIS_RATIO",
    "FINAL_ORDER",
)


def _section_filter(judgment_id: str) -> dict:
    """Build the compound Chroma filter for one judgment's section nodes."""
    return {
        "$and": [
            # Ingestion marks sections with level 2; there is no node_type field.
            {"level": {"$eq": SECTION_LEVEL}},
            # file_id is this project's judgment identifier.
            {"file_id": {"$eq": judgment_id}},
        ]
    }


def count_sections(judgment_id: str) -> int:
    """Count how many section embeddings exist for one judgment."""
    got = collection.get(where=_section_filter(judgment_id), include=[])
    return len(got.get("ids") or [])


def search_sections_for_judgment(
    query_vector: np.ndarray,
    judgment_id: str,
    top_k: int = 3,
) -> list[dict]:
    """Find the sections of one judgment that best match the query.

    Args:
        query_vector: The L2-normalised query embedding.
        judgment_id: The judgment to search within.
        top_k: How many sections to return at most.

    Returns:
        A list of section dicts sorted by descending score, empty if the
        judgment has no section embeddings.
    """
    available = count_sections(judgment_id)
    if available == 0:
        logger.warning(f"No section embeddings found for judgment_id={judgment_id}")
        return []

    # Chroma errors if n_results exceeds the number of matching documents.
    actual_k = min(top_k, available)

    response = collection.query(
        query_embeddings=[query_vector.tolist()],
        n_results=actual_k,
        where=_section_filter(judgment_id),
        include=["metadatas", "distances"],
    )

    ids = (response.get("ids") or [[]])[0]
    distances = (response.get("distances") or [[]])[0]
    metadatas = (response.get("metadatas") or [[]])[0]

    results: list[dict] = []
    for idx, node_id in enumerate(ids):
        meta = metadatas[idx] if idx < len(metadatas) else {}
        distance = distances[idx] if idx < len(distances) else 0.0

        results.append({
            "judgment_id": meta.get("file_id", judgment_id),
            "mongo_doc_id": meta.get("node_id", node_id),
            # Empty until ingestion copies section_type into Chroma metadata.
            "section_type": meta.get("section_type", ""),
            "heading": meta.get("heading", ""),
            # Cosine space, so similarity = 1 - distance.
            "score": float(1.0 - distance),
        })

    results.sort(key=lambda r: r["score"], reverse=True)
    return results


def search_all_judgments(
    query_vector: np.ndarray,
    judgment_ids: list[str],
    top_k_per_judgment: int = 3,
) -> dict[str, list[dict]]:
    """Run the stage 2 search across every judgment from stage 1.

    Args:
        query_vector: The L2-normalised query embedding.
        judgment_ids: The judgments returned by stage 1.
        top_k_per_judgment: How many sections to keep per judgment.

    Returns:
        A dict mapping each judgment_id to its ranked section list.
    """
    logger.info(
        f"Stage 2 search: {len(judgment_ids)} judgments, "
        f"{top_k_per_judgment} sections each"
    )

    # Sequential on purpose: Chroma queries here are fast and local, and a
    # simple loop keeps the ordering deterministic. Parallelise if it matters.
    return {
        judgment_id: search_sections_for_judgment(
            query_vector, judgment_id, top_k=top_k_per_judgment
        )
        for judgment_id in judgment_ids
    }


if __name__ == "__main__":
    from app.retrieval.chroma_client import search_judgments
    from app.retrieval.query_embedder import embed_query

    vec = embed_query("bail granted despite murder charges")

    # Take a real judgment_id from stage 1 rather than hardcoding one.
    top_judgment = search_judgments(vec, top_k=1)[0]
    judgment_id = top_judgment["judgment_id"]
    print(f"judgment_id: {judgment_id}  ({top_judgment['heading']})")
    print(f"sections available: {count_sections(judgment_id)}")

    results = search_sections_for_judgment(vec, judgment_id, top_k=3)
    for r in results:
        label = r["section_type"] or "(section_type not in chroma)"
        print(f"  {label}  score={r['score']:.4f}  {r['heading'][:45]!r}")

    assert results, "stage 2 returned nothing"
    assert results == sorted(results, key=lambda r: r["score"], reverse=True)

    # Guard check: asking for more sections than exist must not raise.
    assert len(search_sections_for_judgment(vec, judgment_id, top_k=99)) == count_sections(judgment_id)
    assert search_sections_for_judgment(vec, "does-not-exist", top_k=3) == []
    print(f"OK: {len(results)} sections ranked; over-fetch and empty guards pass.")
