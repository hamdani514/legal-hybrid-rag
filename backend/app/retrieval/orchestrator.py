"""
The retrieval pipeline's single entry point.

STEP 10 of retrieval: runs every stage in order and returns the finished
response. This is the only module that imports from several pipeline steps at
once; it reimplements none of their logic.

    STAGE 1   preprocess         app.retrieval.query_preprocessor
    STAGE 2   embed              app.retrieval.query_embedder   (v1 path only)
    STAGE 3   chunk search       app.retrieval.chroma_client
    STAGE 3.5 rerank             app.retrieval.reranker
    STAGE 4   rank judgments     app.retrieval.chroma_client
    STAGE 5   section search     app.retrieval.node_searcher
    STAGE 6   expand context     app.retrieval.context_expander
    STAGE 7   assemble context   app.retrieval.context_assembler
    STAGE 8   generate answer    app.retrieval.llm_responder

Why the rerank sits between search and ranking
----------------------------------------------
The bi-encoder scores query and passage separately, which is what makes the
index searchable and also what limits it: measured on this corpus, sections
within a judgment sit only 0.029 cosine closer together than sections across
judgments. Ranking judgments on that margin is stable at eleven cases and
arbitrary at a thousand.

So stage 3 pulls a wide pool cheaply, stage 3.5 rescores the top of it with a
cross-encoder that reads query and passage together, and stage 4 ranks
judgments on those scores instead. The same reranked pool then feeds stage 5,
so the expensive model runs once per query rather than once per stage.

Many users at once
------------------
* **The event loop never runs model or CPU work.** Embedding, chunk search,
  reranking, section search and context assembly (a tiktoken loop) run in
  worker threads; the query record is written in a thread, fire-and-forget.
  Previously one search's embedding and its ~94 KB synchronous json.dump
  stalled every other request in the process.
* **The query is not embedded here on the v2 path.** v2 embeds for itself; the
  vector this module used to compute first was thrown away.
* **Only the top judgment is analysed with the search** (``ANSWER_TOP_ONLY``).
  Gemini's free tier allows 15 requests a minute for the whole project; three
  answers per search capped the system at ~5 searches a minute. The others
  carry ``answer_status="on_demand"`` and are analysed by
  :func:`answer_for_judgment` (POST /query/answer) when the user asks.
* **Every result carries an ``answer_status``** (contracts.ANSWER_STATUSES).
  A spent quota is "rate_limited" with no answer text, never the error
  sentinel rendered as if it were the analysis.
* **Answers are cached** by (normalised query, judgment) in an in-process LRU,
  with single-flight so two clicks on the same case spend one request. The
  context each judgment was given during the search is cached too, so an
  on-demand analysis reads exactly what the search assembled.

Every query's artefacts are recorded through app.retrieval.query_recorder
(slim by default; see that module).
"""

import asyncio
import sys
import time
from collections import OrderedDict
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from loguru import logger

from app.config import settings
from app.database import db
from app.retrieval.chroma_client import rank_judgments, search_chunks
from app.retrieval.context_assembler import assemble_all_judgments, assemble_judgment_context
from app.retrieval.context_expander import expand_all_judgments
from app.retrieval.contracts import (
    ANSWER_ERROR,
    ANSWER_ON_DEMAND,
    ANSWER_RATE_LIMITED,
    ANSWER_READY,
)
from app.retrieval.index_loader import get_nodes_for_judgment
from app.retrieval.llm_responder import generate_answer, generate_summary, status_of
from app.retrieval.mongo_fetcher import ID_FIELD, fetch_nodes
from app.retrieval.node_searcher import search_all_judgments
from app.retrieval.query_embedder import embed_query
from app.retrieval.query_preprocessor import preprocess
from app.retrieval.reranker import (
    RELEVANCE_KEY,
    RERANK_SCORE_KEY,
    is_enabled as rerank_enabled,
    rerank,
)
# Called through this module's global so the evaluation can swap it for a
# no-op (eval/evallib.quiet_pipeline patches orchestrator.record_query).
from app.retrieval.query_recorder import record_query

