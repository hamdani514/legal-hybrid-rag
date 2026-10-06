"""
ChromaDB access for the retrieval pipeline — Stage 1 search (chunk level).

STEP 3 of retrieval: takes a query vector and returns the chunk candidates most
relevant to it, plus the grouping that turns those chunks into a judgment
ranking. No MongoDB calls, no JSON file reads.

How a judgment is scored
------------------------
A judgment's relevance is the score of its single best-matching chunk, not the
score of its root summary. This matters: the ingestion pipeline generates each
root node's context_summary from a template, so those summaries are nearly
identical across judgments apart from party names —

    "Appeal by X against Y regarding the legal dispute. The Supreme Court held
     that the Court interpreted the relevant statutory provisions and rules."

— which carries no subject matter to match a query against. Measured on a
17-query labelled set over 9 judgments, ranking by root summary gave 29.4%
precision@1; ranking by best section gave 94.1% on the identical embeddings and
queries. Every result still identifies its judgment by the root node, so the
two-stage structure is unchanged: stage 1 picks judgments, stage 2 (see
app.retrieval.node_searcher) picks sections within them.

Why the candidate pool is sized, not fixed
------------------------------------------
This used to pull a flat 100 candidates. Against 66 section vectors that is the
entire corpus, so every query was an exhaustive scan followed by a re-rank —
which is precisely why precision measured so well, and precisely why it would
not have survived growth. At a thousand judgments the same 100 would have seen
under 2% of the index, and the five judgments returned would have been drawn
from whatever the ANN happened to surface first.

The pool is therefore a fraction of the collection, floored so small corpora
still get an exhaustive scan and capped so large ones stay fast. A chunk-level
index is several times larger than the old section-level one, so the floor is
also what stops a judgment's own chunks crowding out every other case.

Chunking
--------
One MongoDB node is stored as one or more vectors, id "{node_id}::{chunk}". The
`node_id` metadata field always holds the real node id, so callers group and
resolve by node without knowing chunking exists.
"""

import sys
from pathlib import Path

# Allow `python app/retrieval/chroma_client.py` as well as
# `python -m app.retrieval.chroma_client`.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np
from loguru import logger

from app.config import settings
from app.vectorstore.chroma_store import chroma_store

# Ingestion writes level 1 for root/parent nodes and level 2 for sections.
ROOT_LEVEL = 1
SECTION_LEVEL = 2

# The candidate pool, as a fraction of the section index with a floor and a cap.
#
# FLOOR keeps small corpora exhaustive (today's 66 vectors are all seen, so the
# current precision figures do not regress). FRACTION lets the pool grow with
# the corpus. CAP bounds the cost of the reranking stage that follows.
POOL_FRACTION = 0.05
POOL_FLOOR = 200
POOL_CAP = 1500

collection = chroma_store.collection

logger.info(
    f"ChromaDB connected. Collection: {collection.name}. "
    f"Total embeddings: {collection.count()}"
)

# Root metadata is one row per judgment and changes only on re-ingest, so it is
# cached and invalidated on collection size rather than re-read every query.
_roots_cache: dict[str, dict] = {}
_roots_cache_count: int = -1


def _root_nodes_by_judgment() -> dict[str, dict]:
    """Map each judgment id to its root node's id and heading.

    Cached against the collection count, so a re-ingest is picked up without a
    restart while a steady-state query does no metadata scan at all.
    """
    global _roots_cache, _roots_cache_count

    count = collection.count()
    if count == _roots_cache_count and _roots_cache:
        return _roots_cache

    got = collection.get(where={"level": {"$eq": ROOT_LEVEL}}, include=["metadatas"])
    roots: dict[str, dict] = {}
    for node_id, meta in zip(got.get("ids") or [], got.get("metadatas") or []):
        roots[meta.get("file_id", "")] = {
            "node_id": meta.get("node_id", node_id),
            "heading": meta.get("heading", ""),
        }

    _roots_cache, _roots_cache_count = roots, count
    logger.debug(f"Root node cache rebuilt: {len(roots)} judgments")
    return roots


