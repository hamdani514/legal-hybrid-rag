"""
The retrieval API.

Every stage of the pipeline lives behind app.retrieval.orchestrator; these
routes only translate HTTP in and out of it.

Two runtime details live here because they are about requests, not retrieval:

* **Warm-up.** main.py loads the models and runs one throwaway v2 query in the
  background at start-up, so the server accepts requests before that finishes.
  A search arriving in that window waits (bounded) for the warm-up instead of
  racing it through the same one-off initialisation.
* **The user.** When authentication has identified the caller
  (``request.state.principal``, set by app.api.security), the user id is passed
  on so the query record carries it.

Authentication and per-user limits are attached where the router is included
(main.py), not here.
"""

import asyncio
import time

from fastapi import APIRouter, HTTPException, Request
from loguru import logger

from app.api.schemas import (
    AnswerRequest,
    AnswerResponse,
    CompareRequest,
    CompareResponse,
    JudgmentResult,
    MoreRequest,
    MoreResponse,
    SearchRequest,
    SearchResponse,
    SummarizeRequest,
    SummarizeResponse,
)
from app.retrieval.comparator import compare_judgments
from app.retrieval.llm_responder import status_of
from app.retrieval.orchestrator import answer_for_judgment, more_results, retrieve_and_answer, summarize_judgment
from modules.payment import plans
from modules.payment.plan_guard import plan_guard, refund_query, require_feature

router = APIRouter()

# What the user sees when a step fails. The real error goes to the log only:
# it can carry file paths, database or provider details.
SERVER_ERROR = "Something went wrong on our side. Please try again in a moment."

# How long a request may wait for the start-up warm-up before going ahead.
WARMUP_WAIT_S = 90.0


async def _await_warmup(request: Request) -> None:
    task = getattr(getattr(request.app, "state", None), "warmup", None)
    if task is None or not isinstance(task, asyncio.Future) or task.done():
        return
    try:
        await asyncio.wait_for(asyncio.shield(task), timeout=WARMUP_WAIT_S)
    except Exception:
        # A slow or failed warm-up only means this request loads what it needs.
        pass


def _user_id(request: Request) -> str | None:
    principal = getattr(request.state, "principal", None)
    if isinstance(principal, dict):
        return principal.get("sub") or None
    return getattr(principal, "sub", None)


@router.post("/search", response_model=SearchResponse)
async def search(body: SearchRequest, request: Request) -> SearchResponse:
    """Run the retrieval pipeline and analyse the best match."""
    started = time.perf_counter()
    await _await_warmup(request)

    # Daily search limit (Free 2, Standard 20, Premium 50 — modules/payment/plans.py)
    await plan_guard(request)
    plan_key = getattr(request.state, "effective_plan", plans.FREE)
    plan = plans.describe(plan_key)

    # Free retrieves and summarises from the case cards only: no analysis, so
    # no Gemini call; analysing a case is a paid feature.
    mode = body.mode if plans.has_feature(plan_key, "analyse") else "retrieve_only"
    top_k = body.top_k_judgments
    if plan["max_results"]:
        top_k = min(top_k, plan["max_results"])

    try:
        result = await retrieve_and_answer(
            raw_query=body.query,
            top_k_judgments=top_k,
            top_k_sections=body.top_k_sections,
            mode=mode,
            user_id=_user_id(request),
        )
    except Exception:
        logger.exception("Error in /query/search")
        # Refund query counter on pipeline failure
        await refund_query(request)
        raise HTTPException(status_code=500, detail=SERVER_ERROR)

    judgments = result["judgments"]
    has_more = result.get("has_more", False)
    if plan["max_results"]:
        judgments = judgments[: plan["max_results"]]
        # Further pages are a paid feature; Free is told more exist, so the
        # UI can show the locked "More relevant cases" button.
    more_locked = bool(has_more) and not plans.has_feature(plan_key, "see_all")

    return SearchResponse(
        query=result["query"],
        cleaned_query=result["cleaned_query"],
        intent=result["intent"],
        mode=result["mode"],
        pipeline=result.get("pipeline", "v1"),
        reranked=result.get("reranked", False),
        no_results=result.get("no_results", False),
        message=result.get("message", ""),
        notice=result.get("notice", ""),
        judgments=[JudgmentResult(**j) for j in judgments],
        top_judgment_answer=result["top_judgment_answer"],
        has_more=has_more,
        more_locked=more_locked,
        plan=plan["plan"],
        features=plan["features"],
        latency_ms=int((time.perf_counter() - started) * 1000),
    )


