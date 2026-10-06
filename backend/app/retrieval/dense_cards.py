"""
Dense case-card retrieval (R5 dense_cards) and the build of its collection.

Why one vector per judgment
---------------------------
Chunk vectors answer "which passage says this"; they are poor at "which case is
about this", because no single 480-token passage states what the whole
judgment decided. A case card (Agent B) does: case number, subject, a grounded
headnote, the issues, the holding, keywords. Embedding that one text per
judgment gives a retriever that matches a vague or topical query ("any
evacuee land dispute") against what the case is about rather than against
whichever paragraph happens to share its words.

It replaces nothing: the old root nodes held a templated summary that was
nearly identical across judgments (see app.retrieval.chroma_client), which is
why ranking by root summary measured 29% precision@1. Cards are written from
the judgment's own text.

Storage: Chroma collection settings.CARDS_COLLECTION ("legal_cards_v1"),
cosine space, id = judgment_id, metadata file_id/judgment_id/case_display/
subject/outcome. Empty or missing collection -> retrieve() returns [].

Card text v2: parties and outcome
---------------------------------
Users now describe their case: "my client won in the High Court, the
government appealed and the Supreme Court dismissed it". The v1 card text
held neither the parties nor the outcome, so that half of a description had
nothing to meet. card_text() now adds "Parties: X v. Y" and "Outcome: Appeal
allowed" (from case_cards.outcome; "unknown" is omitted). Vectors built from
this text live in a NEW collection (legal_cards_v2, build_v2()); the live
legal_cards_v1 is never rewritten by this module's tooling.

The v2 text is OPT-IN (settings.CARD_TEXT_VERSION, default 1): measured on the
frozen narrative baseline and the dev set, legal_cards_v2 was WORSE (loose
descriptions 2/5 vs 3/5, dev p@1 14/22 vs 15/22), so any caller that refreshes
card vectors into v1 (the ingestion card wave) keeps writing the v1 text. The
version is stored in each vector's metadata so a mixed collection is detectable.

Query side
----------
The user's phrasing, the rewrite, the expansions and (for narratives) the
facets are each searched and merged by max score per judgment, reading
precomputed vectors from analysis["_vectors"] when pipeline_v2 supplies them.
"""

import asyncio
import sys
import time
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from loguru import logger

from app.config import settings
from app.retrieval.contracts import Candidate, QueryAnalysis, with_ranks

EMBED_BATCH_SIZE = 32
V2_COLLECTION = "legal_cards_v2"

# How a card outcome reads in the card text: the words a FINAL_ORDER and a
# user describing the result would both use.
OUTCOME_PHRASES = {
    "allowed": "Appeal allowed",
    "dismissed": "Appeal dismissed",
    "partly_allowed": "Appeal partly allowed",
    "remanded": "Case remanded for fresh decision",
    "disposed": "Disposed of",
}


def collection_name() -> str:
    return getattr(settings, "CARDS_COLLECTION", "") or "legal_cards_v1"


def card_text_version() -> int:
    return int(getattr(settings, "CARD_TEXT_VERSION", 1) or 1)


def card_text(card: dict, version: int | None = None) -> str:
    """The one text embedded per card: what the case is (v2: also who the parties
    are and how it ended). version defaults to settings.CARD_TEXT_VERSION (1)."""
    version = card_text_version() if version is None else int(version)
    def join(value) -> str:
        if isinstance(value, (list, tuple)):
            return "; ".join(str(v) for v in value if v)
        return str(value or "")

    if version < 2:
        parts = [
            join(card.get("case_display")),
            join(card.get("subject")) if card.get("subject") != "Other" else "",
            join(card.get("headnote")),
            ("Issues: " + join(card.get("issues"))) if card.get("issues") else "",
            ("Held: " + join(card.get("holding"))) if card.get("holding") else "",
            ("Keywords: " + join(card.get("keywords"))) if card.get("keywords") else "",
        ]
        return "\n".join(p.strip() for p in parts if p and p.strip())

    appellant, respondent = join(card.get("appellant")).strip(), join(card.get("respondent")).strip()
    parties = f"{appellant} v. {respondent}" if appellant and respondent else (appellant or respondent)
    outcome = OUTCOME_PHRASES.get(str(card.get("outcome") or ""), "")
    parts = [
        join(card.get("case_display")),
        join(card.get("subject")) if card.get("subject") != "Other" else "",
        ("Parties: " + parties) if parties else "",
        join(card.get("headnote")),
        ("Issues: " + join(card.get("issues"))) if card.get("issues") else "",
        ("Held: " + join(card.get("holding"))) if card.get("holding") else "",
        ("Outcome: " + outcome) if outcome else "",
        ("Keywords: " + join(card.get("keywords"))) if card.get("keywords") else "",
    ]
    return "\n".join(p.strip() for p in parts if p and p.strip())


