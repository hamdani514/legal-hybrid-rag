"""Request and response models for the retrieval API.

Queries are capped at MAX_QUERY_CHARS: users now describe whole case
situations (40-150 words), but an unbounded field would let one request push
an arbitrarily large prompt through the shared LLM quota and the CPU-bound
models. Every result carries ``answer_status`` (contracts.ANSWER_STATUSES) so
the client renders by status, never by sniffing error text out of the answer.
"""

from typing import Literal

from pydantic import BaseModel, Field

from app.config import settings
from app.retrieval.contracts import ANSWER_ON_DEMAND

MAX_QUERY_CHARS = int(getattr(settings, "MAX_QUERY_CHARS", 4000) or 4000)

AnswerStatus = Literal["ready", "on_demand", "rate_limited", "error"]


class SearchRequest(BaseModel):
    query: str = Field(min_length=3, max_length=MAX_QUERY_CHARS,
                       description="Legal research query or case description")
    top_k_judgments: int = Field(default=5, ge=1, le=10)
    top_k_sections: int = Field(default=3, ge=1, le=6)
    mode: Literal["answer", "retrieve_only"] = "answer"


class JudgmentResult(BaseModel):
    judgment_id: str
    filename: str
    similarity_score: float
    sections_retrieved: list[str]
    token_count: int
    # With ANSWER_TOP_ONLY only the best match is analysed with the search;
    # the rest carry None and answer_status "on_demand" (POST /query/answer).
    llm_answer: str | None = None
    answer_status: AnswerStatus = ANSWER_ON_DEMAND
    # Display fields of the judgment's case card (case_display, subject,
    # headnote, holding, outcome, parties, decision_date), when it has one.
    card: dict | None = None
    download_url: str | None = None
    has_drive_file: bool = False
    # Why the LLM judge ranked this judgment where it did (v2 only).
    reason: str = ""
    # "high" or "medium" from pipeline v2; "" from v1, where the % score is shown instead.
    confidence: str = ""


class SearchResponse(BaseModel):
    query: str
    cleaned_query: str
    intent: dict
    mode: str
    # Whether stage 3.5 rescored the candidates with the cross-encoder. False
    # means the ranking is bi-encoder order, either because reranking is off
    # or because the model could not be loaded.
    # Which retrieval pipeline answered: "v1" (dense) or "v2" (hybrid).
    pipeline: str = "v1"
    reranked: bool = False
    # True when nothing in the corpus cleared the relevance floor. The client
    # shows `message` alone: no judgments, no download links, no answer.
    no_results: bool = False
    message: str = ""
    # Set when the results are a category browse rather than an answer.
    notice: str = ""
    judgments: list[JudgmentResult]
    top_judgment_answer: str | None = None
    latency_ms: int


class SummarizeRequest(BaseModel):
    judgment_id: str


class SummarizeResponse(BaseModel):
    judgment_id: str
    filename: str
    summary: str
    # "ready", or "rate_limited"/"error" when `summary` is a plain notice.
    summary_status: AnswerStatus = "ready"


class AnswerRequest(BaseModel):
    """Analyse one judgment from a search against the query, on demand."""
    query: str = Field(min_length=3, max_length=MAX_QUERY_CHARS)
    judgment_id: str = Field(min_length=1, max_length=200)


class AnswerResponse(BaseModel):
    judgment_id: str
    answer: str | None = None
    answer_status: AnswerStatus
    # True when served from the (query, judgment) answer cache.
    cached: bool = False


class CompareRequest(BaseModel):
    """Judgments to line up side by side, in display order."""
    judgment_ids: list[str]


class CompareField(BaseModel):
    key: str
    label: str


class CompareResponse(BaseModel):
    # The table's columns, in the order they should be shown.
    fields: list[CompareField]
    # One row per judgment, keyed by the field keys above. A field the
    # judgment does not record carries an em dash rather than being absent.
    rows: list[dict]
    # True when the shared LLM budget left one or more rows unfilled; each row
    # also carries its own "status" (contracts.ANSWER_STATUSES).
    rate_limited: bool = False
