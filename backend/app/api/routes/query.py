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
    SearchRequest,
    SearchResponse,
    SummarizeRequest,
    SummarizeResponse,
)
from app.retrieval.comparator import compare_judgments
from app.retrieval.llm_responder import status_of
from app.retrieval.orchestrator import answer_for_judgment, retrieve_and_answer, summarize_judgment

router = APIRouter()

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

    try:
        result = await retrieve_and_answer(
            raw_query=body.query,
            top_k_judgments=body.top_k_judgments,
            top_k_sections=body.top_k_sections,
            mode=body.mode,
            user_id=_user_id(request),
        )
    except Exception as e:
        logger.exception("Error in /query/search")
        raise HTTPException(status_code=500, detail=str(e))

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
        judgments=[JudgmentResult(**j) for j in result["judgments"]],
        top_judgment_answer=result["top_judgment_answer"],
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
    await _await_warmup(request)
    try:
        result = await answer_for_judgment(body.query, body.judgment_id)
    except Exception as e:
        logger.exception("Error in /query/answer")
        raise HTTPException(status_code=500, detail=str(e))

    if not result["found"]:
        raise HTTPException(status_code=404, detail="Judgment not found.")
    return AnswerResponse(
        judgment_id=result["judgment_id"],
        answer=result["answer"],
        answer_status=result["answer_status"],
        cached=result["cached"],
    )


@router.post("/summarize", response_model=SummarizeResponse)
async def summarize(body: SummarizeRequest) -> SummarizeResponse:
    """Summarise one judgment, named directly rather than searched for."""
    try:
        filename, summary = await summarize_judgment(body.judgment_id)
    except Exception as e:
        logger.exception("Error in /query/summarize")
        raise HTTPException(status_code=500, detail=str(e))

    return SummarizeResponse(
        judgment_id=body.judgment_id,
        filename=filename,
        summary=str(summary),
        summary_status=status_of(summary) if summary != "Judgment not found." else "error",
    )


@router.post("/compare", response_model=CompareResponse)
async def compare(body: CompareRequest) -> CompareResponse:
    """Line several judgments up side by side on the same fields."""
    if not body.judgment_ids:
        raise HTTPException(status_code=400, detail="No judgments to compare.")

    # One LLM call per judgment, through the shared limiter. Bounded so a
    # crafted request cannot fan out into an unbounded number of calls.
    if len(body.judgment_ids) > 10:
        raise HTTPException(status_code=400, detail="Compare at most 10 judgments.")

    try:
        table = await compare_judgments(body.judgment_ids)
    except Exception as e:
        logger.exception("Error in /query/compare")
        raise HTTPException(status_code=500, detail=str(e))

    return CompareResponse(**table)
