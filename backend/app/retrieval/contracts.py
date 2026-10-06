"""
Shared contracts for the precision-v2 retrieval pipeline.

Every workstream builds against these types rather than against each other's
code, so the agents can work in parallel and integrate without renegotiating.
Change a contract here and every consumer must be told; add a field and nothing
breaks, because all the dicts are `total=False`.

They are TypedDicts, not dataclasses, on purpose: the existing pipeline passes
plain dicts end to end (search_chunks, rank_judgments, context_expander), and
these types describe those dicts rather than replacing them.

Pipeline, for orientation:

    query --Q--> QueryAnalysis
          --R1..R5--> list[Candidate]      (one list per retriever, ranked)
          --F--> judgment-level fusion     (Candidate.scores["rrf"])
          --K--> cross-encoder             (Candidate.scores["rerank"], ["relevance"])
          --J--> LLM judge                 (Candidate.scores["judge"], reason)
"""

from typing import Literal, Protocol, TypedDict, runtime_checkable

# ── Query types ──────────────────────────────────────────────────────────────
# What kind of question it is decides which retrievers and which sections to
# trust. A citation query should be answered by exact match; a paraphrase query
# by meaning. Treating them alike is most of why precision varies by group.
QueryType = Literal[
    "citation",     # names a case number:            "C.A. 5-Q/2014"
    "entity",       # names a party, place or judge:  "Pirzada Noor-ul-Basar"
    "statute",      # names a provision:              "Article 199", "s.302 PPC"
    "issue",        # states a legal question:        "Was the penalty proportionate?"
    "paraphrase",   # describes facts in plain words: "who owns a brand after restructuring"
    "disposition",  # asks about an outcome:          "appeal dismissed with no order as to costs"
    "vague",        # a category, not a question:     "any family dispute case"
    "unknown",
]

QUERY_TYPES: tuple[str, ...] = (
    "citation", "entity", "statute", "issue", "paraphrase", "disposition", "vague", "unknown",
)

# ── Retriever names ──────────────────────────────────────────────────────────
# Candidate.source carries one of these; fusion weights and ablation flags key
# off them, so they are fixed strings rather than free text.
RetrieverName = Literal["exact", "bm25_chunks", "bm25_cards", "dense_chunks", "dense_cards"]

RETRIEVERS: tuple[str, ...] = ("exact", "bm25_chunks", "bm25_cards", "dense_chunks", "dense_cards")

# ── Subject areas ────────────────────────────────────────────────────────────
# A fixed vocabulary, shared by the case-card generator (which assigns one per
# judgment), the query analyzer (which may infer one from the question) and the
# evaluation set (which stratifies by it). Free-text subjects would never match
# across the three. "Other" exists so the generator is never forced to guess.
SUBJECT_AREAS: tuple[str, ...] = (
    "Service law",
    "Service tribunal jurisdiction",
    "Election law",
    "Land and revenue",
    "Evacuee property",
    "Property and title",
    "Tenancy",
    "Family law",
    "Inheritance and succession",
    "Contract",
    "Intellectual property",
    "Company and corporate",
    "Banking and finance",
    "Taxation",
    "Customs and excise",
    "Criminal law",
    "Bail",
    "Narcotics",
    "Constitutional law",
    "Fundamental rights",
    "Writ jurisdiction",
    "Contempt of court",
    "Civil procedure",
    "Criminal procedure",
    "Administrative law",
    "Labour and employment",
    "Local government",
    "Environmental law",
    "Arbitration",
    "Other",
)

Outcome = Literal["allowed", "dismissed", "partly_allowed", "remanded", "disposed", "unknown"]


class CaseRef(TypedDict):
    """One normalised case number. Produced by app.retrieval.case_keys."""
    key: str            # "CA-5-Q-2014" — the exact-match join key
    type: str           # "CA"
    number: str         # "5"
    registry: str | None  # "Q"
    year: int           # 2014
    display: str        # "Civil Appeal No. 5-Q of 2014"


