from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    MONGO_URL: str = "mongodb://localhost:27017"
    REDIS_URL: str = ""
    DB_NAME: str = "legal_rag"
    OPENAI_API_KEY: str = ""
    
    # Gemini API Settings (Primary)
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.5-flash-lite"
    
    # Groq Cloud API Settings (Preserved/Commented in active provider)
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "llama-3.3-70b-versatile"
    GROQ_BASE_URL: str = "https://api.groq.com/openai/v1"

    # Retrieval: where the ingestion pipeline writes its node->vector index.
    # Empty means "use backend/app/connection". Accepts a directory of
    # *_mappings.json files or a single JSON file.
    JSON_INDEX_PATH: str = ""

    # Retrieval: token budget for the context handed to the LLM.
    MAX_CONTEXT_TOKENS: int = 8000

    # ── Embedding model ──────────────────────────────────────────────────
    # One source of truth for both sides of the vector space. The ingestion
    # pipeline and the query embedder MUST agree, so neither hardcodes a name.
    #
    # bge-base is 768-dimensional where bge-small was 384. A ChromaDB
    # collection fixes its dimensionality at creation, so changing the model
    # REQUIRES changing CHROMA_COLLECTION too — the old collection is left on
    # disk untouched, which makes rollback a single env-var flip.
    EMBEDDING_MODEL: str = "BAAI/bge-base-en-v1.5"
    EMBEDDING_DIM: int = 768
    CHROMA_COLLECTION: str = "legal_embeddings_v2"

    # ── Chunking ─────────────────────────────────────────────────────────
    # BGE models have a hard 512-token window and sentence-transformers
    # truncates past it SILENTLY. Before chunking, 33% of section nodes
    # exceeded it and 49.4% of all section text never reached the index —
    # worst of all in ANALYSIS_RATIO, where the ratio decidendi lives.
    #
    # 480 leaves room for the [CLS]/[SEP] pair and a little slack; the
    # chunker measures with the model's own tokenizer, not a word heuristic,
    # so the budget is exact rather than approximate.
    CHUNK_MAX_TOKENS: int = 480
    CHUNK_OVERLAP_SENTENCES: int = 2

    # ── Reranking ────────────────────────────────────────────────────────
    # A bi-encoder scores query and passage independently, which is why the
    # measured separation between judgments is only 0.029 cosine. A cross
    # encoder reads both together and is the single biggest precision lever
    # once the corpus is large enough for that margin to matter.
    #
    # Measured on the 20-query labelled set, 11 judgments, 16 CPU cores,
    # all three runs with identical candidates and the tie fix applied:
    #
    #   no rerank                       p@1 0.650   MRR 0.817     151ms
    #   BAAI/bge-reranker-base          p@1 0.600   MRR 0.771  16,953ms
    #   ms-marco-MiniLM-L-6-v2          p@1 0.850   MRR 0.917   2,397ms
    #
    # The small model wins on both axes, which is not the usual expectation.
    # bge-reranker-base scored every candidate in a narrow band of negative
    # logits (-10.2 to -4.6) — it treats 400-word legal passages as uniformly
    # irrelevant and its ordering is close to noise. MiniLM is trained on
    # MS MARCO passage ranking, which is the same shape of task: find the
    # passage that answers this question.
    #
    # Re-measure both when the corpus grows. A larger cross-encoder may earn
    # its cost once there are thousands of candidates to separate.
    #
    # RERANK_ENABLED false falls back to bi-encoder order — the A/B switch
    # the evaluation harness drives.
    RERANK_ENABLED: bool = True
    RERANKER_MODEL: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    RERANK_CANDIDATES: int = 40

    # ── Abstention ───────────────────────────────────────────────────────
    # The corpus is eleven judgments. Most questions a lawyer asks have no
    # answer in it, and answering them anyway is the worst thing this system
    # can do: a fabricated disposition in a legal tool is not a bad search
    # result, it is a professional hazard.
    #
    # Chosen by sweeping the threshold over the 20 labelled queries and 10
    # deliberately out-of-corpus ones:
    #
    #   threshold   in-corpus kept   out-of-corpus rejected
    #      0.00        20/20                0/10
    #      0.15        18/20                9/10
    #      0.20        18/20               10/10   <- chosen
    #      0.50        16/20               10/10
    #
    # The two classes OVERLAP, so no threshold is clean. "who owns a brand
    # name after a company is restructured" is a real question with a real
    # answer in the corpus (the Shezan trade mark case) and scores 0.0001,
    # while "imran khan bail case" — which has no answer — scores 0.1598. A
    # pure relevance cut cannot tell those apart, and pretending otherwise by
    # tuning the number is how a threshold stops meaning anything.
    #
    # 0.20 is chosen because the errors are not symmetric. Refusing a query
    # that had an answer costs the researcher another search. Answering one
    # that did not can put a disposition from an unrelated case in front of
    # someone about to rely on it. The first is an inconvenience; the second
    # is the failure this system exists to avoid.
    #
    # Cost, stated plainly: 2 of 20 legitimate queries are refused at this
    # setting, both pure paraphrases with almost no wording in common with the
    # judgment. That is the weakness a lexical (BM25) signal alongside the
    # dense one would address; a threshold cannot.
    RELEVANCE_THRESHOLD: float = 0.20

    # ── Precision v2: one flag per component ─────────────────────────────
    # Every stage of the v2 pipeline is switchable, so each one's contribution
    # can be measured by turning it off (eval/run_eval.py --ablate). A stage
    # that does not improve the dev-set numbers is switched off, not kept.
    # All default OFF until the integrator wires and measures them.
    # Master switch: route searches through app.retrieval.pipeline_v2. With it
    # off, live search is exactly the v1 path regardless of the flags below;
    # with it on, the component flags choose what v2 runs.
    #
    # ON since dev measurement (20 answerable, 40 no-answer queries incl. the
    # owner's real out-of-corpus ones): right case first 15/20 vs 13/20 for v1,
    # and 0/40 wrong answers vs v1's 2/40 (v1 answered both queries about a
    # deleted judgment with an unrelated case). Set False to return to v1.
    USE_V2_PIPELINE: bool = True
    USE_QUERY_ANALYZER: bool = False   # Q:  LLM query understanding (Agent D)
    USE_EXACT_MATCH: bool = True     # citation and party queries resolve by lookup, not by guess
    USE_BM25: bool = True     # the largest single gain in fusion (before-rerank hit@1 .773 -> .864)
    USE_CARDS: bool = True     # no p@1 gain alone, but its two retrievers are half the votes the agreement gate counts
    USE_FUSION: bool = True     # judgment-level RRF beat union ordering in every configuration
    USE_LLM_JUDGE: bool = False        # J:  listwise LLM judge over the top 10 (Agent E)

    # Where the lexical index and the card vectors live. New stores, so building
    # them never disturbs the live chunk collection.
    LEXICAL_DB_PATH: str = ""          # empty = backend/lexical.db
    CARDS_COLLECTION: str = "legal_cards_v1"

    # ── Pipeline v2 ranking (app/retrieval/pipeline_v2.py, fusion.py) ────
    # Measured on dev (22 positives, 29 negatives, 11 judgments — directional
    # only; recalibrate at full scale):
    #
    # * Fusion ORDERS, the cross-encoder GATES. Letting the cross-encoder
    #   reorder the fused window demoted 4 correct top-1 judgments and promoted
    #   1 (p@1 16/22 vs 19/22 with fusion order), in every configuration tried.
    #   It still decides abstention and the displayed relevance, which means
    #   displayed scores are not always in descending order.
    # * The floor: lowered from 0.02 to 0.002 after measuring that it was
    #   refusing correct answers at no gain in precision. Re-phrasings of one
    #   question ("property dispute between husband and wife" 0.038 vs "...wife
    #   over property" 0.018 vs the same with a typo 0.005) put the RIGHT
    #   judgment first every time - 3 of 4 retrievers ranked it first in all of
    #   them - yet the cross-encoder score alone decided whether it was shown.
    #   Measured on the dev set plus 14 clearly out-of-archive queries:
    #       floor 0.02   ->  3/5 re-phrasings answered, 0/14 leaked
    #       floor 0.002  ->  5/5 re-phrasings answered, 0/14 leaked
    #   Every negative that does get through this gate is above the separate
    #   V2_CONFIDENT_RELEVANCE cut (0.25), so the floor was never what held
    #   them back; retriever agreement (V2_AGREEMENT_MIN) is the real guard.
    #   Re-sweep at 1,000 and 3,000 judgments: more candidates will push the
    #   top negative up.
    # * Section weighting changed nothing and is not wired; contextual-header
    #   chunks (legal_embeddings_v3_ctx) scored slightly worse than the live
    #   collection, so dense search stays on the live collection.
    V2_RELEVANCE_THRESHOLD: float = 0.002
    # The floor alone let "imran khan bail case" through (top relevance 0.160,
    # inside the band where real answers also sit). Between the floor and
    # V2_CONFIDENT_RELEVANCE the top judgment is shown only if at least
    # V2_AGREEMENT_MIN retrievers ranked it first. See pipeline_v2._agreement_gate.
    V2_CONFIDENT_RELEVANCE: float = 0.25
    V2_AGREEMENT_MIN: int = 3
    V2_FINAL_ORDER: str = "fusion"     # "fusion" | "rerank"
    # The cross-encoder only gates now, so it needs to see the head of the fused
    # list, not 30 judgments: at 3,000 docs 30 × 3 passages is ~90 pairs, ~5-9s.
    V2_RERANK_JUDGMENTS: int = 10
    V2_RERANK_PASSAGES: int = 3
    V2_RERANK_INCLUDE_CARD: bool = False   # +2 p@1 at a 0.20 floor, nothing at 0.02
    V2_CHUNK_POOL: int = 200
    V2_CARD_POOL: int = 50
    FUSION_K: int = 60
    FUSION_WEIGHTS: dict = {}          # retriever -> weight; empty = 1.0 each, untuned
    DENSE_CHUNKS_COLLECTION: str = ""  # empty = the live collection
    JUDGE_TIMEOUT: float = 6.0
    JUDGE_TOP_N: int = 10
    # ONNX int8 is 1.2-1.8x faster and agrees with torch at Spearman 0.9965
    # pooled, but dips to 0.94 on individual queries and changed the top
    # judgment on 3 of 51, so it is opt-in.
    RERANKER_BACKEND: str = "torch"    # "torch" | "onnx"

    # ── Case-description search (Agent N) ────────────────────────────────
    # Queries of NARRATIVE_MIN_WORDS+ words (contracts.NARRATIVE_MIN_WORDS) are
    # split into facets and searched facet-by-facet against the matching
    # sections. Without the LLM judge the top result of a narrative query is
    # never labelled better than NARRATIVE_MAX_CONFIDENCE: measured on the
    # analysis set, 2 of 7 out-of-archive descriptions matched a similar-area
    # case that the cross-encoder and the agreement gate both passed.
    NARRATIVE_FACETS: bool = True
    NARRATIVE_MAX_CONFIDENCE: str = "medium"   # owner's choice: show, labelled "verify"

    # ── Shared Gemini budget (Agent M) ───────────────────────────────────
    # Free tier: 15 requests/min for the WHOLE project. Every call in the
    # search path goes through one limiter so a burst queues instead of
    # failing, and only the top judgment is analysed automatically.
    LLM_RPM_LIMIT: int = 14
    LLM_MAX_CONCURRENCY: int = 3
    LLM_MAX_WAIT_S: float = 20.0        # queue at most this long, then report rate_limited
    ANSWER_TOP_ONLY: bool = True        # others are analysed on demand (POST /query/answer)
    MAX_QUERY_CHARS: int = 4000
    TORCH_THREADS: int = 0              # 0 = automatic
    QUERY_RECORDER_ENABLED: bool = True
    QUERY_RECORDER_SLIM: bool = True    # no 768-float vector, no full contexts

    # ── Authentication (Agent S) ─────────────────────────────────────────
    # OFF until the integrator has wired the frontend to send tokens; turning
    # it on early would lock the current UI out of search.
    AUTH_REQUIRED: bool = False
    JWT_EXPIRE_MINUTES: int = 720
    USER_SEARCHES_PER_MINUTE: int = 10
    USER_ANSWERS_PER_DAY: int = 200
    # Anonymous callers are keyed by client IP, and behind the Vite dev proxy
    # every browser arrives as 127.0.0.1 — so with this on and auth off, ALL
    # users would share one 10-searches/min allowance. Off until AUTH_REQUIRED
    # is on and every request carries its own identity. The shared Gemini
    # limiter (LLM_RPM_LIMIT) protects the quota meanwhile.
    RATE_LIMIT_ANONYMOUS: bool = False

    # ── Ingestion completeness (Agent I) ─────────────────────────────────
    # The contextual collection is never read by live search (it scored
    # slightly worse) but doubled embedding CPU on every upload.
    CONTEXTUAL_INDEXING: bool = False
    # Where embedding writes the per-judgment node index JSON. Empty = the
    # default backend/app/connection. Scratch and test runs point it elsewhere so
    # they never drop files into the live index.
    CONNECTION_DIR: str = ""

    # ── Query analyzer (app/retrieval/query_analyzer.py) ─────────────────
    # The analyzer always runs its regex path; the LLM path adds the legal
    # rewrite. On the Gemini free tier (15 requests/min for the whole project)
    # every search spending a call on it competes with ingestion and answers,
    # so the LLM half can be switched off independently of the analyzer.
    QUERY_ANALYZER_TIMEOUT: float = 3.0
    QUERY_ANALYZER_CACHE_SIZE: int = 1024
    QUERY_ANALYZER_USE_LLM: bool = True

    # ── Case cards (app/ingestion/case_card.py) ──────────────────────────
    # One LLM call per judgment. The cap is a per-process safety stop against a
    # runaway loop; it must exceed the corpus size for a full build.
    CASE_CARD_MAX_TOKENS: int = 900
    CASE_CARD_CALL_PAUSE_S: float = 1.0
    CASE_CARD_MAX_LLM_CALLS: int = 4000

    # ── Admin uploads (several PDFs at once from the Cases page) ─────────
    # Uploads are queued: this many judgments are extracted/OCR'd and parsed at
    # the same time; the index stage (vectors, card, keyword index) runs one
    # judgment at a time, as in bulk ingest. Raise to 3-4 on a paid Gemini tier
    # if the CPU keeps up; OCR of scanned PDFs is the heavy part.
    ADMIN_INGEST_CONCURRENCY: int = 2

    # ── Bulk ingestion (backend/ingest_bulk.py) ──────────────────────────
    BULK_LLM_CONCURRENCY: int = 3      # parallel Gemini parses; raise on a paid tier
    BULK_OCR_WORKERS: int = 0          # 0 = automatic (cores and free RAM)
    BULK_MAX_ATTEMPTS: int = 5
    BULK_BACKOFF_BASE_S: float = 5.0
    BULK_PARSE_TIMEOUT_S: int = 600
    BULK_REPORT_DIR: str = ""          # empty = backend/ingest_reports

    # Parser Configuration
    USE_LLM_PARSER: bool = True
    PARSER_MODE: str = "hybrid"  # Options: "hybrid", "pure_llm", "rule_based"

    # LLM Provider: "gemini", "groq", or "ollama"
    LLM_PROVIDER: str = "gemini"

    # Ollama Local Settings (Fallback)
    OLLAMA_MODEL: str = "mistral"
    OLLAMA_BASE_URL: str = "http://localhost:11434/v1"

    # SMTP & Email Settings
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASS: str = ""
    FRONTEND_URL: str = "http://localhost:5173"
    REACTIVATION_TOKEN_EXPIRY_DAYS: int = 30

    # Auth & Security
    JWT_SECRET: str = "long_random_string_here"
    GOOGLE_CLIENT_ID: str = ""
    RECAPTCHA_SECRET_KEY: str = ""
    RECAPTCHA_SCORE_THRESHOLD: float = 0.5
    CONTACT_RECEIVER_EMAIL: str = "verdictaisupport@gmail.com"

    # Google Drive Integration
    GOOGLE_DRIVE_TARGET_EMAIL: str = "verdictaisupport@gmail.com"
    GOOGLE_DRIVE_FOLDER_ID: str = ""
    GOOGLE_SERVICE_ACCOUNT_FILE: str = "service_account.json"
    GOOGLE_DRIVE_TOKEN_FILE: str = "token.json"
    GOOGLE_DRIVE_CLIENT_SECRET_FILE: str = "client_secret.json"
    GOOGLE_DRIVE_ENABLED: bool = True

    model_config = SettingsConfigDict(
        env_file=[
            str(Path(__file__).resolve().parents[1] / ".env"),  # backend/.env
            str(Path(__file__).resolve().parents[2] / ".env"),  # repo-root .env (fallback)
        ],
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
