"""
The retrieval API.

Every stage of the pipeline lives behind app.retrieval.orchestrator; these
routes only translate HTTP in and out of it.
"""

import time

from fastapi import APIRouter, HTTPException
from loguru import logger

from app.api.schemas import (
    JudgmentResult,
    SearchRequest,
    SearchResponse,
    SummarizeRequest,
    SummarizeResponse,
)
from app.retrieval.orchestrator import retrieve_and_answer, summarize_judgment

router = APIRouter()


@router.post("/search", response_model=SearchResponse)
async def search(body: SearchRequest) -> SearchResponse:
    """Run the retrieval pipeline and answer a legal research query."""
    started = time.perf_counter()

    try:
        result = await retrieve_and_answer(
            raw_query=body.query,
            top_k_judgments=body.top_k_judgments,
            top_k_sections=body.top_k_sections,
            mode=body.mode,
        )
    except Exception as e:
        logger.exception("Error in /query/search")
        raise HTTPException(status_code=500, detail=str(e))

    return SearchResponse(
        query=result["query"],
        cleaned_query=result["cleaned_query"],
        intent=result["intent"],
        mode=result["mode"],
        judgments=[JudgmentResult(**j) for j in result["judgments"]],
        top_judgment_answer=result["top_judgment_answer"],
        latency_ms=int((time.perf_counter() - started) * 1000),
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
        summary=summary,
    )