# Ingestion writes level 1 for root nodes; the index mirrors it as node_type.
ROOT_NODE_TYPE = "root"

MODE_ANSWER = "answer"
MODE_RETRIEVE_ONLY = "retrieve_only"

# Shown when nothing in the corpus answers the query. The wording matters: it
# says the archive does not hold an answer, not that no such law exists.
NO_RESULTS_MESSAGE = (
    "No relevant case is available in our data centre for this query. "
    "The archive holds reported judgments of the Supreme Court of Pakistan, "
    "and none of them address this question."
)

# The case-card fields a result carries, so an un-analysed result still says
# what the case is about (the frontend's "on demand" view).
# "bench" is the list of judges; the results list filters by judge name, and
# nothing else in the UI can supply it.
CARD_FIELDS = ("case_display", "subject", "headnote", "holding", "outcome",
               "appellant", "respondent", "decision_date", "bench", "card_status")


# ── Caches ──────────────────────────────────────────────────────────────────

class _LRU:
    """A small bounded mapping, most-recently-used last. Event-loop only."""

    def __init__(self, maxsize: int):
        self.maxsize = max(1, int(maxsize))
        self._data: OrderedDict = OrderedDict()

    def get(self, key):
        if key not in self._data:
            return None
        self._data.move_to_end(key)
        return self._data[key]

    def put(self, key, value) -> None:
        self._data[key] = value
        self._data.move_to_end(key)
        while len(self._data) > self.maxsize:
            self._data.popitem(last=False)

    def __len__(self) -> int:
        return len(self._data)

    def clear(self) -> None:
        self._data.clear()


_answer_cache = _LRU(int(getattr(settings, "ANSWER_CACHE_SIZE", 512) or 512))
_context_cache = _LRU(int(getattr(settings, "ANSWER_CONTEXT_CACHE_SIZE", 256) or 256))
_inflight: dict[tuple[str, str], asyncio.Future] = {}
_background: set[asyncio.Task] = set()


def normalise_query(query: str) -> str:
    """The cache key form of a query: case and whitespace do not matter."""
    return " ".join((query or "").lower().split())


async def _answer_cached(raw_query: str, judgment_id: str, context: str) -> tuple[str | None, str]:
    """Generate (or reuse) one judgment's analysis. Returns (answer, status).

    Only ready answers are cached: a rate-limited attempt must be retryable.
    Concurrent requests for the same (query, judgment) share one generation.
    """
    key = (normalise_query(raw_query), judgment_id)
    cached = _answer_cache.get(key)
    if cached is not None:
        return cached, ANSWER_READY

    pending = _inflight.get(key)
    if pending is not None:
        try:
            return await asyncio.shield(pending)
        except asyncio.CancelledError:
            if not pending.cancelled():
                raise  # this request itself was cancelled
            # The request that was generating went away (client disconnect);
            # generate here instead of failing a request that is still live.

    future: asyncio.Future = asyncio.get_running_loop().create_future()
    _inflight[key] = future
    try:
        response = await generate_answer(raw_query, context)
        status = status_of(response)
        result = (str(response), ANSWER_READY) if status == ANSWER_READY else (None, status)
        if status == ANSWER_READY:
            _answer_cache.put(key, result[0])
        future.set_result(result)
        return result
    except asyncio.CancelledError:
        if not future.done():
            future.cancel()  # waiters see a cancelled future and generate themselves
        raise
    except BaseException as e:
        if not future.done():
            future.set_exception(e)
            future.exception()  # mark retrieved: waiters re-raise, nobody logs it twice
        raise
    finally:
        _inflight.pop(key, None)


def _record_in_background(**kwargs) -> None:
    """Write the query record in a worker thread without awaiting it."""
    recorder = record_query  # module global, possibly replaced by the eval
    try:
        task = asyncio.get_running_loop().create_task(asyncio.to_thread(recorder, **kwargs))
    except Exception as e:  # recording is diagnostic; never fail a search over it
        logger.warning(f"Could not schedule the query record: {e}")
        return
    _background.add(task)
    task.add_done_callback(_background.discard)