def _client():
    from app.vectorstore.chroma_store import chroma_store
    return chroma_store.client


def build_from_cards(cards: list[dict], reset: bool = False, name: str | None = None,
                     text_version: int | None = None) -> int:
    """Upsert one vector per card; drop vectors for judgments no longer carded.

    Idempotent: re-running with the same cards rewrites the same ids.
    Returns the number of vectors written.
    """
    from app.embeddings.embedding_generator import EmbeddingGenerator

    name = name or collection_name()
    assert name != getattr(settings, "CHROMA_COLLECTION", "legal_embeddings_v2"), \
        "the cards collection must not be the live chunk collection"
    client = _client()
    if reset:
        try:
            client.delete_collection(name)
        except Exception:
            pass
    collection = client.get_or_create_collection(name=name, metadata={"hnsw:space": "cosine"})

    text_version = card_text_version() if text_version is None else int(text_version)
    rows = [(c["judgment_id"], card_text(c, text_version), c) for c in cards if c.get("judgment_id")]
    rows = [r for r in rows if r[1]]
    keep = {r[0] for r in rows}

    stale = [i for i in collection.get(include=[]).get("ids", []) if i not in keep]
    if stale:
        collection.delete(ids=stale)

    generator = EmbeddingGenerator()
    for start in range(0, len(rows), EMBED_BATCH_SIZE):
        batch = rows[start:start + EMBED_BATCH_SIZE]
        vectors = generator.generate_embeddings([text for _, text, _ in batch])
        collection.upsert(
            ids=[jid for jid, _, _ in batch],
            embeddings=vectors,
            documents=[text for _, text, _ in batch],
            metadatas=[{
                "file_id": jid, "judgment_id": jid,
                "case_display": str(card.get("case_display") or ""),
                "subject": str(card.get("subject") or ""),
                "outcome": str(card.get("outcome") or "unknown"),
                "card_text_version": text_version,
            } for jid, _, card in batch],
        )
    logger.info(f"Card vectors: {len(rows)} written, {len(stale)} stale removed, "
                f"{collection.count()} in {name!r}")
    return len(rows)


async def build(reset: bool = False) -> dict:
    """Build the card collection from MongoDB case_cards."""
    from app.indexing.fts_index import load_cards

    started = time.perf_counter()
    cards = await load_cards()
    written = build_from_cards(list(cards.values()), reset=reset) if cards or reset else 0
    if not cards:
        logger.warning("case_cards is empty; card collection left as is (nothing to embed)")
    return {"cards": len(cards), "written": written, "collection": collection_name(),
            "elapsed_s": round(time.perf_counter() - started, 2)}


async def build_v2(reset: bool = True) -> dict:
    """Build legal_cards_v2 (card text v2) from MongoDB case_cards; never touches v1.

        python -m app.retrieval.dense_cards --build-v2
    """
    from app.indexing.fts_index import load_cards

    assert V2_COLLECTION != "legal_cards_v1"
    started = time.perf_counter()
    cards = await load_cards()
    written = build_from_cards(list(cards.values()), reset=reset, name=V2_COLLECTION, text_version=2)         if cards else 0
    return {"cards": len(cards), "written": written, "collection": V2_COLLECTION,
            "elapsed_s": round(time.perf_counter() - started, 2)}


