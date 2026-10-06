"""
Precision-v2 retrieval: analysis -> R1..R5 -> fusion -> cross-encoder -> judge -> abstention.

Why a separate entry point
--------------------------
The live orchestrator ranks judgments by reranking the top 40 chunks of the
whole corpus (see app.retrieval.reranker). That window is counted in chunks, so
at 3,000 judgments the right case falls outside it. This module ranks in
judgments end to end, and returns exactly what orchestrator's stages 4-5
produce, so the integrator can splice it in after stage 4 without touching
context expansion, assembly or answering:

    "analysis"        QueryAnalysis
    "parent_results"  [{judgment_id, mongo_doc_id (ROOT node), heading, score 0..1}]
    "stage2_results"  {judgment_id: [section dicts, node_searcher.dedupe_to_sections shape]}
    "candidates"      the evidence Candidates the cross-encoder read
    "reranked", "judge_used", "reasons", "no_results", "timings_ms"

Stages, each behind a flag read at CALL time (so eval ablations can flip them):

    Q  analysis      analyze() if USE_QUERY_ANALYZER and QUERY_ANALYZER_USE_LLM,
                     analyze_regex() if USE_QUERY_ANALYZER only, else a bare
                     analysis (raw, cleaned, heuristic type — no entities)
    R  retrievers    dense_chunks always; exact (USE_EXACT_MATCH); bm25 chunks +
                     cards (USE_BM25); dense_cards (USE_CARDS) — in parallel
    F  fusion        judgment-level RRF (USE_FUSION), else the union control
    K  cross-encoder top V2_RERANK_JUDGMENTS judgments x <=V2_RERANK_PASSAGES
                     passages; relevance = max sigmoid(logit). By default
                     (V2_FINAL_ORDER="fusion") it gates and scores but does not
                     reorder: on dev the fused order was the better top-1. With
                     "fusion" order, parent_results scores are therefore NOT
                     necessarily descending.
    J  judge         listwise LLM judge over the top JUDGE_TOP_N (USE_LLM_JUDGE)
    A  abstention    judge off: relevance >= RELEVANCE_THRESHOLD; judge on:
                     keep what the judge marks relevant, abstain only if it
                     marks nothing AND the top relevance is under the floor

Exact-match hits are never abstained on: the user named the case.

Case descriptions (narratives)
------------------------------
A query of NARRATIVE_MIN_WORDS+ words with 2+ text facets (query_analyzer)
takes the facet path for stages K and A:
  * every text (query, rewrite, expansions, facets) is embedded ONCE and the
    vectors are shared by dense retrieval, the outcome signal and evidence;
  * the facet outcome_sc nudges judgments whose card has the same outcome
    (fusion.apply_outcome_signal, a quarter of one vote, never a filter);
  * evidence is one passage per facet from that facet's sections
    (build_facet_evidence), the cross-encoder scores facet <-> passage pairs
    with a short query side (rerank_facets), and a judgment's relevance is the
    mean of its two best facets (narrative_relevance);
  * the agreement gate runs with the narrative floor
    (V2_NARRATIVE_RELEVANCE_THRESHOLD);
  * without the judge, the top result is labelled at most
    NARRATIVE_MAX_CONFIDENCE ("medium"); only a case number keeps "high".
Party-name hits on a narrative vote in fusion instead of pinning (exact_match).

Degradation, and the one place it fails closed
----------------------------------------------
A retriever that raises contributes []; fusion that fails falls back to dense
order; a judge that times out or returns garbage leaves the reranker order.
The cross-encoder is different: it IS the gate, so when it raises or the model
is unavailable the search abstains (only case-number hits are shown) rather
than showing ungated results. Only when reranking is switched off by the
operator (RERANK_ENABLED=False) is the fused order shown ungated, as before.
retrieve_v2 itself never raises for a well-formed string.
"""

import asyncio
import sys
import time
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from loguru import logger

from app.config import settings
from app.retrieval.contracts import NARRATIVE_MIN_WORDS, Candidate, QueryAnalysis
from app.retrieval.fusion import SECTION_PREFERENCE, FusedJudgment, apply_outcome_signal, fuse, select_evidence

# Test/eval hook: values here win over settings. Lets the evaluation toggle
# proposed keys that config.py does not define yet (pydantic settings reject
# unknown attributes). Empty in production.
OVERRIDES: dict = {}

# Debug artefacts of the last call (full ranked window with relevance), for the
# calibration sweep and the query log. Not part of the return contract.
last_debug: dict = {}

DEFAULTS = {
    "DENSE_CHUNKS_COLLECTION": "",     # "" = the live collection via chroma_client.search_chunks
    "V2_CHUNK_POOL": 200,              # candidates per chunk retriever
    "V2_CARD_POOL": 50,                # candidates per card retriever
    "V2_RERANK_JUDGMENTS": 30,         # fused judgments the cross-encoder sees
    "V2_RERANK_PASSAGES": 3,           # passages per judgment
    "USE_SECTION_WEIGHTING": False,    # reserve an evidence slot for the query type's section
    "V2_RERANK_INCLUDE_CARD": False,   # also cross-encode the judgment's case card
    "JUDGE_TOP_N": 10,
    # "fusion": the cross-encoder GATES (abstention, displayed score) and the
    # fused order is kept; "rerank": the cross-encoder also ORDERS. Measured on
    # dev (22 positives), fusion order wins: p@1 19/22 vs 16/22 with no floor,
    # 17/22 vs 15/22 at a 0.01 floor — the cross-encoder demoted four correct
    # top-1 judgments and promoted one. n is tiny; re-measure at scale.
    "V2_FINAL_ORDER": "fusion",
    # Case descriptions (see the narrative section). Measured on the frozen
    # narrative baseline (11 detailed + 1 loose narratives on the facet path
    # vs 7 out-of-archive + 2 party-misfire descriptions): the top judgment's
    # facet relevance (mean of the two best facets) was >= 0.019 for every real
    # match and <= 0.003 for every negative that 3+ retrievers agreed on, so
    # the floor sits between them (0.008, near their geometric middle). n is
    # tiny; re-measure on Agent V's narrative dev set and at 1,000 judgments.
    "V2_NARRATIVE_RELEVANCE_THRESHOLD": 0.008,
    # A second way for a case description's top judgment to pass the gate
    # (see lexical_lead): both keyword indexes single it out by this relative
    # margin AND V2_AGREEMENT_MIN retrievers rank it first. On narrative_dev
    # every out-of-archive description led by <= 0.32 and the real matches
    # the cross-encoder scored ~0 (unreliable section labels) by 0.41-0.53;
    # the cut sits between, leaning towards the positives (a leak costs more
    # than a refusal). More
    # judgments make the lead smaller, so the rule gets stricter with scale.
    # n is tiny (2 judgments recovered); re-measure at 1,000. None disables.
    "V2_NARRATIVE_LEXICAL_LEAD": 0.38,
    "V2_NARRATIVE_AGGREGATE": "mean_top2",
    "V2_NARRATIVE_MIN_FACETS": 2,
    "V2_OUTCOME_SIGNAL": True,
}