async def _documents_meta_for(judgment_ids: list[str]) -> dict[str, dict]:
    """Map judgment ids to their original PDF filenames and drive information.

    Node documents do not carry the filename; it lives on the `documents`
    collection, keyed by pdf_id.
    """
    if db.database is None or not judgment_ids:
        return {}

    cursor = db.database.documents.find(
        {"pdf_id": {"$in": judgment_ids}}, {"pdf_id": 1, "filename": 1, "drive": 1}
    )
    meta = {}
    async for d in cursor:
        drive_info = d.get("drive") if isinstance(d.get("drive"), dict) else {}
        meta[d["pdf_id"]] = {
            "filename": d.get("filename", ""),
            "has_drive_file": bool(drive_info.get("file_id")),
            "drive_file_id": drive_info.get("file_id"),
        }
    return meta


async def _cards_for(judgment_ids: list[str]) -> dict[str, dict]:
    """Map judgment ids to the display fields of their case cards ({} if none)."""
    if db.database is None or not judgment_ids:
        return {}
    try:
        cursor = db.database.case_cards.find(
            {"judgment_id": {"$in": judgment_ids}},
            {"_id": 0, "judgment_id": 1, **{f: 1 for f in CARD_FIELDS}},
        )
        cards = {}
        async for c in cursor:
            card = {f: c[f] for f in CARD_FIELDS if c.get(f) not in (None, "", [])}
            if card:
                cards[c["judgment_id"]] = card
        return cards
    except Exception as e:  # a card is a nicety; the result stands without it
        logger.warning(f"Case cards unavailable for results: {e}")
        return {}


