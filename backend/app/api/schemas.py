"""Request and response models for the retrieval API."""

from typing import Literal

from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    query: str = Field(min_length=3, description="Legal research query")
    top_k_judgments: int = Field(default=5, ge=1, le=10)
    top_k_sections: int = Field(default=3, ge=1, le=6)
    mode: Literal["answer", "retrieve_only"] = "answer"


class JudgmentResult(BaseModel):
    judgment_id: str
    filename: str
    similarity_score: float
    sections_retrieved: list[str]
    token_count: int
    # Only the best-matching judgment is answered; the rest carry None.
    llm_answer: str | None = None


class SearchResponse(BaseModel):
    query: str
    cleaned_query: str
    intent: dict
    mode: str
    judgments: list[JudgmentResult]
    top_judgment_answer: str | None = None
    latency_ms: int


class SummarizeRequest(BaseModel):
    judgment_id: str


class SummarizeResponse(BaseModel):
    judgment_id: str
    filename: str
    summary: str