def opt(name: str, default=None):
    """OVERRIDES, then settings, then DEFAULTS — always at call time."""
    if name in OVERRIDES:
        return OVERRIDES[name]
    return getattr(settings, name, DEFAULTS.get(name, default))


# ── Q: analysis ──────────────────────────────────────────────────────────────

async def _analysis(raw: str) -> QueryAnalysis:
    from app.retrieval import query_analyzer

    try:
        if opt("USE_QUERY_ANALYZER", False):
            if opt("QUERY_ANALYZER_USE_LLM", True):
                return await query_analyzer.analyze(raw)
            return query_analyzer.analyze_regex(raw)
        full = query_analyzer.analyze_regex(raw)
    except Exception as e:
        logger.warning(f"query analysis failed, using the raw query: {e}")
        return QueryAnalysis(raw=raw, cleaned=raw.strip().lower(), query_type="unknown",
                             rewrite="", expansions=[], source="regex",
                             is_narrative=len(raw.split()) >= NARRATIVE_MIN_WORDS,  # type: ignore[typeddict-unknown-key]
                             facets={})  # type: ignore[typeddict-unknown-key]
    # Analyzer off: the text and a heuristic type only — no case refs, parties
    # or rewrite — so the analyzer's contribution is measurable on its own.
    # Narrative detection and the cue-based facets are kept: they cost no
    # network call and the whole case-description path depends on them.
    return QueryAnalysis(raw=raw, cleaned=full.get("cleaned", raw), query_type=full.get("query_type", "unknown"),
                         rewrite="", expansions=[], source="regex",
                         is_narrative=bool(full.get("is_narrative")),  # type: ignore[typeddict-unknown-key]
                         facets=dict(full.get("facets") or {}),  # type: ignore[typeddict-unknown-key]
                         outcome=full.get("outcome") if full.get("is_narrative") else None)


# ── R: retrievers ────────────────────────────────────────────────────────────

# ExactMatchRetriever holds a motor client bound to the loop it first ran on,
# so retrievers are cached per event loop rather than per process.
_retrievers: dict[int, dict] = {}


def _retriever_set() -> dict:
    loop_id = id(asyncio.get_running_loop())
    collection = opt("DENSE_CHUNKS_COLLECTION", "") or None
    cached = _retrievers.get(loop_id)
    if cached is None or cached["_collection"] != collection:
        from app.retrieval.dense_cards import DenseCardsRetriever
        from app.retrieval.dense_chunks import DenseChunksRetriever
        from app.retrieval.exact_match import ExactMatchRetriever
        from app.retrieval.lexical import BM25CardsRetriever, BM25ChunksRetriever

        cached = {
            "_collection": collection,
            "dense_chunks": DenseChunksRetriever(collection_name=collection),
            "exact": ExactMatchRetriever(),
            "bm25_chunks": BM25ChunksRetriever(),
            "bm25_cards": BM25CardsRetriever(),
            "dense_cards": DenseCardsRetriever(),
        }
        _retrievers[loop_id] = cached
    return cached


def enabled_retrievers() -> list[str]:
    names = ["dense_chunks"]
    if opt("USE_EXACT_MATCH", False):
        names.append("exact")
    if opt("USE_BM25", False):
        names += ["bm25_chunks", "bm25_cards"]
    if opt("USE_CARDS", False):
        names.append("dense_cards")
    return names


async def run_retrievers(analysis: QueryAnalysis, retrievers: dict | None = None) -> dict[str, list[Candidate]]:
    """Every enabled retriever in parallel; one that raises contributes []."""
    retrievers = retrievers or _retriever_set()
    names = enabled_retrievers()
    pools = {"bm25_cards": opt("V2_CARD_POOL"), "dense_cards": opt("V2_CARD_POOL"), "exact": 10}
    results = await asyncio.gather(
        *(retrievers[n].retrieve(analysis, int(pools.get(n, opt("V2_CHUNK_POOL")))) for n in names),
        return_exceptions=True,
    )
    out: dict[str, list[Candidate]] = {}
    for name, result in zip(names, results):
        if isinstance(result, BaseException):
            logger.warning(f"retriever {name} raised inside gather; continuing without it: {result!r}")
            out[name] = []
        else:
            out[name] = list(result or [])
    return out


# ── K: evidence top-up from inside one judgment ──────────────────────────────

def _chroma_collection():
    name = opt("DENSE_CHUNKS_COLLECTION", "") or None
    if not name:
        from app.retrieval.chroma_client import collection
        return collection
    from app.vectorstore.chroma_store import chroma_store
    return chroma_store.client.get_collection(name)


def top_up(judgment_id: str, query_vector, have: list[Candidate], need: int,
           sections: tuple[str, ...] = ()) -> list[Candidate]:
    """Up to `need` more passages of one judgment, by a within-judgment vector query.

    Used when fusion brought fewer than V2_RERANK_PASSAGES chunks of a judgment
    (always the case for an exact or card-only hit). Read-only.
    """
    if need <= 0 or query_vector is None:
        return []
    try:
        collection = _chroma_collection()
        clauses = [{"level": {"$eq": 2}}, {"file_id": {"$eq": judgment_id}}]
        if sections:
            clauses.append({"section_type": {"$in": list(sections)}})
        where = {"$and": clauses}
        available = len(collection.get(where=where, include=[]).get("ids") or [])
        if not available:
            return []
        response = collection.query(query_embeddings=[query_vector.tolist()],
                                    n_results=min(available, need * 4 + len(have)),
                                    where=where, include=["metadatas", "distances", "documents"])
    except Exception as e:
        logger.warning(f"evidence top-up failed for {judgment_id}: {e}")
        return []
    seen_nodes = {c.get("mongo_doc_id") for c in have}
    seen_ids = {c.get("vector_id") for c in have}
    found: list[Candidate] = []
    rows = list(zip(response["ids"][0], response["metadatas"][0], response["distances"][0],
                    response["documents"][0]))
    for distinct_pass in (True, False):
        for vector_id, meta, distance, doc in rows:
            if len(found) >= need:
                return found
            meta = meta or {}
            node = meta.get("node_id", vector_id)
            if vector_id in seen_ids or (distinct_pass and node in seen_nodes):
                continue
            found.append(Candidate(judgment_id=judgment_id, mongo_doc_id=node, vector_id=vector_id,
                                   section_type=meta.get("section_type", ""), heading=meta.get("heading", ""),
                                   chunk_index=meta.get("chunk_index", 0), text=doc or "",
                                   source="dense_chunks", rank=-1, score=float(1.0 - distance),
                                   scores={"topup": 1.0}))
            seen_ids.add(vector_id)
            seen_nodes.add(node)
    return found