async def retrieve_and_answer(
    raw_query: str,
    top_k_judgments: int = 5,
    top_k_sections: int = 3,
    mode: str = MODE_ANSWER,
    user_id: str | None = None,
) -> dict:
    """Run the whole retrieval pipeline for one query.

    Args:
        raw_query: The researcher's question or case description, as typed.
        top_k_judgments: How many judgments stage 3 should return.
        top_k_sections: How many sections stage 4 keeps per judgment.
        mode: ``"answer"`` to analyse the best match (all matches when
            ANSWER_TOP_ONLY is off), ``"retrieve_only"`` to stop after
            assembling context.
        user_id: The authenticated user, recorded with the query.

    Returns:
        The finished response: the query, its intent, the ranked judgments with
        their assembled context and ``answer_status``, and the answer for the
        top match.
    """
    timings: dict[str, float] = {}
    started = time.perf_counter()

    def mark(stage: str, since: float) -> float:
        now = time.perf_counter()
        timings[stage] = (now - since) * 1000
        return now

    # STAGE 1 — preprocess (regex and a dictionary; microseconds)
    cleaned_query, intent = preprocess(raw_query)
    t = mark("preprocess", started)

    # STAGES 2-5 come from one of two pipelines.
    #
    # v1 is the dense-only path below. v2 (app.retrieval.pipeline_v2) runs the
    # query analyzer, five retrievers, judgment-level fusion, the cross-encoder
    # over each judgment's best passages and, optionally, the LLM judge — and
    # returns parent_results and stage2_results in exactly v1's shapes, so
    # everything from abstention onward is shared.
    #
    # v2 is opt-in (USE_V2_PIPELINE) and read on every call, so the evaluation
    # harness can switch between the two without a restart. Any failure inside
    # v2 falls back to v1 for that query: a search must never fail because the
    # newer path did.
    pipeline = "v2" if getattr(settings, "USE_V2_PIPELINE", False) else "v1"
    reasons: dict[str, str] = {}
    # v2 may explain an empty result ("too general") or flag a browse ("broad
    # query: judgments about family matters"); v1 never sets these.
    v2_message = ""
    notice = ""
    stage2_results: dict = {}
    candidates: list = []
    reranked = False
    parent_results: list = []
    query_vector = None

    if pipeline == "v2":
        try:
            from app.retrieval.pipeline_v2 import retrieve_v2

            v2 = await retrieve_v2(
                raw_query, top_k_judgments=top_k_judgments, top_k_sections=top_k_sections
            )
            candidates = v2.get("candidates") or []
            reranked = bool(v2.get("reranked"))
            parent_results = v2.get("parent_results") or []
            stage2_results = v2.get("stage2_results") or {}
            reasons = v2.get("reasons") or {}
            v2_message = v2.get("message") or ""
            notice = v2.get("notice") or ""
            query_vector = v2.get("query_vector")  # only for the full (non-slim) record
            for stage, ms in (v2.get("timings_ms") or {}).items():
                timings[f"v2.{stage}"] = float(ms)
            t = time.perf_counter()
        except Exception:
            logger.exception("Pipeline v2 failed; falling back to v1 for this query")
            pipeline = "v1"
            t = time.perf_counter()

    if pipeline == "v1":
        # STAGE 2 — embed (v1 only; in a thread, through the inference slots)
        query_vector = await asyncio.to_thread(embed_query, cleaned_query)
        t = mark("embed", t)

        # STAGE 3 — chunk-level search across the corpus
        candidates = await asyncio.to_thread(search_chunks, query_vector)
        t = mark("chunk_search", t)

        # STAGE 3.5 — rerank the top of the pool with a cross-encoder
        candidates = await asyncio.to_thread(rerank, cleaned_query, candidates)
        reranked = rerank_enabled() and any(RERANK_SCORE_KEY in c for c in candidates)
        t = mark("rerank", t)

        # STAGE 4 — group the scored chunks into a judgment ranking, discarding
        # anything that does not clear the relevance floor.
        parent_results = rank_judgments(
            candidates,
            top_k=top_k_judgments,
            # Rank and display on the calibrated figure: the raw logit is
            # unbounded and negative, and this score reaches the UI.
            score_key=RELEVANCE_KEY if reranked else "score",
        )
        t = mark("judgment_rank", t)

    judgment_ids = [r["judgment_id"] for r in parent_results]

    # Nothing cleared the floor. Stop here: do not expand context, do not
    # assemble it, and above all do not call the LLM. Handing an unrelated
    # judgment to a model and asking it to answer a legal question is how a
    # query about a bail case comes back with another case's disposition
    # attached — which is not a poor answer but a fabricated one.
    if not parent_results:
        logger.info(f"No judgment cleared the relevance floor for query: {cleaned_query!r}")
        _record_in_background(
            original_query=raw_query,
            cleaned_query=cleaned_query,
            intent=intent,
            embedding=query_vector,
            user_id=user_id,
            extra={
                "mode": mode,
                "pipeline": pipeline,
                "reranked": reranked,
                "stage1_candidates": len(candidates),
                "no_results": True,
                "best_relevance": max(
                    (c.get(RELEVANCE_KEY, 0.0) for c in candidates), default=0.0
                ),
                "timings_ms": {k: round(v, 1) for k, v in timings.items()},
            },
        )
        return {
            "query": raw_query,
            "cleaned_query": cleaned_query,
            "intent": intent,
            "mode": mode,
            "pipeline": pipeline,
            "reranked": reranked,
            "judgments": [],
            "top_judgment_answer": None,
            "no_results": True,
            "message": v2_message or NO_RESULTS_MESSAGE,
        }

    # STAGE 5 — section-level search, reusing the reranked scores where it can.
    # v2 has already chosen each judgment's sections from its evidence.
    if pipeline == "v1":
        stage2_results = await asyncio.to_thread(
            search_all_judgments,
            query_vector,
            judgment_ids,
            top_k_per_judgment=top_k_sections,
            candidates=candidates,
        )
        t = mark("section_search", t)

    # STAGE 6 — expand context (judgments concurrently), alongside the
    # documents/cards lookups the response needs anyway.
    expanded, docs_meta, cards = await asyncio.gather(
        expand_all_judgments(stage2_results),
        _documents_meta_for(judgment_ids),
        _cards_for(judgment_ids),
    )
    t = mark("expand", t)

    # STAGE 7 — assemble context (tiktoken counting: CPU, so in a thread)
    assembled = await asyncio.to_thread(assemble_all_judgments, expanded)
    t = mark("assemble", t)

    norm = normalise_query(raw_query)
    for c in assembled:
        if c.get("context"):
            _context_cache.put((norm, c["judgment_id"]), c["context"])

    # STAGE 8 — analyse. Only judgments that survived the relevance floor reach
    # this point, so no call is spent on an unrelated case. With ANSWER_TOP_ONLY
    # only the best match is analysed now; the rest are "on_demand" and cost
    # nothing unless the user opens them. The model receives the RAW query: its
    # fit check compares the judgment with the user's own description, which
    # the keyword-cleaned form no longer contains.
    answers: list[str | None] = [None] * len(assembled)
    statuses: list[str] = [ANSWER_ON_DEMAND] * len(assembled)
    if mode == MODE_ANSWER and assembled:
        top_only = bool(getattr(settings, "ANSWER_TOP_ONLY", True))
        targets = [0] if top_only else list(range(len(assembled)))
        answerable = [i for i in targets if assembled[i].get("context")]
        for i in targets:
            if i not in answerable:
                statuses[i] = ANSWER_ERROR  # nothing to analyse it from
        if answerable:
            generated = await asyncio.gather(*(
                _answer_cached(raw_query, assembled[i]["judgment_id"], assembled[i]["context"])
                for i in answerable
            ))
            for index, (answer, status) in zip(answerable, generated):
                answers[index], statuses[index] = answer, status

    top_judgment_answer = answers[0] if answers else None
    mark("generate", t)

    # Section labels come from the expanded documents; the Chroma metadata that
    # stage 4 returns does not carry section_type.
    sections_by_judgment = {
        e["judgment_id"]: [s["section_type"] for s in e["retrieved_sections"]]
        for e in expanded
    }
    scores_by_judgment = {r["judgment_id"]: r["score"] for r in parent_results}
    # v2 labels each result "high" or "medium"; v1 results carry no label.
    confidence_by_judgment = {r["judgment_id"]: r.get("confidence", "") for r in parent_results}

    judgments = [
        {
            "judgment_id": c["judgment_id"],
            "filename": docs_meta.get(c["judgment_id"], {}).get("filename", ""),
            "heading": c.get("heading", ""),
            "similarity_score": scores_by_judgment.get(c["judgment_id"], 0.0),
            "confidence": confidence_by_judgment.get(c["judgment_id"], ""),
            "sections_retrieved": sections_by_judgment.get(c["judgment_id"], []),
            "context": c["context"],
            "token_count": c["token_count"],
            "llm_answer": answers[idx] if idx < len(answers) else None,
            "answer_status": statuses[idx] if idx < len(statuses) else ANSWER_ON_DEMAND,
            "card": cards.get(c["judgment_id"]),
            "download_url": f"/api/admin/judgments/{c['judgment_id']}/download",
            "has_drive_file": docs_meta.get(c["judgment_id"], {}).get("has_drive_file", False),
            # The LLM judge's one-line justification, when v2 ran it.
            "reason": reasons.get(c["judgment_id"], ""),
        }
        for idx, c in enumerate(assembled)
    ]

    total_ms = (time.perf_counter() - started) * 1000
    logger.info(
        "Retrieval complete in {:.0f}ms | ".format(total_ms)
        + " | ".join(f"{stage} {ms:.0f}ms" for stage, ms in timings.items())
    )

    _record_in_background(
        original_query=raw_query,
        cleaned_query=cleaned_query,
        intent=intent,
        embedding=query_vector,
        user_id=user_id,
        extra={
            "mode": mode,
            "reranked": reranked,
            "stage1_candidates": len(candidates),
            "stage1_judgments": parent_results,
            "stage2_sections": stage2_results,
            "expanded_context": expanded,
            "assembled_contexts": assembled,
            "pipeline": pipeline,
            "judge_reasons": reasons,
            "answer": top_judgment_answer,
            "answer_statuses": {j["judgment_id"]: j["answer_status"] for j in judgments},
            "timings_ms": {k: round(v, 1) for k, v in timings.items()},
        },
    )

    return {
        "query": raw_query,
        "cleaned_query": cleaned_query,
        "intent": intent,
        "mode": mode,
        "pipeline": pipeline,
        "reranked": reranked,
        "judgments": judgments,
        "top_judgment_answer": top_judgment_answer,
        "no_results": False,
        "message": "",
        "notice": notice,
    }


