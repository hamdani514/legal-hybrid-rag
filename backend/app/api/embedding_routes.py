from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from app.ingestion.embedding_pipeline import run_embedding_pipeline
from loguru import logger

router = APIRouter(prefix="/embeddings", tags=["embeddings"])

class GenerateRequest(BaseModel):
    pdf_id: Optional[str] = None
    force_regenerate: Optional[bool] = False

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