def build_evidence(window: list[FusedJudgment], analysis: QueryAnalysis, query_vector) -> dict[str, list[Candidate]]:
    per = int(opt("V2_RERANK_PASSAGES"))
    preferred = SECTION_PREFERENCE.get(analysis.get("query_type") or "", ()) \
        if opt("USE_SECTION_WEIGHTING", False) else ()
    include_card = bool(opt("V2_RERANK_INCLUDE_CARD", False))
    evidence: dict[str, list[Candidate]] = {}
    for item in window:
        chosen = select_evidence(item, per, preferred, include_card)
        chunks = [c for c in chosen if c.get("mongo_doc_id")]
        if len(chunks) < per:
            extra = top_up(item["judgment_id"], query_vector, chunks, per - len(chunks))
            chosen = chunks + extra + [c for c in chosen if not c.get("mongo_doc_id")]
            chunks = chunks + extra
        if preferred and chunks and not any(c.get("section_type") in preferred for c in chunks):
            extra = top_up(item["judgment_id"], query_vector, chunks, 1, sections=preferred)
            if extra:
                index = max(i for i, c in enumerate(chosen) if c.get("mongo_doc_id"))
                chosen[index] = extra[0]
        evidence[item["judgment_id"]] = chosen
    return evidence


# ── Embedding: once per text per search ──────────────────────────────────────

def embed_texts(texts: list[str]) -> dict:
    """{text: vector} for every distinct non-empty text, in ONE batched encode.

    The whole search shares these: dense_chunks, dense_cards (via
    analysis["_vectors"]), the evidence top-up, the facet evidence and the
    section search. Before, the query was embedded ~4 times per search, and
    each encode now queues for one of the process-wide inference slots
    (embedding_generator.inference_slot), so one batched call holds one slot
    once. Same prefix and normalisation as query_embedder.embed_query, so the
    vectors are interchangeable with it.
    """
    from app.retrieval import query_embedder

    distinct = list(dict.fromkeys(t for t in texts if t and t.strip()))
    if not distinct:
        return {}
    matrix = query_embedder._generator.model.encode(
        [query_embedder.QUERY_INSTRUCTION_PREFIX + t for t in distinct],
        normalize_embeddings=True, show_progress_bar=False)
    last_debug["embed_calls"] = last_debug.get("embed_calls", 0) + 1
    return {text: matrix[i] for i, text in enumerate(distinct)}


def score_pairs(pairs: list[tuple[str, str]]) -> list[float] | None:
    """Cross-encoder logits for (query, passage) pairs with DIFFERENT queries, one model call.

    rerank_judgments takes a single query, so scoring four facets through it
    costs four model calls (four waits for an inference slot). This scores all
    facet pairs in one batch. Uses reranker.score_pairs when the reranker
    provides it; otherwise the reranker's loaded CrossEncoder (torch backend)
    inside embedding_generator.inference_slot — the same model, logits and
    slot discipline as Reranker.score. None when reranking is disabled or the
    model is unavailable (the caller fails closed).
    """
    from app.retrieval import reranker

    if not pairs or not reranker.is_enabled():
        return None
    provided = getattr(reranker, "score_pairs", None)
    last_debug["rerank_calls"] = last_debug.get("rerank_calls", 0) + 1
    if callable(provided):
        return provided(pairs)
    model = reranker._reranker.model      # loads under the reranker's own lock; None if unavailable
    if model is None:
        return None
    import torch

    from app.embeddings.embedding_generator import inference_slot

    identity = torch.nn.Identity()
    with inference_slot():
        for attempt in (
            lambda: model.predict(pairs, show_progress_bar=False, activation_fn=identity),
            lambda: model.predict(pairs, show_progress_bar=False, activation_fct=identity),
        ):
            try:
                return [float(s) for s in attempt()]
            except TypeError:
                continue
    logger.error("cross-encoder predict accepts no identity activation; no scores")
    return None


# ── Narrative (case-description) path ────────────────────────────────────────
#
# Why facets instead of the whole story
# -------------------------------------
# The cross-encoder (MiniLM, ms-marco, max_length 512) was trained on short
# queries. A 190-token description leaves ~320 tokens of a 480-token passage
# and asks one passage to match facts, both sides and the court's view at once;
# correct matches scored 0.02-0.04. Each facet is instead paired with the
# section that discusses it (facts -> FACTS, each side -> ARGUMENTS, the court's
# view -> ANALYSIS_RATIO/LEGAL_ISSUES), keeping the query side short, and a
# judgment's relevance aggregates its facet scores (narrative_relevance).

FACET_SECTIONS: dict[str, tuple[str, ...]] = {
    "facts": ("FACTS",),
    "claimant": ("ARGUMENTS",),
    "respondent": ("ARGUMENTS",),
    "court_view": ("ANALYSIS_RATIO", "LEGAL_ISSUES"),
}
# The cross-encoder reads at most this many words of a facet, so the passage
# keeps (nearly) all of its 512-token window.
FACET_QUERY_WORDS = 60


def narrative_facets(analysis: QueryAnalysis) -> list[tuple[str, str]]:
    """[(facet, text)] for the text facets present, in FACET_SECTIONS order."""
    if not analysis.get("is_narrative"):
        return []
    facets = analysis.get("facets") or {}
    return [(name, str(facets[name]).strip()) for name in FACET_SECTIONS
            if isinstance(facets.get(name), str) and str(facets[name]).strip()]


def facet_query(text: str) -> str:
    words = text.split()
    return " ".join(words[:FACET_QUERY_WORDS])


def _window_chunks(judgment_ids: list[str]) -> dict[str, list[dict]]:
    """Every section chunk (level 2) of the window's judgments, with its vector — one Chroma call."""
    import numpy as np

    if not judgment_ids:
        return {}
    response = _chroma_collection().get(
        where={"$and": [{"level": {"$eq": 2}}, {"file_id": {"$in": list(judgment_ids)}}]},
        include=["embeddings", "metadatas", "documents"])
    out: dict[str, list[dict]] = {}
    embeddings = response.get("embeddings")
    for i, vector_id in enumerate(response.get("ids") or []):
        meta = (response["metadatas"][i] or {})
        if embeddings is None or embeddings[i] is None:
            continue
        out.setdefault(meta.get("file_id", ""), []).append({
            "vector_id": vector_id, "meta": meta, "text": (response["documents"][i] or ""),
            "vector": np.asarray(embeddings[i], dtype="float32")})
    return out