class QueryAnalysis(TypedDict, total=False):
    """What the query analyzer (Agent D) understood the question to be.

    Every retriever receives this instead of a bare string, so a retriever can
    use the rewrite, the entities, or both.
    """
    raw: str                    # as typed
    cleaned: str                # after clean_query (keeps / ( ) § and numbers)
    query_type: QueryType
    case_refs: list[CaseRef]    # from case_keys.parse_case_numbers
    parties: list[str]
    statutes: list[str]         # normalised: "Article 199", "Section 302 PPC"
    years: list[int]
    registry: str | None
    subject: str | None         # one of SUBJECT_AREAS, if confidently inferred
    outcome: Outcome | None     # only when the user asks about an outcome
    rewrite: str                # the question restated in legal language
    expansions: list[str]       # 0-2 alternative phrasings, for paraphrase queries
    source: Literal["llm", "regex"]  # "regex" means the LLM path failed or timed out


class Candidate(TypedDict, total=False):
    """One retrieved item, from any retriever, at any stage.

    Retrievers fill the identity fields, `source`, `rank` and `score`. Later
    stages add to `scores` and never overwrite what an earlier stage wrote, so
    the full provenance of a ranking survives to the eval logs.
    """
    judgment_id: str            # pdf_id — always present
    mongo_doc_id: str           # the MongoDB node; "" for a card-level hit
    vector_id: str              # Chroma id ("{node_id}::{chunk}") or FTS rowid
    section_type: str           # HEADER_CORAM … FINAL_ORDER; "CARD" for card hits
    heading: str
    chunk_index: int
    text: str                   # the passage, so rerankers need no second lookup
    source: RetrieverName
    rank: int                   # 0-based position within its own retriever's list
    score: float                # the retriever's native score (cosine, -bm25, 1.0)
    scores: dict[str, float]    # added by later stages: rrf, rerank, relevance, judge
    reason: str                 # the LLM judge's one-line justification


class CaseCard(TypedDict, total=False):
    """Structured, grounded facts about one judgment (Agent B).

    Stored one per judgment in the MongoDB `case_cards` collection, keyed by
    judgment_id. Feeds exact match, BM25 over cards, dense card vectors, the
    contextual chunk headers, the LLM judge and the compare table.

    Metadata fields come from deterministic extraction and are trustworthy. The
    LLM fields (subject … keywords) must be grounded in the judgment text; a
    field the text does not support is left empty rather than inferred.
    """
    judgment_id: str
    # deterministic, from the raw text head + HEADER_CORAM
    case_refs: list[CaseRef]
    case_keys: list[str]        # flattened case_refs[*].key, indexed for exact match
    case_display: str
    bench: list[str]
    appellant: str
    respondent: str
    lower_court: str
    impugned_date: str
    decision_date: str
    counsel: list[str]
    statutes: list[str]
    citations: list[str]        # reported citations: "2000 SCMR 1046"
    outcome: Outcome
    # LLM, grounded, one call per judgment
    subject: str                # one of SUBJECT_AREAS
    headnote: str               # 2-3 sentences; replaces the templated root summary
    issues: list[str]
    holding: str
    keywords: list[str]
    # provenance
    metadata_version: int
    card_model: str
    card_version: int


@runtime_checkable
class Retriever(Protocol):
    """Every retriever in R1..R5 implements this.

    Async because exact match reads MongoDB through motor; the synchronous
    retrievers (Chroma, SQLite) simply do their work inside the coroutine.
    Must return candidates sorted best-first with `rank` filled 0..k-1, and
    must return [] rather than raise when it has nothing — one failing
    retriever must never take down a search.
    """
    name: str

    async def retrieve(self, analysis: QueryAnalysis, k: int) -> list[Candidate]: ...


def with_ranks(candidates: list[Candidate], source: str) -> list[Candidate]:
    """Stamp `rank` and `source` on an already-sorted list. For retriever authors."""
    for index, candidate in enumerate(candidates):
        candidate["rank"] = index
        candidate["source"] = source  # type: ignore[typeddict-item]
        candidate.setdefault("scores", {})
    return candidates


# ── Contextual chunk header ──────────────────────────────────────────────────
# Shared here rather than owned by the card generator, because the reindex must
# be able to call it while cards are still being built, and must produce the
# same header for a chunk no matter which process writes it.

SECTION_LABELS = {
    "HEADER_CORAM": "Header and Coram",
    "FACTS": "Facts",
    "ARGUMENTS": "Arguments",
    "LEGAL_ISSUES": "Legal Issues",
    "ANALYSIS_RATIO": "Analysis and Ratio",
    "FINAL_ORDER": "Final Order",
    "ROOT": "Case Summary",
    "CARD": "Case Card",
}


