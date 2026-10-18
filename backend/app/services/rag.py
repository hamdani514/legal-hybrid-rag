from typing import Optional, List, Dict, Any
from loguru import logger
from app.retrieval.orchestrator import retrieve_and_answer


async def run_rag_pipeline(query: str, user_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Executes the legal hybrid RAG pipeline for the given query.
    Returns:
        {
            "answer": str,
            "sources": List[dict]
        }
    """
    try:
        result = await retrieve_and_answer(
            raw_query=query,
            user_id=str(user_id) if user_id else None,
        )
    except Exception as e:
        logger.error(f"Error executing RAG pipeline for query '{query}': {e}")
        return {
            "answer": "An error occurred while processing your legal query through the retrieval pipeline.",
            "sources": [],
        }

    # Extract answer text
    answer = (
        result.get("top_judgment_answer")
        or result.get("message")
        or "No relevant Supreme Court judgments cleared the relevance threshold for this query."
    )

    # Extract source citations
    sources = []
    for j in result.get("judgments", []):
        sources.append({
            "docId": j.get("judgment_id") or j.get("filename") or "Unknown Document",
            "sectionType": j.get("heading") or "Judgment Summary",
            "confidence": j.get("confidence", "Medium"),
            "score": float(j.get("similarity_score", 0.0)),
            "filename": j.get("filename", ""),
        })

    return {
        "answer": answer,
        "sources": sources,
    }