class DenseCardsRetriever:
    """R5: query vector vs one card vector per judgment."""

    name = "dense_cards"

    def __init__(self, name: str | None = None):
        self.collection_name = name or collection_name()

    def search(self, analysis: QueryAnalysis, k: int) -> list[Candidate]:
        from app.retrieval.query_embedder import embed_query

        try:
            collection = _client().get_collection(self.collection_name)
        except Exception:
            return []
        from app.retrieval.dense_chunks import query_texts

        total = collection.count()
        # The rewrite is legal language, which is what card text is written in;
        # the user's own phrasing, the expansions and a narrative's facets are
        # searched too and merged by max.
        texts = query_texts(analysis)
        if not total or not texts or k <= 0:
            return []
        vectors = analysis.get("_vectors") or {}
        best: dict[str, Candidate] = {}
        for text in texts:
            vector = vectors.get(text)
            if vector is None:
                vector = embed_query(text)
            response = collection.query(
                query_embeddings=[vector.tolist()],
                n_results=min(k, total),
                include=["metadatas", "distances", "documents"],
            )
            for jid, dist, meta, doc in zip(response["ids"][0], response["distances"][0],
                                            response["metadatas"][0], response["documents"][0]):
                score = float(1.0 - dist)
                if jid not in best or score > best[jid]["score"]:
                    best[jid] = {
                        "judgment_id": (meta or {}).get("judgment_id") or jid,
                        "mongo_doc_id": "",
                        "vector_id": f"card:{jid}",
                        "section_type": "CARD",
                        "heading": (meta or {}).get("case_display", ""),
                        "chunk_index": 0,
                        "text": doc or "",
                        "score": score,
                    }
        ranked = sorted(best.values(), key=lambda c: c["score"], reverse=True)[:k]
        return with_ranks(ranked, self.name)

    async def retrieve(self, analysis: QueryAnalysis, k: int) -> list[Candidate]:
        try:
            return await asyncio.to_thread(self.search, analysis, k)
        except Exception as e:
            logger.warning(f"dense_cards failed, returning []: {e}")
            return []


if __name__ == "__main__":
    logger.remove()
    if "--build-v2" in sys.argv:
        print(asyncio.run(build_v2()))
        sys.exit(0)

    card = {"judgment_id": "j", "case_display": "Civil Appeal No. 5-Q of 2014",
            "subject": "Election law", "headnote": "Election petition dismissed.",
            "issues": ["corrupt practice", "recount"], "keywords": ["NA-266"]}
    text = card_text(card)
    assert text.startswith("Civil Appeal No. 5-Q of 2014\nElection law")
    assert "Issues: corrupt practice; recount" in text and "Keywords: NA-266" in text
    assert card_text({"judgment_id": "x", "subject": "Other"}) == ""
    v1 = card_text({**card, "appellant": "X", "respondent": "Y", "outcome": "dismissed"}, 1)
    assert "Parties" not in v1 and "Outcome" not in v1 and v1 == text, "v1 text must be unchanged"
    full = card_text({**card, "appellant": "Mir Saleem Ahmed Khosa", "respondent": "Zafarullah Khan Jamali",
                      "outcome": "dismissed"}, 2)
    assert "Parties: Mir Saleem Ahmed Khosa v. Zafarullah Khan Jamali" in full, full
    assert "Outcome: Appeal dismissed" in full
    assert "Outcome" not in card_text({**card, "outcome": "unknown"}, 2)
    print("OK: card text (v2: parties and outcome; unknown outcome omitted)")

    assert asyncio.run(DenseCardsRetriever("no_such_cards_collection").retrieve(
        {"raw": "x", "cleaned": "x"}, 5)) == []
    print("OK: missing collection -> []")

    # Round trip through a throwaway collection, so the real one is untouched.
    test_name = "legal_cards_selftest"
    try:
        cards = [
            card,
            {"judgment_id": "k", "case_display": "Civil Appeal No. 1 of 2020",
             "subject": "Intellectual property", "headnote": "Assignment of a trade mark."},
        ]
        assert build_from_cards(cards, reset=True, name=test_name) == 2
        assert build_from_cards(cards[:1], name=test_name) == 1          # stale card removed
        assert _client().get_collection(test_name).count() == 1
        build_from_cards(cards, name=test_name)
        got = asyncio.run(DenseCardsRetriever(test_name).retrieve(
            {"raw": "who owns a trade mark", "cleaned": "who owns a trade mark"}, 5))
        assert got[0]["judgment_id"] == "k" and got[0]["section_type"] == "CARD", got
        assert got[0]["mongo_doc_id"] == "" and got[0]["rank"] == 0
        print(f"OK: build/upsert/stale-removal/retrieve round trip (top {got[0]['score']:.3f})")
    finally:
        try:
            _client().delete_collection(test_name)
        except Exception:
            pass