def build_facet_evidence(window: list[FusedJudgment], analysis: QueryAnalysis,
                         vectors: dict) -> dict[str, list[Candidate]]:
    """Per judgment, the best passage for each facet from that facet's sections.

    Best = highest cosine between the facet's vector and the chunk's stored
    vector (both L2-normalised), within the facet's sections; a judgment with no
    chunk of those sections (the parser does not always find ARGUMENTS) falls
    back to its best chunk overall, so every facet is still scored. Each passage
    is its own dict tagged with ``facet``, so a chunk chosen by two facets is
    scored twice without the scores overwriting each other. Read-only.
    """
    import numpy as np

    facets = [(name, text, vectors.get(text)) for name, text in narrative_facets(analysis)]
    facets = [f for f in facets if f[2] is not None]
    if not facets or not window:
        return {}
    chunks = _window_chunks([item["judgment_id"] for item in window])
    evidence: dict[str, list[Candidate]] = {}
    for item in window:
        jid = item["judgment_id"]
        rows = chunks.get(jid) or []
        if not rows:
            continue
        matrix = np.stack([r["vector"] for r in rows])
        chosen: list[Candidate] = []
        for name, _text, vector in facets:
            sims = matrix @ np.asarray(vector, dtype="float32")
            allowed = [i for i, r in enumerate(rows) if r["meta"].get("section_type") in FACET_SECTIONS[name]]
            pool = allowed or list(range(len(rows)))
            best = max(pool, key=lambda i: sims[i])
            row = rows[best]
            meta = row["meta"]
            chosen.append(Candidate(  # type: ignore[typeddict-unknown-key]
                judgment_id=jid, mongo_doc_id=meta.get("node_id", row["vector_id"]), vector_id=row["vector_id"],
                section_type=meta.get("section_type", ""), heading=meta.get("heading", ""),
                chunk_index=meta.get("chunk_index", 0), text=row["text"], source="dense_chunks", rank=-1,
                score=float(sims[best]), scores={"facet_cos": float(sims[best])},
                facet=name, facet_section_match=bool(allowed)))
        evidence[jid] = chosen
    return evidence


def narrative_relevance(facet_scores: dict[str, float], mode: str = "mean_top2") -> float:
    """One judgment's relevance from its per-facet cross-encoder relevances.

    "mean_top2" (default): the mean of the two best facets. A real match agrees
    on at least two parts of a description (its facts AND the court's view, or
    one side's case); an out-of-archive story in the same area typically
    matches one generic part (a land dispute's facts) and nothing else. With a
    single facet it is that facet. "max" and "mean" are kept for measurement.
    """
    values = sorted(facet_scores.values(), reverse=True)
    if not values:
        return 0.0
    if mode == "max" or len(values) == 1:
        return values[0]
    if mode == "mean":
        return sum(values) / len(values)
    return (values[0] + values[1]) / 2


def rerank_facets(analysis: QueryAnalysis, evidence: dict[str, list[Candidate]]) -> dict[str, dict] | None:
    """Cross-encode each facet against its passages; aggregate per judgment.

    All facet <-> passage pairs of all judgments go through the cross-encoder
    in ONE call (score_pairs). Each scored passage gains scores["rerank"] /
    scores["relevance"] as rerank_judgments would write them. Returns None when
    the model is disabled or unavailable — the caller decides how to fail.
    """
    from app.retrieval.reranker import _sigmoid

    mode = str(opt("V2_NARRATIVE_AGGREGATE", "mean_top2"))
    queries = {name: facet_query(text) for name, text in narrative_facets(analysis)}
    flat = [(jid, p) for jid, passages in evidence.items() for p in passages
            if p.get("facet") in queries and (p.get("text") or "").strip()]
    if not flat:
        return None
    started = time.perf_counter()
    logits = score_pairs([(queries[p["facet"]], p["text"]) for _, p in flat])
    if logits is None or len(logits) != len(flat):
        return None
    elapsed = (time.perf_counter() - started) * 1000
    per_judgment: dict[str, dict] = {}
    for (jid, passage), logit in zip(flat, logits):
        relevance = _sigmoid(logit)
        passage.setdefault("scores", {})
        passage["scores"]["rerank"] = logit
        passage["scores"]["relevance"] = relevance
        entry = per_judgment.setdefault(jid, {"facets": {}, "best": None, "logit": float("-inf")})
        name = passage["facet"]
        entry["facets"][name] = max(entry["facets"].get(name, 0.0), relevance)
        if logit > entry["logit"]:
            entry["logit"], entry["best"] = logit, passage
    for entry in per_judgment.values():
        entry["relevance"] = narrative_relevance(entry["facets"], mode)
    last_debug["facet_rerank_stats"] = {"pairs": len(flat), "ms": round(elapsed, 1), "calls": 1,
                                        "ms_per_pair": round(elapsed / len(flat), 1)}
    return per_judgment


async def card_outcomes(judgment_ids: list[str]) -> dict[str, str]:
    """case_cards.outcome for the given judgments ({} on any failure). Read-only."""
    if not judgment_ids:
        return {}
    try:
        from app.database import connect_db, db

        if db.database is None:
            await connect_db()
        return {c["judgment_id"]: c.get("outcome") or "unknown"
                async for c in db.database.case_cards.find(
                    {"judgment_id": {"$in": list(judgment_ids)}}, {"_id": 0, "judgment_id": 1, "outcome": 1})}
    except Exception as e:
        logger.warning(f"card outcomes unavailable, no outcome signal: {e}")
        return {}


CONFIDENCE_ORDER = {"related": 0, "medium": 1, "high": 2}


def cap_confidence(label: str, cap: str) -> str:
    """The lower of two confidence labels ("related" < "medium" < "high")."""
    if cap not in CONFIDENCE_ORDER:
        return label
    return label if CONFIDENCE_ORDER.get(label, 0) <= CONFIDENCE_ORDER[cap] else cap


# ── Entry point ──────────────────────────────────────────────────────────────

LEXICAL_LEAD_RETRIEVERS = ("bm25_chunks", "bm25_cards")


def lexical_lead(lists: dict[str, list[Candidate]], judgment_id: str) -> float | None:
    """How far ahead of every other judgment both keyword indexes put this one.

    Per BM25 retriever: (best score of this judgment - best score of any other
    judgment) / best score of this judgment, i.e. 0.5 = it outscores the
    runner-up by half its own score. Negative when another judgment is ahead.
    Returns the smaller of the two leads, or None when either index has no
    score for it. Independent of the cross-encoder: it says the description's
    own words are specific to this judgment's text and its case card.
    """
    leads = []
    for name in LEXICAL_LEAD_RETRIEVERS:
        best: dict[str, float] = {}
        for c in lists.get(name) or []:
            score = c.get("score")
            if score is None:
                continue
            jid = c.get("judgment_id")
            best[jid] = max(best.get(jid, float("-inf")), float(score))
        mine = best.pop(judgment_id, None)
        if mine is None or mine <= 0:
            return None
        other = max(best.values(), default=0.0)
        leads.append((mine - other) / mine)
    return min(leads) if leads else None