async def answer_for_judgment(raw_query: str, judgment_id: str) -> dict:
    """Analyse one judgment against a query on demand (POST /query/answer).

    Reads the context the search assembled for this (query, judgment) when it
    is still cached, otherwise the judgment's full context. Answers are cached
    by (normalised query, judgment).

    Returns:
        ``{"judgment_id", "answer", "answer_status", "cached", "found"}``;
        ``found`` is False for an unknown judgment.
    """
    key = (normalise_query(raw_query), judgment_id)
    cached = _answer_cache.get(key)
    if cached is not None:
        return {"judgment_id": judgment_id, "answer": cached, "answer_status": ANSWER_READY,
                "cached": True, "found": True}

    context = _context_cache.get(key)
    if not context:
        _, context = await build_judgment_context(judgment_id)
    if not context:
        return {"judgment_id": judgment_id, "answer": None, "answer_status": ANSWER_ERROR,
                "cached": False, "found": False}

    answer, status = await _answer_cached(raw_query, judgment_id, context)
    return {"judgment_id": judgment_id, "answer": answer, "answer_status": status,
            "cached": False, "found": True}


async def build_judgment_context(judgment_id: str) -> tuple[str, str]:
    """Assemble the full context of one judgment, independent of any query.

    Used by summarisation, which names the judgment outright rather than
    searching for it, and by on-demand answers whose search context expired.

    Args:
        judgment_id: The judgment to assemble.

    Returns:
        A ``(filename, context)`` tuple; context is "" if the judgment is
        unknown.
    """
    entries = get_nodes_for_judgment(judgment_id)
    if not entries:
        logger.warning(f"No index entries for judgment_id={judgment_id}")
        return "", ""

    nodes = await fetch_nodes([e["mongo_doc_id"] for e in entries])
    if not nodes:
        return "", ""

    root_ids = {e["mongo_doc_id"] for e in entries if e.get("node_type") == ROOT_NODE_TYPE}
    root_node = next((n for n in nodes.values() if n[ID_FIELD] in root_ids), None)

    # Every section counts as expanded here: nothing was retrieved by score.
    expanded = {
        "judgment_id": judgment_id,
        "root_node": root_node,
        "retrieved_sections": [],
        "expanded_sections": [
            {
                "section_type": n.get("section_type") or "",
                "text": n.get("text") or "",
                "score": 0.0,
                "is_directly_retrieved": False,
                "mongo_doc_id": n[ID_FIELD],
                "heading": n.get("title") or "",
            }
            for n in nodes.values()
            if n[ID_FIELD] not in root_ids
        ],
    }

    # _filenames_for was renamed to _documents_meta_for and this call site was
    # missed, so summarisation raised NameError for every judgment.
    meta = await _documents_meta_for([judgment_id])
    filename = meta.get(judgment_id, {}).get("filename", "")
    return filename, await asyncio.to_thread(assemble_judgment_context, expanded)


