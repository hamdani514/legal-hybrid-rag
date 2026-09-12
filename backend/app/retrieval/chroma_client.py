"""
ChromaDB access for the retrieval pipeline — Stage 1 search (judgment level).

STEP 3 of retrieval: takes a query vector and returns a ranked list of the
judgments most relevant to it. No MongoDB calls, no JSON file reads.

How a judgment is scored
------------------------
A judgment's relevance is the score of its single best-matching section, not
the score of its root summary. This matters: the ingestion pipeline generates
each root node's context_summary from a template, so those summaries are nearly
identical across judgments apart from party names —

    "Appeal by X against Y regarding the legal dispute. The Supreme Court held
     that the Court interpreted the relevant statutory provisions and rules."

— which carries no subject matter to match a query against. Measured on a
17-query labelled set over 9 judgments, ranking by root summary gave 29.4%
precision@1; ranking by best section gave 94.1% on the identical embeddings and
queries. Every result still identifies its judgment by the root node, so the
two-stage structure is unchanged: stage 1 picks judgments, stage 2 (see
app.retrieval.node_searcher) picks sections within them.

Notes on this project's actual ChromaDB setup
---------------------------------------------
ChromaDB runs *embedded* here (chromadb.PersistentClient over
backend/chroma_db), not as an HTTP server, so there is no CHROMA_HOST/PORT to
read. The connection is owned by app.vectorstore.chroma_store, which the
ingestion pipeline also writes through; this module reuses that singleton so
only one client ever touches the on-disk database.

The ingestion pipeline stores these metadata fields on every embedding:

    node_id         str   this node's id (also the Chroma vector id)
    file_id         str   the judgment/PDF id that owns this node
    parent_node_id  str   parent node id, "" for a root
    level           int   1 = root/parent node, 2 = section/child node
    heading         str   the node's title

There is no `node_type`, `filename` or `section_type` in Chroma: roots are
identified by level == 1, and filename/section_type live in MongoDB
(documents.filename, nodes.section_type) for a later step to join on.
"""

import sys
from pathlib import Path

# Allow `python app/retrieval/chroma_client.py` as well as
# `python -m app.retrieval.chroma_client`.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np
from loguru import logger

from app.vectorstore.chroma_store import chroma_store

# Ingestion writes level 1 for root/parent nodes and level 2 for sections.
ROOT_LEVEL = 1
SECTION_LEVEL = 2

# How many sections to pull before grouping them by judgment. The top sections
# often cluster inside a few judgments, so the pool has to be well wider than
# top_k for the ranking to see enough distinct cases.
CANDIDATES_PER_JUDGMENT = 20
MIN_CANDIDATE_POOL = 100

collection = chroma_store.collection

logger.info(
    f"ChromaDB connected. Collection: {collection.name}. "
    f"Total embeddings: {collection.count()}"
)


def _root_nodes_by_judgment() -> dict[str, dict]:
    """Map each judgment id to its root node's id and heading.

    Read fresh rather than cached, so a re-ingest is picked up without a
    restart; it is one metadata-only read of a single row per judgment.
    """
    got = collection.get(where={"level": {"$eq": ROOT_LEVEL}}, include=["metadatas"])
    roots: dict[str, dict] = {}
    for node_id, meta in zip(got.get("ids") or [], got.get("metadatas") or []):
        roots[meta.get("file_id", "")] = {
            "node_id": meta.get("node_id", node_id),
            "heading": meta.get("heading", ""),
        }
    return roots


def search_judgments(query_vector: np.ndarray, top_k: int = 5) -> list[dict]:
    """Stage 1 search: rank judgments by their best-matching section.

    Args:
        query_vector: The L2-normalised query embedding from
            :func:`app.retrieval.query_embedder.embed_query`.
        top_k: How many judgments to return.

    Returns:
        A list of dicts sorted by descending score, each holding
        ``judgment_id``, ``mongo_doc_id`` (the root node, for context
        expansion), ``heading`` (the case title) and ``score``.
    """
    pool = max(top_k * CANDIDATES_PER_JUDGMENT, MIN_CANDIDATE_POOL)

    response = collection.query(
        query_embeddings=[query_vector.tolist()],
        n_results=pool,
        where={"level": {"$eq": SECTION_LEVEL}},
        include=["metadatas", "distances"],
    )

    # Chroma nests one list per submitted query vector; we only sent one.
    distances = (response.get("distances") or [[]])[0]
    metadatas = (response.get("metadatas") or [[]])[0]

    # Keep only each judgment's strongest section.
    best: dict[str, float] = {}
    for meta, distance in zip(metadatas, distances):
        judgment_id = meta.get("file_id", "")
        if not judgment_id:
            continue
        # The collection uses cosine space, so similarity = 1 - distance.
        score = float(1.0 - distance)
        if score > best.get(judgment_id, float("-inf")):
            best[judgment_id] = score

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
    results = results[:top_k]

    logger.info(f"Stage 1 search: returned {len(results)} judgments")
    return results


if __name__ == "__main__":
    from app.retrieval.query_embedder import embed_query

    vec = embed_query("suo motu jurisdiction of a single judge under article 199")
    results = search_judgments(vec, top_k=3)

    for r in results:
        print(f"{r['heading'][:48]!r}  score={r['score']:.4f}  judgment_id={r['judgment_id'][:8]}")

    assert results, "Stage 1 search returned nothing"
    assert all(r["judgment_id"] for r in results), "a result is missing its judgment_id"
    assert all(r["mongo_doc_id"] for r in results), "a result is missing its root node"
    assert all(r["heading"] for r in results), "a result is missing its case title"
    assert len({r["judgment_id"] for r in results}) == len(results), "a judgment appeared twice"
    assert results == sorted(results, key=lambda r: r["score"], reverse=True), "not sorted"
    print(f"OK: {len(results)} judgments ranked.")