def _agreement_gate(rows: list[dict], floor: float, confident: float | None = None,
                    lexical_min: float | None = None) -> list[dict]:
    """Decide what to show when the LLM judge is not available.

    A single threshold on cross-encoder relevance cannot separate a real answer
    from a plausible wrong one on this corpus. Measured on dev positives plus
    the owner's real out-of-corpus queries, the top judgment's relevance was:

        real answers                0.242 0.195 0.167 0.152 0.077 0.054 ...
        no answer in the corpus     0.166 0.160 ("imran khan bail case") 0.099

    — interleaved, so any cut either fabricates or refuses. What did separate
    them in that band was retriever agreement: real answers were ranked first
    by 3-4 of the 4 independent retrievers, the coincidental matches by 0-2.
    Different retrievers fail on different words, so agreement is evidence the
    match is about the question and not about a shared surname or phrase.

    The rule, applied to the TOP fused judgment:
        relevance >= V2_CONFIDENT_RELEVANCE (0.25)          -> show
        floor <= relevance < 0.25 and n_first >= V2_AGREEMENT_MIN (3) -> show
        otherwise                                             -> abstain entirely

    If the top judgment fails, nothing is shown — a lower judgment is NEVER
    promoted into its place. The cross-encoder overrates surface-similar
    passages: for one out-of-corpus query it scored an unrelated judgment
    further down the list at 0.99. Promoting it would turn a correct refusal
    into a confident wrong answer.

    Below the top, additional judgments are shown only when confidently
    relevant (>= 0.25); they cannot be "first" in any list, so the agreement
    signal does not apply to them.

    Case descriptions have a second way through (lexical_min, from
    V2_NARRATIVE_LEXICAL_LEAD): the top judgment's lexical_lead >= lexical_min
    and n_first >= V2_AGREEMENT_MIN, whatever its cross-encoder relevance. On
    narrative_dev, 7 of 9 refused descriptions had the right judgment first
    with the cross-encoder at ~0: their facet passages came from mislabelled
    sections (a FACTS "section" that is a table of dates). Widening the
    passage pools lifted near-domain out-of-archive stories just as much.

    Chosen on 20 reachable dev positives and 40 negatives: directional, not
    proven. Re-measure at full corpus; the LLM judge replaces this gate when
    it is enabled.
    """
    if not rows:
        return []

    confident = float(opt("V2_CONFIDENT_RELEVANCE", 0.25)) if confident is None else float(confident)
    agreement = int(opt("V2_AGREEMENT_MIN", 3))

    def top_passes(row: dict) -> bool:
        if row["pinned"] or row["relevance"] >= confident:
            return True
        if row.get("n_first", 0) < agreement:
            return False
        if row["relevance"] >= floor:
            return True
        lead = row.get("lexical_lead")
        return lexical_min is not None and lead is not None and lead >= lexical_min

    first, rest = rows[0], rows[1:]
    if not top_passes(first):
        return [r for r in rows if r["pinned"]]  # an exact case-number hit is never refused

    return [first] + [r for r in rest if r["pinned"] or r["relevance"] >= confident]


TOO_BROAD_MESSAGE = (
    "This query is too general to match particular judgments: every judgment in "
    "the archive is a legal dispute. Describe the facts, the parties, the statute "
    "or the legal question you are researching."
)

# How far down the fused list a category browse looks for judgments that are
# genuinely about the category. The lexical grounding test is cheap, so the
# window can be wide.
CATEGORY_WINDOW = 30


async def _browse_category(raw_query, category, analysis, timings, mark,
                           top_k_judgments, top_k_sections) -> dict:
    """List the judgments that are about one category, instead of answering.

    Search runs on the category's own vocabulary (the free-tier stand-in for the
    LLM rewrite), then every candidate judgment must literally contain one of
    the category's phrases somewhere in its text. Judgments are ordered by how
    many distinct category phrases they contain, then by fused rank — a case
    that discusses dower, nikah and the husband's heirs is more of a family
    matter than one that mentions a widow in passing.

    The cross-encoder is not consulted: it is exactly what failed on these
    queries. Every result is labelled "related", and the response carries a
    notice saying this is a browse, not an answer.
    """
    from app.database import db
    from app.retrieval import categories
    from app.retrieval.chroma_client import _root_nodes_by_judgment
    from app.retrieval.node_searcher import search_all_judgments
    from app.retrieval.query_embedder import embed_query

    spec = categories.CATEGORIES[category]
    terms = categories.search_text(category)
    browse = dict(analysis)
    browse["rewrite"] = terms
    browse["expansions"] = []

    lists = await run_retrievers(browse)
    fused = fuse(lists, mode="rrf")[:CATEGORY_WINDOW]
    mark("category_retrieve")

    ids = [item["judgment_id"] for item in fused]
    texts: dict[str, list[str]] = {jid: [] for jid in ids}
    if ids:
        async for node in db.database.nodes.find({"pdf_id": {"$in": ids}}, {"pdf_id": 1, "text": 1}):
            texts.setdefault(node["pdf_id"], []).append(node.get("text") or "")

    grounded = []
    for position, item in enumerate(fused):
        found = categories.matched_phrases(category, "\n".join(texts.get(item["judgment_id"], [])))
        if found:
            grounded.append((len(found), position, item, found))
    grounded.sort(key=lambda g: (-g[0], g[1]))
    kept = grounded[:top_k_judgments]
    mark("category_ground")

    if not kept:
        out = _empty(analysis, timings)
        out["message"] = (
            f"No judgment in the archive deals with {spec['label']} matters. "
            "The archive holds reported judgments of the Supreme Court of Pakistan."
        )
        return out

    roots = await asyncio.to_thread(_root_nodes_by_judgment)
    parent_results = [{
        "judgment_id": item["judgment_id"],
        "mongo_doc_id": roots.get(item["judgment_id"], {}).get("node_id", ""),
        "heading": roots.get(item["judgment_id"], {}).get("heading", "") or item.get("heading", ""),
        "score": 0.0,
        "confidence": "related",
    } for _, _, item, _ in kept]

    kept_ids = [item["judgment_id"] for _, _, item, _ in kept]
    candidates = [c for _, _, item, _ in kept for c in (item.get("evidence") or [])]
    try:
        vector = await asyncio.to_thread(embed_query, terms)
        stage2 = await asyncio.to_thread(
            search_all_judgments, vector, kept_ids, top_k_sections,
            [c for c in candidates if c.get("mongo_doc_id")],
        )
    except Exception as e:
        logger.warning(f"category section search failed: {e}")
        from app.retrieval.node_searcher import sections_from_candidates
        stage2 = sections_from_candidates(candidates, kept_ids, top_k_sections)
    mark("sections")

    return {
        "analysis": analysis,
        "parent_results": parent_results,
        "stage2_results": stage2,
        "candidates": candidates,
        "reranked": False,
        "judge_used": False,
        # Shown under each case: why it counts as part of the category.
        "reasons": {item["judgment_id"]: "Mentions " + ", ".join(found[:5])
                    for _, _, item, found in kept},
        "no_results": False,
        "notice": (
            f"This is a broad query, so these are judgments that deal with "
            f"{spec['label']} matters rather than an answer to one question. "
            "For a precise answer, describe the facts or the legal issue."
        ),
        "timings_ms": {k: round(v, 1) for k, v in timings.items()},
    }


def _empty(analysis, timings, reranked=False, judge_used=False, candidates=None) -> dict:
    return {"analysis": analysis, "parent_results": [], "stage2_results": {},
            "candidates": candidates or [], "reranked": reranked, "judge_used": judge_used,
            "reasons": {}, "no_results": True, "timings_ms": {k: round(v, 1) for k, v in timings.items()}}