def candidate_pool_size() -> int:
    """How many chunks stage 1 should pull, given the current corpus size."""
    total = collection.count()
    return int(min(max(total * POOL_FRACTION, POOL_FLOOR), POOL_CAP))


def search_chunks(query_vector: np.ndarray, pool: int | None = None) -> list[dict]:
    """Stage 1 search: the most relevant section chunks across the corpus.

    Args:
        query_vector: The L2-normalised query embedding from
            :func:`app.retrieval.query_embedder.embed_query`.
        pool: How many candidates to pull. Defaults to
            :func:`candidate_pool_size`.

    Returns:
        Chunk dicts holding ``judgment_id``, ``mongo_doc_id`` (the owning
        node), ``section_type``, ``heading``, ``text`` and ``score``, sorted by
        descending score. ``text`` is present so the reranker can read the
        passage without a second lookup.
    """
    pool = pool or candidate_pool_size()

    response = collection.query(
        query_embeddings=[query_vector.tolist()],
        n_results=pool,
        where={"level": {"$eq": SECTION_LEVEL}},
        # Documents are included so stage 3.5 can rerank without re-fetching.
        include=["metadatas", "distances", "documents"],
    )

    # Chroma nests one list per submitted query vector; we only sent one.
    ids = (response.get("ids") or [[]])[0]
    distances = (response.get("distances") or [[]])[0]
    metadatas = (response.get("metadatas") or [[]])[0]
    documents = (response.get("documents") or [[]])[0]

    candidates: list[dict] = []
    for index, vector_id in enumerate(ids):
        meta = metadatas[index] if index < len(metadatas) else {}
        judgment_id = meta.get("file_id", "")
        if not judgment_id:
            continue

        candidates.append({
            "judgment_id": judgment_id,
            # The MongoDB node this chunk belongs to, not the chunk itself.
            "mongo_doc_id": meta.get("node_id", vector_id),
            "vector_id": vector_id,
            "section_type": meta.get("section_type", ""),
            "heading": meta.get("heading", ""),
            "chunk_index": meta.get("chunk_index", 0),
            "text": documents[index] if index < len(documents) else "",
            # The collection uses cosine space, so similarity = 1 - distance.
            "score": float(1.0 - (distances[index] if index < len(distances) else 0.0)),
        })

    logger.info(f"Stage 1 search: {len(candidates)} chunk candidates (pool {pool})")
    return candidates


def rank_judgments(
    candidates: list[dict],
    top_k: int = 5,
    score_key: str = "score",
    threshold: float | None = None,
) -> list[dict]:
    """Group chunk candidates into a judgment ranking.

    Args:
        candidates: Chunks from :func:`search_chunks`, optionally reranked.
        top_k: How many judgments to return.
        score_key: Which score to rank on — ``"score"`` for bi-encoder order,
            ``"relevance"`` once stage 3.5 has run.
        threshold: Drop judgments scoring below this. Only meaningful on an
            absolute scale, so it applies to ``"relevance"`` and is ignored for
            raw cosine, which has no calibrated floor. None uses the configured
            RELEVANCE_THRESHOLD.

    Returns:
        A list of dicts sorted by descending score, each holding
        ``judgment_id``, ``mongo_doc_id`` (the root node, for context
        expansion), ``heading`` (the case title) and ``score``. Returns an
        EMPTY list when nothing clears the floor — the corpus is small, most
        questions have no answer in it, and saying so is the correct result.
    """
    best: dict[str, float] = {}
    for candidate in candidates:
        judgment_id = candidate["judgment_id"]
        # A candidate the reranker did not reach keeps its bi-encoder score,
        # which would compare against cross-encoder scores on a different
        # scale — so those are ranked only when nothing was reranked at all.
        score = candidate.get(score_key)
        if score is None:
            continue
        if score > best.get(judgment_id, float("-inf")):
            best[judgment_id] = float(score)

    if not best:
        return rank_judgments(candidates, top_k=top_k, score_key="score") if score_key != "score" else []

    roots = _root_nodes_by_judgment()

    results = [
        {
            # file_id is this project's judgment identifier.
            "judgment_id": judgment_id,
            # The root node id, which context expansion resolves the case from.
            "mongo_doc_id": roots.get(judgment_id, {}).get("node_id", ""),
            "heading": roots.get(judgment_id, {}).get("heading", ""),
            "score": score,
        }
        for judgment_id, score in best.items()
    ]

    results.sort(key=lambda r: r["score"], reverse=True)

    # The floor is only applied on the calibrated scale. Cosine similarity has
    # no meaningful absolute cut-off here, so bi-encoder-only runs are not
    # filtered; abstention needs the cross-encoder.
    if score_key == "relevance":
        floor = settings.RELEVANCE_THRESHOLD if threshold is None else threshold
        kept = [r for r in results if r["score"] >= floor]
        if len(kept) < len(results):
            logger.info(
                f"Relevance floor {floor:.2f}: kept {len(kept)} of {len(results)} judgments"
            )
        results = kept

    return results[:top_k]


