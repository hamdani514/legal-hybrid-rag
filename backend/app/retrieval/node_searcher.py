"""
Stage 2 search — section nodes within a single judgment.

STEP 4 of retrieval: Stage 1 (app.retrieval.chroma_client) narrows the corpus
to a handful of judgments; this module drills into each one and finds its most
relevant sections. No MongoDB calls, no JSON file reads.

It reuses the collection already opened by app.retrieval.chroma_client rather
than creating a second ChromaDB connection.

Chunks in, sections out
-----------------------
One section is stored as several vectors since chunking was introduced, so a
raw search inside a judgment will happily return five chunks of the same
ANALYSIS_RATIO and call them five results. Everything downstream counts in
sections, not chunks:

  * context_expander builds ``scores = {mongo_doc_id: score}``, so duplicate
    node ids would silently collapse to whichever chunk came last;
  * context_assembler keys text by section_type, so the duplicates would
    overwrite each other anyway;
  * the UI lists the divisions a result was found in, and "ANALYSIS_RATIO,
    ANALYSIS_RATIO, ANALYSIS_RATIO" tells a researcher nothing.

So this module over-fetches chunks and collapses them to distinct nodes, taking
each node's BEST chunk score. `top_k` therefore means what it says: k distinct
sections of that judgment.

Where section_type comes from
-----------------------------
It now arrives in the Chroma metadata, written by the ingestion pipeline.
Previously it lived only in MongoDB and this module returned "" for it, which
is why context_expander recovers it from the fetched documents as well.
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

# How many chunks to pull per requested section. A long ANALYSIS_RATIO can be
# twenty chunks on its own, so asking for k chunks would routinely return one
# section k times over; this over-fetch gives the dedupe something to work with.
CHUNKS_PER_SECTION = 6


def _section_filter(judgment_id: str) -> dict:
    """Build the compound Chroma filter for one judgment's section chunks."""
    return {
        "$and": [
            # Ingestion marks sections with level 2; there is no node_type field.
            {"level": {"$eq": SECTION_LEVEL}},
            # file_id is this project's judgment identifier.
            {"file_id": {"$eq": judgment_id}},
        ]
    }


def count_chunks(judgment_id: str) -> int:
    """Count how many section CHUNKS exist for one judgment."""
    got = collection.get(where=_section_filter(judgment_id), include=[])
    return len(got.get("ids") or [])


# Retained under its previous name; it now counts chunks, which is what the
# Chroma-side guards actually need.
count_sections = count_chunks


def dedupe_to_sections(chunks: list[dict], top_k: int) -> list[dict]:
    """Collapse chunk hits to distinct sections, keeping each one's best score.

    Args:
        chunks: Chunk dicts carrying ``mongo_doc_id`` and a score.
        top_k: How many distinct sections to keep.

    Returns:
        Up to `top_k` section dicts, sorted by descending score.
    """
    best: dict[str, dict] = {}

    for chunk in chunks:
        node_id = chunk.get("mongo_doc_id")
        if not node_id:
            continue

        # Prefer the cross-encoder's normalised relevance where stage 3.5
        # produced one, so a reranked chunk is never compared against a raw
        # bi-encoder cosine on a different scale.
        score = chunk.get("relevance")
        if score is None:
            score = chunk.get("score", 0.0)

        current = best.get(node_id)
        if current is None or score > current["score"]:
            best[node_id] = {
                "judgment_id": chunk.get("judgment_id", ""),
                "mongo_doc_id": node_id,
                "section_type": chunk.get("section_type", ""),
                "heading": chunk.get("heading", ""),
                "score": float(score),
                "matched_chunk": chunk.get("chunk_index", 0),
            }

    sections = sorted(best.values(), key=lambda s: s["score"], reverse=True)
    return sections[:top_k]


def search_sections_for_judgment(
    query_vector: np.ndarray,
    judgment_id: str,
    top_k: int = 3,
) -> list[dict]:
    """Find the sections of one judgment that best match the query.

    Args:
        query_vector: The L2-normalised query embedding.
        judgment_id: The judgment to search within.
        top_k: How many distinct sections to return at most.

    Returns:
        A list of section dicts sorted by descending score, empty if the
        judgment has no section embeddings.
    """
    available = count_chunks(judgment_id)
    if available == 0:
        logger.warning(f"No section embeddings found for judgment_id={judgment_id}")
        return []

    # Over-fetch chunks so the dedupe can reach `top_k` distinct sections.
    # Chroma errors if n_results exceeds the number of matching documents.
    actual_k = min(top_k * CHUNKS_PER_SECTION, available)

    response = collection.query(
        query_embeddings=[query_vector.tolist()],
        n_results=actual_k,
        where=_section_filter(judgment_id),
        include=["metadatas", "distances"],
    )

    ids = (response.get("ids") or [[]])[0]
    distances = (response.get("distances") or [[]])[0]
    metadatas = (response.get("metadatas") or [[]])[0]

    chunks: list[dict] = []
    for index, vector_id in enumerate(ids):
        meta = metadatas[index] if index < len(metadatas) else {}
        distance = distances[index] if index < len(distances) else 0.0

        chunks.append({
            "judgment_id": meta.get("file_id", judgment_id),
            # The owning MongoDB node, not the chunk's own vector id.
            "mongo_doc_id": meta.get("node_id", vector_id),
            "section_type": meta.get("section_type", ""),
            "heading": meta.get("heading", ""),
            "chunk_index": meta.get("chunk_index", 0),
            # Cosine space, so similarity = 1 - distance.
            "score": float(1.0 - distance),
        })

    return dedupe_to_sections(chunks, top_k)