async def summarize_judgment(judgment_id: str) -> tuple[str, str]:
    """Summarise one judgment.

    Args:
        judgment_id: The judgment to summarise.

    Returns:
        A ``(filename, summary)`` tuple. The summary is an LLMText whose
        ``status`` says whether it is a real summary or a busy/failed notice.
    """
    filename, context = await build_judgment_context(judgment_id)
    if not context:
        return filename, "Judgment not found."
    return filename, await generate_summary(context)


if __name__ == "__main__":
    from app.database import connect_db

    async def main() -> None:
        await connect_db()

        # An in-corpus query. The old fixture asked about bail and murder,
        # which this archive does not hold — since abstention was added that
        # query correctly returns nothing, so it can no longer stand in for
        # the happy path.
        query = "evacuee land granted and later disputed in Tando Adam"
        result = await retrieve_and_answer(query, top_k_judgments=3, top_k_sections=2, mode=MODE_ANSWER)

        print(f"Query: {result['query']}")
        print(f"Intent: {result['intent']}")
        print(f"Judgments found: {len(result['judgments'])}")
        for j in result["judgments"]:
            print(f"  {j['filename']}  score={j['similarity_score']:.4f}  "
                  f"status={j['answer_status']}  sections={j['sections_retrieved']}")

        if result["top_judgment_answer"]:
            print("\nLLM Answer:")
            print(result["top_judgment_answer"])

        judgments = result["judgments"]
        assert judgments, "no judgments returned"
        assert all(j["filename"] for j in judgments), "filename not resolved"
        assert all(j["sections_retrieved"] for j in judgments), "no section labels"
        assert all(0.0 <= j["similarity_score"] <= 1.0 for j in judgments), \
            "a relevance score fell outside 0..1"
        assert all(j["answer_status"] in (ANSWER_READY, ANSWER_ON_DEMAND, ANSWER_RATE_LIMITED, ANSWER_ERROR)
                   for j in judgments)
        top = judgments[0]
        assert top["llm_answer"] == result["top_judgment_answer"]
        assert top["answer_status"] in (ANSWER_READY, ANSWER_RATE_LIMITED), top["answer_status"]
        if top["answer_status"] == ANSWER_READY:
            assert top["llm_answer"] and not top["llm_answer"].startswith("Error"), top["llm_answer"]
        else:
            assert top["llm_answer"] is None, "a rate-limited result carried answer text"
        if getattr(settings, "ANSWER_TOP_ONLY", True):
            assert all(j["answer_status"] == ANSWER_ON_DEMAND and j["llm_answer"] is None
                       for j in judgments[1:]), "a non-top judgment was analysed with the search"

        # On demand: the second judgment is analysed when asked, then cached.
        if len(judgments) > 1:
            second = judgments[1]["judgment_id"]
            first = await answer_for_judgment(query, second)
            assert first["found"] and first["answer_status"] in (ANSWER_READY, ANSWER_RATE_LIMITED), first
            if first["answer_status"] == ANSWER_READY:
                again = await answer_for_judgment("  EVACUEE land granted and later disputed in tando adam ", second)
                assert again["cached"] and again["answer"] == first["answer"], "answer cache missed"
                print(f"\nOn-demand answer for #2 ({len(first['answer'])} chars), cached on repeat.")
        missing = await answer_for_judgment(query, "no-such-judgment")
        assert not missing["found"] and missing["answer"] is None

        # Abstention. This is the property that matters most: a query with no
        # answer in the corpus must return nothing at all — no judgments, no
        # downloads, and above all no disposition borrowed from an unrelated
        # case. Getting this wrong is how "imran khan bail case" came back
        # reporting that an appeal had been allowed.
        empty = await retrieve_and_answer("imran khan bail case", top_k_judgments=3)
        assert empty["no_results"] is True, "an out-of-corpus query returned results"
        assert empty["judgments"] == [], "an out-of-corpus query returned judgments"
        assert empty["top_judgment_answer"] is None, "an out-of-corpus query was answered"
        assert empty["message"], "no explanation given for the empty result"
        print(f"\nAbstention OK: {empty['message'][:62]}...")

        retrieve_only = await retrieve_and_answer(
            "did the Service Tribunal have jurisdiction to entertain the service appeal",
            top_k_judgments=2,
            mode=MODE_RETRIEVE_ONLY,
        )
        assert retrieve_only["top_judgment_answer"] is None, "retrieve_only generated an answer"
        assert all(j["answer_status"] == ANSWER_ON_DEMAND for j in retrieve_only["judgments"])
        await asyncio.gather(*list(_background), return_exceptions=True)
        print("\nOK: orchestrator verified (top answer + on-demand + cache + abstention + retrieve_only).")

    asyncio.run(main())