def search_judgments(query_vector: np.ndarray, top_k: int = 5) -> list[dict]:
    """Rank judgments straight from a query vector, without reranking.

    Kept as the single-call form for callers that do not run the full pipeline
    (summarisation, the self-checks in this package). The orchestrator calls
    :func:`search_chunks` and :func:`rank_judgments` separately so it can
    rerank in between.
    """
    results = rank_judgments(search_chunks(query_vector), top_k=top_k)
    logger.info(f"Stage 1 search: returned {len(results)} judgments")
    return results


if __name__ == "__main__":
    from app.retrieval.query_embedder import embed_query

    print(f"collection : {collection.name}")
    print(f"vectors    : {collection.count()}")
    print(f"pool size  : {candidate_pool_size()}\n")

    vec = embed_query("suo motu jurisdiction of a single judge under article 199")

    chunks = search_chunks(vec)
    print(f"chunk candidates: {len(chunks)}")
    for c in chunks[:3]:
        label = c["section_type"] or "(no section_type)"
        print(f"  {c['score']:.4f}  {label:<16} chunk {c['chunk_index']}  {c['heading'][:34]!r}")

    results = search_judgments(vec, top_k=3)
    print(f"\njudgments: {len(results)}")
    for r in results:
        print(f"  {r['score']:.4f}  {r['heading'][:48]!r}  {r['judgment_id'][:8]}")

    assert chunks, "stage 1 returned no chunks"
    assert all(c["mongo_doc_id"] for c in chunks), "a chunk is missing its node id"
    assert all("::" not in c["mongo_doc_id"] for c in chunks), \
        "mongo_doc_id carries a chunk suffix; it must be the bare node id"
    assert chunks == sorted(chunks, key=lambda c: c["score"], reverse=True), "chunks not sorted"

    assert results, "Stage 1 search returned nothing"
    assert all(r["judgment_id"] for r in results), "a result is missing its judgment_id"
    assert all(r["mongo_doc_id"] for r in results), "a result is missing its root node"
    assert all(r["heading"] for r in results), "a result is missing its case title"
    assert len({r["judgment_id"] for r in results}) == len(results), "a judgment appeared twice"
    assert results == sorted(results, key=lambda r: r["score"], reverse=True), "not sorted"

    # section_type must now arrive from Chroma rather than being blank.
    labelled = [c for c in chunks if c["section_type"]]
    print(f"\nchunks carrying section_type: {len(labelled)}/{len(chunks)}")
    assert labelled, "section_type is still missing from Chroma metadata"

    print(f"OK: {len(chunks)} chunks -> {len(results)} judgments ranked.")
