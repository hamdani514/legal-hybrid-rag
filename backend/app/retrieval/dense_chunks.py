"""
Dense chunk retrieval (R4 dense_chunks) behind the Retriever protocol.

Why an adapter rather than a new search
---------------------------------------
app.retrieval.chroma_client.search_chunks is the live stage-1 search and is
already tuned (pool sizing, level filter, cosine scores). This class only gives
it the Retriever shape the fusion stage expects: a QueryAnalysis in, ranked
Candidates out, [] instead of an exception.

Rewrite and expansions
----------------------
When the query analyzer supplies a legal ``rewrite`` and ``expansions``, each
is embedded and searched too, and the lists are merged by the MAX score per
vector id. Max, not sum: a chunk that matches one phrasing very well is a good
hit, and summing would reward chunks for being mediocre against all of them.

Case descriptions
-----------------
For a narrative query the facets (facts, each side's case, the court's view —
the user's own words, split by the query analyzer) are searched as well and
merged by the same max. A whole 150-word story embeds as an average of all
its parts; a single part embeds sharply and finds the one section that
discusses it (the court's view finds ANALYSIS_RATIO, the facts find FACTS).

One embedding per text per search
---------------------------------
pipeline_v2 embeds every distinct text once and hands the vectors over in
``analysis["_vectors"]`` ({text: vector}); this retriever, dense_cards and the
evidence top-up all read from it, and embed only what is missing (so the
retriever still works on its own). The key is internal and never returned.

Other collections
-----------------
``collection_name`` points the retriever at a different Chroma collection with
the same metadata layout — used to measure the contextual-header experiment
(legal_embeddings_v3_ctx) against the live legal_embeddings_v2 without
touching the live module. The default (None) is the live search_chunks path.
"""

import asyncio
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from loguru import logger

from app.retrieval.contracts import Candidate, QueryAnalysis, with_ranks

SECTION_LEVEL = 2


FACET_TEXT_KEYS = ("facts", "claimant", "respondent", "court_view")


def facet_texts(analysis: QueryAnalysis) -> list[str]:
    """A narrative's facet texts (user's words), in a fixed order; [] for short queries."""
    if not analysis.get("is_narrative"):
        return []
    facets = analysis.get("facets") or {}
    return [str(facets[k]).strip() for k in FACET_TEXT_KEYS
            if isinstance(facets.get(k), str) and facets[k].strip()]


def query_texts(analysis: QueryAnalysis, with_facets: bool = True) -> list[str]:
    """The phrasings to search: cleaned (or raw), rewrite, expansions, then facets."""
    texts = [analysis.get("cleaned") or analysis.get("raw") or ""]
    if analysis.get("rewrite"):
        texts.append(analysis["rewrite"])
    texts.extend(e for e in (analysis.get("expansions") or []) if e)
    if with_facets:
        texts.extend(facet_texts(analysis))
    out: list[str] = []
    for text in texts:
        text = str(text).strip()
        if text and text not in out:
            out.append(text)
    return out


def _search_collection(collection, vector, pool: int) -> list[dict]:
    """search_chunks' query and result shape, against an arbitrary collection."""
    response = collection.query(
        query_embeddings=[vector.tolist()],
        n_results=max(1, min(pool, collection.count())),
        where={"level": {"$eq": SECTION_LEVEL}},
        include=["metadatas", "distances", "documents"],
    )
    ids = (response.get("ids") or [[]])[0]
    distances = (response.get("distances") or [[]])[0]
    metadatas = (response.get("metadatas") or [[]])[0]
    documents = (response.get("documents") or [[]])[0]
    out = []
    for i, vector_id in enumerate(ids):
        meta = metadatas[i] or {}
        if not meta.get("file_id"):
            continue
        out.append({
            "judgment_id": meta["file_id"],
            "mongo_doc_id": meta.get("node_id", vector_id),
            "vector_id": vector_id,
            "section_type": meta.get("section_type", ""),
            "heading": meta.get("heading", ""),
            "chunk_index": meta.get("chunk_index", 0),
            "text": documents[i] if i < len(documents) else "",
            "score": float(1.0 - distances[i]),
        })
    return out


