from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from app.ingestion.embedding_pipeline import run_embedding_pipeline
from app.retrieval.orchestrator import retrieve_and_answer
from loguru import logger

router = APIRouter(prefix="/embeddings", tags=["embeddings"])

class GenerateRequest(BaseModel):
    pdf_id: Optional[str] = None
    force_regenerate: Optional[bool] = False

class SearchRequest(BaseModel):
    query: str
    limit: Optional[int] = 5

@router.post("/generate")
async def generate_embeddings(body: Optional[GenerateRequest] = None):
    """
    Generate embeddings for parsed judgment nodes.
    Supports resume if interrupted and avoids duplicates.
    Can be filtered by pdf_id.
    """
    try:
        pdf_id = body.pdf_id if body else None
        force_reg = body.force_regenerate if body else False
        
        logger.info(f"API Triggered: generate_embeddings (pdf_id={pdf_id}, force_regenerate={force_reg})")
        result = await run_embedding_pipeline(pdf_id=pdf_id, force_regenerate=force_reg)
        return result
    except Exception as e:
        logger.exception("Error in generate_embeddings API endpoint")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/search")
async def search_embeddings(body: SearchRequest):
    """
    Superseded by POST /query/search — kept so existing callers keep working.

    Delegates to the same orchestrator, so the two routes can never diverge.
    """
    try:
        logger.info(f"API Triggered: search_embeddings (query='{body.query}', limit={body.limit})")
        return await retrieve_and_answer(
            raw_query=body.query,
            top_k_judgments=body.limit or 5,
        )
    except Exception as e:
        logger.exception("Error in search_embeddings API endpoint")
        raise HTTPException(status_code=500, detail=str(e))