async def retrieve_v2(raw_query: str, top_k_judgments: int = 5, top_k_sections: int = 3) -> dict:
    """Rank judgments for one query; see the module docstring for the contract."""
    from app.retrieval import reranker

    timings: dict[str, float] = {}
    clock = [time.perf_counter()]
    last_debug.clear()

    def mark(stage: str) -> None:
        now = time.perf_counter()
        timings[stage] = (now - clock[0]) * 1000
        clock[0] = now

    raw_query = raw_query or ""
    # Transliterated terms in the judgments' spelling ("nikkah" -> "nikah"),
    # before anything reads the query; see app.retrieval.spelling.
    if opt("NORMALISE_SPELLING", True):
        from app.retrieval.spelling import normalise
        raw_query = normalise(raw_query)
    analysis = await _analysis(raw_query)
    mark("analysis")
    if not raw_query.strip():
        return _empty(analysis, timings)

    # Broad queries take their own path (see app.retrieval.categories): a
    # phrase like "legal dispute" is refused with a request for specifics, and
    # a category like "family dispute" browses the judgments that are about it.
    from app.retrieval import categories

    kind, category = categories.classify(raw_query)
    if kind == "too_broad":
        mark("too_broad")
        out = _empty(analysis, timings)
        out["message"] = TOO_BROAD_MESSAGE
        return out
    if kind == "category":
        return await _browse_category(
            raw_query, category, analysis, timings, mark, top_k_judgments, top_k_sections
        )

    from app.retrieval.dense_chunks import query_texts

    # Narrative: a case description with facets to search part by part.
    is_narrative = bool(analysis.get("is_narrative"))
    # The facet path needs a story with parts: with a single text facet (a
    # loose description, often one sentence and a question) the facet IS the
    # whole query, and the whole-query path reads it against the best passages
    # of any section instead of one section.
    narrative = (is_narrative and bool(opt("NARRATIVE_FACETS", True))
                 and len(narrative_facets(analysis)) >= int(opt("V2_NARRATIVE_MIN_FACETS", 2)))

    # Embed every text this search needs exactly once.
    main_text = analysis.get("cleaned") or raw_query
    try:
        vectors = await asyncio.to_thread(embed_texts, [main_text] + query_texts(analysis))
    except Exception as e:
        logger.warning(f"query embedding failed; dense retrievers embed on their own, no top-up: {e}")
        vectors = {}
    query_vector = vectors.get(main_text)
    mark("embed")

    view = dict(analysis)
    view["_vectors"] = vectors   # internal: never returned or logged
    lists = await run_retrievers(view)  # type: ignore[arg-type]
    mark("retrieve")

    try:
        fused = fuse(lists, mode="rrf" if opt("USE_FUSION", False) else "union")
    except Exception as e:
        logger.warning(f"fusion failed, using dense order: {e}")
        fused = fuse({"dense_chunks": lists.get("dense_chunks") or []}, mode="union")
    mark("fusion")
    if not fused:
        return _empty(analysis, timings)

    # Outcome soft signal (narratives that state the SC outcome): a fraction of
    # one vote for judgments whose card records the same outcome; never a filter.
    outcome_sc = (analysis.get("facets") or {}).get("outcome_sc") if is_narrative else None
    if outcome_sc and opt("V2_OUTCOME_SIGNAL", True):
        head = fused[: int(opt("V2_RERANK_JUDGMENTS")) * 2]
        outcomes = await card_outcomes([i["judgment_id"] for i in head])
        fused = apply_outcome_signal(head, outcome_sc, outcomes, share=opt("V2_OUTCOME_VOTE_SHARE", None)) \
            + fused[len(head):]
        mark("outcome")

    window = fused[: int(opt("V2_RERANK_JUDGMENTS"))]
    if narrative:
        evidence = await asyncio.to_thread(build_facet_evidence, window, analysis, vectors)
        if not evidence:   # no chunk vectors for the window: the whole-query path
            narrative = False
    if not narrative:
        evidence = await asyncio.to_thread(build_evidence, window, analysis, query_vector)
    candidates = [c for passages in evidence.values() for c in passages]
    mark("evidence")

    from app.retrieval.reranker import is_enabled as rerank_enabled

    rerank_failed = False
    try:
        if narrative:
            judged = await asyncio.to_thread(rerank_facets, analysis, evidence)
        else:
            last_debug["rerank_calls"] = last_debug.get("rerank_calls", 0) + 1
            judged = await asyncio.to_thread(reranker.rerank_judgments, raw_query.strip(), evidence)
    except Exception as e:
        logger.warning(f"cross-encoder failed: {e}")
        judged, rerank_failed = None, True
    if judged is None and rerank_enabled():
        rerank_failed = True   # enabled but produced nothing: the model is unavailable
    reranked = judged is not None
    mark("rerank")

    # Order: pinned exact hits by exact score, then cross-encoder relevance, fused order breaking ties.
    position = {item["judgment_id"]: i for i, item in enumerate(window)}
    rows = []
    for item in window:
        jid = item["judgment_id"]
        if reranked:
            relevance = judged.get(jid, {}).get("relevance", 0.0)
        else:
            dense = [c.get("score", 0.0) for c in item.get("evidence") or [] if c.get("source") == "dense_chunks"]
            relevance = max(0.0, min(1.0, max(dense, default=0.0)))
        if item.get("pinned"):
            relevance = max(relevance, float(item.get("exact_score") or 0.0))
        ranks = item.get("ranks") or {}
        row = {"judgment_id": jid, "relevance": float(relevance), "pinned": bool(item.get("pinned")),
               # A case number the user typed — the one pin a narrative keeps "high".
               "case_number": bool(item.get("pinned")) and str(item.get("exact_reason", "")).startswith("case number"),
               "heading": item.get("heading", ""), "rrf": item.get("rrf", 0.0),
               # How many independent retrievers put this judgment first.
               "n_first": sum(1 for r in ranks.values() if r == 1),
               "n_lists": len(ranks)}
        if is_narrative:
            row["lexical_lead"] = lexical_lead(lists, jid)
        if narrative and reranked:
            row["facet_relevance"] = dict(judged.get(jid, {}).get("facets") or {})
        if item.get("outcome_match"):
            row["outcome_match"] = True
        rows.append(row)
    if reranked and str(opt("V2_FINAL_ORDER")).lower() == "rerank":
        rows.sort(key=lambda r: (not r["pinned"], -r["relevance"], position[r["judgment_id"]]))

    # v2 has its own floor. The live v1 path was calibrated at 0.20 over a
    # top-40-chunk rerank; v2 gates on max relevance over each judgment's best
    # passages, where the dev sweep put every negative under 0.006 and all but
    # two positives above 0.05. Sharing one key would force a choice between
    # breaking v1's abstention and refusing a quarter of v2's real answers.
    floor = float(opt("V2_RELEVANCE_THRESHOLD", 0.02))
    # Facet relevances are on a different footing from whole-query ones (short
    # query vs the matching section), so narratives have their own two cuts.
    gate_confident = float(opt("V2_CONFIDENT_RELEVANCE", 0.25))
    if narrative and reranked:
        floor = float(opt("V2_NARRATIVE_RELEVANCE_THRESHOLD", floor))
        gate_confident = float(opt("V2_NARRATIVE_CONFIDENT_RELEVANCE", gate_confident))
    lexical_min = opt("V2_NARRATIVE_LEXICAL_LEAD") if is_narrative and reranked else None
    lexical_min = None if lexical_min is None else float(lexical_min)
    reasons: dict[str, str] = {}
    judge_used = False
    judge_relevant: dict[str, bool] | None = None
    if opt("USE_LLM_JUDGE", False) and rows:
        try:
            from app.retrieval import judge

            top_n = int(opt("JUDGE_TOP_N"))
            verdict = await judge.judge(raw_query, rows[:top_n], evidence)
            if verdict.get("used"):
                judge_used = True
                order = {jid: i for i, jid in enumerate(verdict["ranking"])}
                head = sorted(rows[:top_n], key=lambda r: (not r["pinned"], order.get(r["judgment_id"], 10 ** 6)))
                rows = head + rows[top_n:]
                judge_relevant = verdict.get("relevant") or {}
                reasons = verdict.get("reasons") or {}
        except Exception as e:
            logger.warning(f"judge failed, keeping reranker order: {e}")
    mark("judge")

    last_debug.update(rows=[dict(r) for r in rows], lists={k: len(v) for k, v in lists.items()},
                      fused=[i["judgment_id"] for i in fused], judge_relevant=judge_relevant,
                      rerank_stats=dict(reranker.last_stats), analysis=analysis,
                      narrative=narrative, rerank_failed=rerank_failed)

    # A: abstention.
    if rerank_failed:
        # FAIL CLOSED: the cross-encoder is the gate. Without it nothing
        # separates a real match from a plausible wrong one, so only what the
        # user named by case number is shown.
        logger.warning("cross-encoder unavailable: abstaining (case-number hits only)")
        kept = [r for r in rows if r["case_number"]]
    elif not reranked:
        kept = rows  # reranking switched off by the operator: nothing to abstain on
    elif judge_used and judge_relevant is not None:
        kept = [r for r in rows if r["pinned"] or judge_relevant.get(r["judgment_id"], False)]
        if not kept:
            kept = _agreement_gate(rows, floor, gate_confident, lexical_min)
    else:
        kept = _agreement_gate(rows, floor, gate_confident, lexical_min)
    kept = kept[:top_k_judgments]
    if not kept:
        mark("abstain")
        return _empty(analysis, timings, reranked, judge_used, candidates)

    from app.retrieval.chroma_client import _root_nodes_by_judgment
    from app.retrieval.node_searcher import search_all_judgments

    try:
        roots = await asyncio.to_thread(_root_nodes_by_judgment)
    except Exception as e:
        logger.warning(f"root node lookup failed: {e}")
        roots = {}
    confident = gate_confident
    # Confidence policy for case descriptions (owner's choice): without the LLM
    # judge the top result of a narrative is at most NARRATIVE_MAX_CONFIDENCE
    # ("medium" = "Possible match - verify"). Measured before this change, 2 of
    # 7 out-of-archive descriptions passed both the cross-encoder and the
    # agreement gate on a same-area case, one at 0.361 ("high"). A case number
    # the user typed is verified by construction and keeps "high".
    cap = str(opt("NARRATIVE_MAX_CONFIDENCE", "medium")) if is_narrative and not judge_used else ""

    def label(i: int, r: dict) -> str:
        base = ("high" if r["pinned"]
                else ("high" if r["relevance"] >= confident else "medium") if i == 0
                else "related")
        return cap_confidence(base, cap) if cap and not r["case_number"] else base

    parent_results = [{
        "judgment_id": r["judgment_id"],
        "mongo_doc_id": roots.get(r["judgment_id"], {}).get("node_id", ""),
        "heading": roots.get(r["judgment_id"], {}).get("heading", "") or r["heading"],
        "score": r["relevance"],
        # Fusion decides the order and the cross-encoder the score, so raw
        # scores are not monotonic down the list. A coarse label is what a
        # reader can actually use: is this a strong match or one to verify?
        #
        # Only the top judgment earns "high"/"medium". Results below it are
        # labelled "related": on dev, 11 of 12 secondaries the cross-encoder
        # scored >= 0.25 were not the labelled answer (some genuinely related,
        # some surface matches on a shared word), and without the LLM judge
        # nothing distinguishes the two. An exact case-number or party hit is
        # verified by construction, so it stays "high" wherever it sits.
        "confidence": label(i, r),
    } for i, r in enumerate(kept)]

    ids = [r["judgment_id"] for r in kept]
    chunk_evidence = [c for c in candidates if c.get("mongo_doc_id")]
    try:
        if query_vector is None:
            raise RuntimeError("no query vector")
        stage2 = await asyncio.to_thread(search_all_judgments, query_vector, ids, top_k_sections, chunk_evidence)
    except Exception as e:
        logger.warning(f"section search failed, using evidence only: {e}")
        from app.retrieval.node_searcher import sections_from_candidates
        stage2 = sections_from_candidates(chunk_evidence, ids, top_k_sections)
    mark("sections")

    return {
        "analysis": analysis,
        "parent_results": parent_results,
        "stage2_results": stage2,
        "candidates": candidates,
        "reranked": reranked,
        "judge_used": judge_used,
        "reasons": {jid: reasons[jid] for jid in ids if jid in reasons},
        "no_results": False,
        "timings_ms": {k: round(v, 1) for k, v in timings.items()},
    }