class DenseChunksRetriever:
    """R4: bge-base chunk vectors in Chroma; one candidate per chunk."""

    name = "dense_chunks"

    def __init__(self, collection_name: str | None = None):
        self.collection_name = collection_name
        self._collection = None

    def _collection_handle(self):
        if self._collection is None:
            from app.vectorstore.chroma_store import chroma_store
            self._collection = chroma_store.client.get_collection(self.collection_name)
        return self._collection

    def search(self, analysis: QueryAnalysis, k: int) -> list[Candidate]:
        from app.retrieval.query_embedder import embed_query

        texts = query_texts(analysis)
        if not texts or k <= 0:
            return []

        vectors = analysis.get("_vectors") or {}
        best: dict[str, dict] = {}
        for text in texts:
            vector = vectors.get(text)
            if vector is None:
                vector = embed_query(text)
            if self.collection_name:
                hits = _search_collection(self._collection_handle(), vector, k)
            else:
                from app.retrieval.chroma_client import search_chunks
                hits = search_chunks(vector, pool=k)
            for hit in hits:
                key = hit.get("vector_id") or hit["mongo_doc_id"]
                if key not in best or hit["score"] > best[key]["score"]:
                    best[key] = hit

        ranked = sorted(best.values(), key=lambda c: c["score"], reverse=True)[:k]
        return with_ranks([Candidate(**c) for c in ranked], self.name)  # type: ignore[typeddict-item]

    async def retrieve(self, analysis: QueryAnalysis, k: int) -> list[Candidate]:
        try:
            return await asyncio.to_thread(self.search, analysis, k)
        except Exception as e:
            logger.warning(f"dense_chunks({self.collection_name or 'live'}) failed, returning []: {e}")
            return []


if __name__ == "__main__":
    logger.remove()
    q = "general elections 2013 National Assembly seat NA-266 Nasirabad Jaffarabad"

    live = asyncio.run(DenseChunksRetriever().retrieve({"raw": q, "cleaned": q.lower()}, 20))
    assert live and len(live) <= 20, "live dense search returned nothing"
    assert [c["rank"] for c in live] == list(range(len(live)))
    assert all(live[i]["score"] >= live[i + 1]["score"] for i in range(len(live) - 1))
    assert live[0]["source"] == "dense_chunks" and live[0]["judgment_id"]
    print(f"OK: live top-1 {live[0]['judgment_id'][:8]} {live[0]['section_type']} {live[0]['score']:.3f}")

    merged = asyncio.run(DenseChunksRetriever().retrieve(
        {"raw": q, "cleaned": q.lower(), "rewrite": "election petition NA-266",
         "expansions": ["corrupt practices in the 2013 election"]}, 20))
    ids = [c["vector_id"] for c in merged]
    assert len(ids) == len(set(ids)), "merge must dedupe by vector id"
    assert merged[0]["score"] >= live[0]["score"] - 1e-6, "max-merge cannot lower the top score"
    print(f"OK: rewrite+expansions merged by max, {len(merged)} unique chunks")

    # Facets are searched for narratives only; precomputed vectors are used, not recomputed.
    story = {"raw": q, "cleaned": q.lower(), "is_narrative": True,
             "facets": {"facts": "election to NA-266", "court_view": "the tribunal dismissed the petition",
                        "outcome_sc": "dismissed"}}
    assert query_texts(story) == [q.lower(), "election to NA-266", "the tribunal dismissed the petition"]
    assert query_texts({**story, "is_narrative": False}) == [q.lower()]
    import app.retrieval.query_embedder as qe
    precomputed = {t: qe.embed_query(t) for t in query_texts(story)}
    original, calls = qe.embed_query, []
    qe.embed_query = lambda text: calls.append(text) or original(text)
    try:
        got = asyncio.run(DenseChunksRetriever().retrieve({**story, "_vectors": precomputed}, 20))
    finally:
        qe.embed_query = original
    assert got and calls == [], f"precomputed vectors must be used, embedded again: {calls}"
    print(f"OK: facets searched for narratives, precomputed vectors reused ({len(got)} chunks)")

    assert asyncio.run(DenseChunksRetriever("no_such_collection").retrieve(
        {"raw": q, "cleaned": q}, 5)) == []
    assert asyncio.run(DenseChunksRetriever().retrieve({"raw": "", "cleaned": ""}, 5)) == []
    print("OK: missing collection and empty query return []")