def contextual_header(card: "CaseCard | None", section_type: str, fallback_title: str = "") -> str:
    """The line prepended to every chunk before it is embedded and indexed.

    A passage from the middle of ANALYSIS_RATIO says nothing about which case it
    belongs to, so on its own it embeds as anonymous legal prose. Prefixing the
    case, its subject and its division lets both dense and lexical retrieval
    attribute it: a query about election petitions now also matches the
    "Election law" in the header of every chunk of an election judgment.

        [Civil Appeal No. 5-Q of 2014 | Election law | Analysis and Ratio]

    Fields the card does not have are omitted rather than written as blanks.
    With no card at all, the node's own title stands in for the case.
    """
    card = card or {}
    parts = [
        (card.get("case_display") or fallback_title or "").strip(),
        (card.get("subject") or "").strip(),
        SECTION_LABELS.get((section_type or "").upper(), (section_type or "").title()),
    ]
    parts = [p for p in parts if p and p != "Other"]
    return f"[{' | '.join(parts)}]" if parts else ""


# ════════════════════════════════════════════════════════════════════════════
# Wave 0, round 2: case-description search for many users
# ════════════════════════════════════════════════════════════════════════════
#
# Users describe their case situation in 40-150 words — facts, what each side
# claims, what the courts held, the outcome. These contracts let Agent N
# (narrative retrieval), Agent M (multi-user runtime), Agent S (security) and
# Agent I (ingestion) build in parallel without negotiating shapes.


class Facets(TypedDict, total=False):
    """The parts of a case description, as the user wrote them.

    Extracted by query_analyzer (a cue-based splitter on the free tier, the LLM
    when enabled). Each value is the user's own words for that part, never a
    paraphrase, so retrieval and answer checks stay grounded in what was said.
    A part the user did not describe is absent, not "".
    """
    facts: str          # what happened
    claimant: str       # what the user's side / the appellant says
    respondent: str     # what the other side says
    court_view: str     # what a court below held or reasoned
    outcome_sc: Outcome  # the outcome attributed to the SUPREME COURT specifically;
                         # a High Court's result is NOT this (it is usually reversed or
                         # upheld by the SC, so the two point in opposite directions)


# Words at which a query is treated as a case description rather than a short
# question. Below it, the short-query path (categories, exact match, plain
# fusion) applies unchanged.
NARRATIVE_MIN_WORDS = 25

# QueryAnalysis gains these optional keys (TypedDicts are open via total=False,
# so existing producers and consumers are unaffected):
#     is_narrative: bool
#     facets: Facets


# ── Answers under a shared quota ─────────────────────────────────────────────
# A judgment's analysis is no longer always generated with the search. The
# frontend renders by status, never by sniffing error text out of the answer.
ANSWER_READY = "ready"            # llm_answer holds the analysis
ANSWER_ON_DEMAND = "on_demand"    # not generated yet; POST /query/answer creates it
ANSWER_RATE_LIMITED = "rate_limited"  # the shared Gemini budget is spent; retry later
ANSWER_ERROR = "error"            # generation failed for another reason
ANSWER_STATUSES = (ANSWER_READY, ANSWER_ON_DEMAND, ANSWER_RATE_LIMITED, ANSWER_ERROR)


# ── Per-store ingestion status ───────────────────────────────────────────────
# Stored on documents.index_status. A judgment is "complete" only when every
# REQUIRED store is written; the card is required but may arrive later, in the
# card wave, so a judgment can be searchable before it is complete.
INDEX_STORES = ("tree", "dense", "fts", "card", "card_vector")
INDEX_REQUIRED_FOR_SEARCH = ("tree", "dense", "fts")


class IndexStatus(TypedDict, total=False):
    tree: bool
    dense: bool
    fts: bool
    card: bool          # a COMPLETE card; a metadata_only card from a 429 is False
    card_vector: bool
    last_error: str
    updated_at: str     # ISO timestamp
    report: dict        # the last index_judgment report, {store: "ok" | "error: ..."}


# ── Auth token payload ───────────────────────────────────────────────────────
class TokenPayload(TypedDict):
    sub: str                         # user id (users collection) or admin id
    role: Literal["user", "admin"]
    exp: int                         # unix seconds