@router.post("/more", response_model=MoreResponse)
async def more(body: MoreRequest, request: Request) -> MoreResponse:
    """The next page of a search's judgments ("More relevant cases").

    Continues the search the user already ran, so it does not count against
    the plan's daily search limit; it spends no Gemini quota either (every
    result is "on_demand"). It is rate-limited per minute like a search,
    because each page runs the cross-encoder.
    """
    started = time.perf_counter()
    filters = body.filters.as_dict() if body.filters else None
    # Filtering every candidate is the "filter" feature; plain paging is "see all".
    await require_feature(request, "filter" if filters else "see_all")
    await _await_warmup(request)
    try:
        result = await more_results(
            body.query, body.shown, top_k_sections=body.top_k_sections, filters=filters
        )
    except Exception:
        logger.exception("Error in /query/more")
        raise HTTPException(status_code=500, detail=SERVER_ERROR)

    return MoreResponse(
        judgments=[JudgmentResult(**j) for j in result["judgments"]],
        has_more=result["has_more"],
        latency_ms=int((time.perf_counter() - started) * 1000),
    )


@router.post("/answer", response_model=AnswerResponse)
async def answer(body: AnswerRequest, request: Request) -> AnswerResponse:
    """Analyse one judgment from a search result against the query, on demand.

    Always 200 with an ``answer_status`` for a known judgment — "ready",
    "rate_limited" (the shared LLM budget is spent; retry shortly) or "error" —
    so the client renders a state, never provider error text. 404 for an
    unknown judgment.
    """
    await require_feature(request, "analyse")
    await _await_warmup(request)
    try:
        result = await answer_for_judgment(body.query, body.judgment_id)
    except Exception:
        logger.exception("Error in /query/answer")
        raise HTTPException(status_code=500, detail=SERVER_ERROR)

    if not result["found"]:
        raise HTTPException(status_code=404, detail="Judgment not found.")
    return AnswerResponse(
        judgment_id=result["judgment_id"],
        answer=result["answer"],
        answer_status=result["answer_status"],
        cached=result["cached"],
    )


@router.post("/summarize", response_model=SummarizeResponse)
async def summarize(body: SummarizeRequest, request: Request) -> SummarizeResponse:
    """Summarise one judgment, named directly rather than searched for."""
    await require_feature(request, "summarize")
    try:
        filename, summary = await summarize_judgment(body.judgment_id)
    except Exception:
        logger.exception("Error in /query/summarize")
        raise HTTPException(status_code=500, detail=SERVER_ERROR)

    return SummarizeResponse(
        judgment_id=body.judgment_id,
        filename=filename,
        summary=str(summary),
        summary_status=status_of(summary) if summary != "Judgment not found." else "error",
    )


@router.post("/compare", response_model=CompareResponse)
async def compare(body: CompareRequest, request: Request) -> CompareResponse:
    """Line several judgments up side by side on the same fields."""
    await require_feature(request, "compare")
    if not body.judgment_ids:
        raise HTTPException(status_code=400, detail="No judgments to compare.")

    # One LLM call per judgment, through the shared limiter. Bounded so a
    # crafted request cannot fan out into an unbounded number of calls.
    if len(body.judgment_ids) > 10:
        raise HTTPException(status_code=400, detail="Compare at most 10 judgments.")

    try:
        table = await compare_judgments(body.judgment_ids)
    except Exception:
        logger.exception("Error in /query/compare")
        raise HTTPException(status_code=500, detail=SERVER_ERROR)

    return CompareResponse(**table)