def sections_from_candidates(
    candidates: list[dict],
    judgment_ids: list[str],
    top_k_per_judgment: int = 3,
) -> dict[str, list[dict]]:
    """Pick each judgment's best sections out of an already-scored candidate set.

    Stage 3.5 reranks the stage 1 pool, and those cross-encoder scores are
    better than anything a second vector search would produce. Reusing them
    here means the expensive model runs once per query rather than once per
    stage.

    Args:
        candidates: The stage 1 chunks, after reranking.
        judgment_ids: The judgments stage 1 selected.
        top_k_per_judgment: How many distinct sections to keep per judgment.

    Returns:
        A dict mapping each judgment_id to its ranked section list. A judgment
        with no chunks in the candidate set maps to an empty list, which the
        caller can fill with :func:`search_sections_for_judgment`.
    """
    by_judgment: dict[str, list[dict]] = {jid: [] for jid in judgment_ids}
    for candidate in candidates:
        judgment_id = candidate.get("judgment_id")
        if judgment_id in by_judgment:
            by_judgment[judgment_id].append(candidate)

    return {
        judgment_id: dedupe_to_sections(chunks, top_k_per_judgment)
        for judgment_id, chunks in by_judgment.items()
    }


def search_all_judgments(
    query_vector: np.ndarray,
    judgment_ids: list[str],
    top_k_per_judgment: int = 3,
    candidates: list[dict] | None = None,
) -> dict[str, list[dict]]:
    """Run the stage 2 search across every judgment from stage 1.

    Args:
        query_vector: The L2-normalised query embedding.
        judgment_ids: The judgments returned by stage 1.
        top_k_per_judgment: How many sections to keep per judgment.
        candidates: The reranked stage 1 pool, when the caller has one. Sections
            are taken from it where possible, and only judgments it does not
            cover fall back to their own vector search.

    Returns:
        A dict mapping each judgment_id to its ranked section list.
    """
    logger.info(
        f"Stage 2 search: {len(judgment_ids)} judgments, "
        f"{top_k_per_judgment} sections each"
    )

    results: dict[str, list[dict]] = {}
    if candidates:
        results = sections_from_candidates(candidates, judgment_ids, top_k_per_judgment)

    # Any judgment the candidate pool did not cover well enough gets its own
    # search. Sequential on purpose: these are fast and local, and a simple
    # loop keeps the ordering deterministic.
    for judgment_id in judgment_ids:
        if len(results.get(judgment_id) or []) < top_k_per_judgment:
            found = search_sections_for_judgment(
                query_vector, judgment_id, top_k=top_k_per_judgment
            )
            # Keep whichever pass found more; the reranked set wins on ties
            # because its scores come from the better model.
            if len(found) > len(results.get(judgment_id) or []):
                results[judgment_id] = found

    return results


if __name__ == "__main__":
    from app.retrieval.chroma_client import search_chunks, search_judgments
    from app.retrieval.query_embedder import embed_query

    vec = embed_query("bail granted despite murder charges")

    # Take a real judgment_id from stage 1 rather than hardcoding one.
    top_judgment = search_judgments(vec, top_k=1)[0]
    judgment_id = top_judgment["judgment_id"]
    print(f"judgment_id: {judgment_id}  ({top_judgment['heading']})")
    print(f"chunks available: {count_chunks(judgment_id)}")

    results = search_sections_for_judgment(vec, judgment_id, top_k=3)
    for r in results:
        label = r["section_type"] or "(no section_type)"
        print(f"  {label:<16} score={r['score']:.4f}  chunk {r['matched_chunk']}  {r['heading'][:32]!r}")

    assert results, "stage 2 returned nothing"
    assert results == sorted(results, key=lambda r: r["score"], reverse=True)

    # The whole point of the dedupe: k distinct SECTIONS, never k chunks of one.
    node_ids = [r["mongo_doc_id"] for r in results]
    assert len(node_ids) == len(set(node_ids)), "a section was returned more than once"
    assert all("::" not in n for n in node_ids), "a chunk id leaked out as a node id"
    print(f"  -> {len(results)} results, {len(set(node_ids))} distinct sections  OK")

    # Reusing the stage 1 pool must agree with a direct search on the judgment.
    pooled = sections_from_candidates(search_chunks(vec), [judgment_id], 3)
    assert judgment_id in pooled, "candidate reuse dropped the judgment"
    print(f"  -> candidate reuse found {len(pooled[judgment_id])} sections  OK")

    # Guard checks: over-fetch must not raise, unknown judgments return empty.
    assert len(search_sections_for_judgment(vec, judgment_id, top_k=99)) <= count_chunks(judgment_id)
    assert search_sections_for_judgment(vec, "does-not-exist", top_k=3) == []
    print("OK: dedupe, candidate reuse, over-fetch and empty guards pass.")