if __name__ == "__main__":
    from app.database import connect_db

    logger.remove()
    logger.add(sys.stderr, level="WARNING")
    CA_5Q = "5a14105d-8a45-413c-8c93-26d6301cf028"

    async def main() -> None:
        await connect_db()  # same loop as the retrievers (motor)
        OVERRIDES.update(USE_EXACT_MATCH=True, USE_BM25=True, USE_CARDS=True, USE_FUSION=True,
                         USE_LLM_JUDGE=False)

        out = await retrieve_v2("general elections 2013 National Assembly seat NA-266 Nasirabad Jaffarabad", 3, 2)
        assert set(out) == {"analysis", "parent_results", "stage2_results", "candidates", "reranked",
                            "judge_used", "reasons", "no_results", "timings_ms"}, set(out)
        assert not out["no_results"] and out["parent_results"][0]["judgment_id"] == CA_5Q, out["parent_results"]
        top = out["parent_results"][0]
        assert top["mongo_doc_id"] and top["heading"] and 0.0 <= top["score"] <= 1.0
        assert all(out["stage2_results"][p["judgment_id"]] for p in out["parent_results"])
        section = out["stage2_results"][CA_5Q][0]
        assert {"judgment_id", "mongo_doc_id", "section_type", "heading", "score", "matched_chunk"} <= set(section)
        assert out["reranked"] and len(out["candidates"]) <= 30 * 4
        print(f"OK: in-corpus query -> {top['judgment_id'][:8]} {top['score']:.3f}; timings {out['timings_ms']}")

        out = await retrieve_v2("C.A. 5-Q/2014", 3, 2)
        assert out["parent_results"][0]["judgment_id"] == CA_5Q and out["parent_results"][0]["score"] == 1.0
        print("OK: exact case number pinned at relevance 1.0")

        out = await retrieve_v2("how do I make chicken biryani at home", 3, 2)
        assert out["no_results"] and out["parent_results"] == [] and out["stage2_results"] == {}
        print("OK: out-of-corpus query abstains")

        # A retriever raising inside gather must not kill the search.
        class Boom:
            name = "bm25_chunks"

            async def retrieve(self, analysis, k):
                raise RuntimeError("simulated retriever crash")

        retrievers = dict(_retriever_set())
        retrievers["bm25_chunks"] = Boom()
        lists = await run_retrievers(await _analysis("seniority of police officers"), retrievers)
        assert lists["bm25_chunks"] == [] and lists["dense_chunks"], lists.keys()
        print("OK: a retriever raising inside gather contributes [] and the others still return")

        out = await retrieve_v2("", 3, 2)
        assert out["no_results"]

        # ── Case descriptions ────────────────────────────────────────────────
        assert narrative_relevance({"facts": 0.9, "court_view": 0.1, "claimant": 0.0}) == 0.5
        assert narrative_relevance({"facts": 0.9, "court_view": 0.1}, "max") == 0.9
        assert narrative_relevance({"facts": 0.4}) == 0.4 and narrative_relevance({}) == 0.0
        assert cap_confidence("high", "medium") == "medium" and cap_confidence("related", "medium") == "related"
        assert cap_confidence("high", "") == "high"

        # The baseline party misfire: institutional words no longer pin a case.
        misfire = ("My client is a police constable in Punjab who was dismissed after a departmental inquiry "
                   "into absence from duty. He says the inquiry officer never recorded his evidence. The "
                   "Inspector General of Police said the dismissal was proper and his departmental appeal "
                   "was rejected.")
        out = await retrieve_v2(misfire, 5, 2)
        assert not any(r["pinned"] for r in last_debug["rows"]), last_debug["rows"][:2]
        assert all(p["confidence"] != "high" for p in out["parent_results"]), out["parent_results"]
        print(f"OK: party misfire not pinned ({len(out['parent_results'])} shown)")

        # A detailed description finds its judgment, labelled at most "medium" without the judge.
        story = ("I was appointed on contract as a Deputy District Attorney in Sindh. We asked the High Court "
                 "to regularise our services and it allowed our constitutional petitions, but the province "
                 "appealed saying the High Court had overstepped its jurisdiction.")
        out = await retrieve_v2(story, 5, 2)
        assert out["analysis"]["is_narrative"] and last_debug["narrative"], "facet path expected"
        assert "_vectors" not in out["analysis"], "internal vectors must never leave retrieve_v2"
        assert out["parent_results"] and out["parent_results"][0]["judgment_id"].startswith("2df8aea1")
        assert out["parent_results"][0]["confidence"] == "medium", out["parent_results"][0]
        assert last_debug["rows"][0].get("facet_relevance"), last_debug["rows"][0]
        print(f"OK: narrative -> {out['parent_results'][0]['judgment_id'][:8]} 'medium', "
              f"facets {last_debug['rows'][0]['facet_relevance']}")

        # ...but a case number typed inside a description keeps "high".
        out = await retrieve_v2(story + " The case is C.A. 5-Q/2014.", 5, 2)
        assert out["parent_results"][0]["judgment_id"] == CA_5Q and out["parent_results"][0]["confidence"] == "high"
        print("OK: case number inside a narrative stays pinned and 'high'")

        # Fail closed: a cross-encoder that raises means no ungated results.
        from app.retrieval import reranker as _rr

        original_rerank = _rr.rerank_judgments

        def broken(*_a, **_k):
            raise RuntimeError("simulated cross-encoder crash")

        _rr.rerank_judgments = broken
        original_pairs = globals()["score_pairs"]
        globals()["score_pairs"] = broken
        try:
            out = await retrieve_v2(story, 5, 2)
            assert out["no_results"] and last_debug["rerank_failed"], out["parent_results"]
            out = await retrieve_v2("general elections 2013 National Assembly seat NA-266 Nasirabad Jaffarabad", 3, 2)
            assert out["no_results"], "short path must fail closed too"
            out = await retrieve_v2("C.A. 5-Q/2014", 3, 2)
            assert out["parent_results"][0]["judgment_id"] == CA_5Q, "a case-number hit survives a dead reranker"
        finally:
            _rr.rerank_judgments = original_rerank
            globals()["score_pairs"] = original_pairs
        print("OK: cross-encoder failure fails closed (case-number hits only)")

        # One embed call and one cross-encoder call per search, on both paths.
        from app.retrieval import query_embedder as _qe

        model = _qe._generator.model
        original_encode, counts = model.encode, {"encode": 0}

        def counting_encode(*a, **k):
            counts["encode"] += 1
            return original_encode(*a, **k)

        model.encode = counting_encode
        try:
            for q in (story, "general elections 2013 National Assembly seat NA-266 Nasirabad Jaffarabad"):
                counts["encode"] = 0
                await retrieve_v2(q, 5, 2)
                assert counts["encode"] == 1 and last_debug.get("embed_calls") == 1, (q[:30], counts)
                assert last_debug.get("rerank_calls") == 1, (q[:30], last_debug.get("rerank_calls"))
        finally:
            model.encode = original_encode
        print("OK: one batched embed and one cross-encoder call per search (narrative and short)")

        # A hung judge returns within JUDGE_TIMEOUT with the reranker order;
        # a garbage judge falls back the same way. No real LLM call is made.
        from app.retrieval import judge

        query = "seniority and promotion of police officers before a service tribunal"
        reference = [p["judgment_id"] for p in (await retrieve_v2(query, 5, 2))["parent_results"]]
        original_call = judge._call_llm

        async def hung(*_):
            await asyncio.sleep(120)

        async def garbage(*_):
            return "I think C2 is best, probably."

        OVERRIDES["USE_LLM_JUDGE"] = True
        try:
            for name, fake in (("hung", hung), ("garbage", garbage)):
                judge._call_llm = fake
                started = time.perf_counter()
                out = await retrieve_v2(query, 5, 2)
                took = time.perf_counter() - started
                assert not out["judge_used"], name
                assert [p["judgment_id"] for p in out["parent_results"]] == reference, name
                assert took < judge.judge_timeout() + 5.0, (name, took)
                print(f"OK: {name} judge -> reranker order kept, returned in {took:.1f}s "
                      f"(judge stage {out['timings_ms']['judge']:.0f}ms, timeout {judge.judge_timeout():.0f}s)")
        finally:
            judge._call_llm = original_call
            OVERRIDES.clear()
        print("OK: empty query -> no_results, no exception")

    asyncio.run(main())
