"""
Shared plumbing for the evaluation set: the dataset format, the dev/test split,
the test-set freeze, corpus lookups and a quiet way to run the pipeline.

Why one module
--------------
Five scripts (build_datasets, label_real_queries, import_labels, synth_queries,
run_eval) all have to agree on three things, and a disagreement in any of them
silently corrupts every number the harness reports:

1. **Which split a judgment belongs to.** The split is decided by a stable hash
   of the judgment's pdf_id, never by position or by random draw, so (a) every
   query about one judgment lands in the same split — synthetic queries cannot
   leak a test judgment into dev — and (b) adding 3,000 judgments later does not
   move any of the 11 that are already assigned.
2. **What the test set is.** test.jsonl is frozen by its SHA-256. Anything that
   reads it checks the hash; anything that would change it must be told to.
3. **What a row looks like.** One JSON object per line:

       {"id", "query", "relevant": {pdf_id: grade}, "query_type", "origin",
        "split", "status", "notes", ...optional extras}

   grade 2 = the judgment that answers it, 1 = a genuinely relevant alternate.
   A negative has "relevant": {} and is answered correctly only by abstaining.

Running the pipeline from eval must not write to the real-query log
(app/query/*.json): those files are the record of how *users* ask, and every
eval run used to add one file per query to them (the 10x duplicates of the
legacy queries in that folder are exactly that). `quiet_pipeline()` swaps the
recorder for a no-op in this process only; nothing under app/ is modified.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent
BACKEND_DIR = EVAL_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

DATASETS_DIR = EVAL_DIR / "datasets"
LABELS_DIR = EVAL_DIR / "labels"
SYNTH_DIR = EVAL_DIR / "synthetic"
RESULTS_DIR = EVAL_DIR / "results"

DEV_PATH = DATASETS_DIR / "dev.jsonl"
TEST_PATH = DATASETS_DIR / "test.jsonl"
TEST_HASH_PATH = DATASETS_DIR / "test.sha256"

LEGACY_PATH = EVAL_DIR / "queries.json"
NEGATIVES_PATH = EVAL_DIR / "negatives.json"
SYNTH_PATH = SYNTH_DIR / "synthetic_queries.jsonl"
REAL_PROPOSED_PATH = LABELS_DIR / "real_queries_proposed.json"
REAL_REVIEW_PATH = LABELS_DIR / "real_queries_review.md"
REAL_CONFIRMED_PATH = LABELS_DIR / "real_queries_confirmed.jsonl"

# The last three are the case-description (narrative) set; see narrative_lib.py.
ORIGINS = ("real", "synthetic", "negative", "legacy", "synthetic_narrative", "narrative_negative", "hand_written")
STATUSES = ("confirmed", "proposed")
REQUIRED_FIELDS = ("id", "query", "relevant", "query_type", "origin", "split", "status", "notes")

# Bumping the salt reshuffles every judgment between dev and test. Never do it
# once a test number has been reported: it would put test judgments into dev.
SPLIT_SALT = "legal-hybrid-rag/split-v1"
TEST_PERCENT = 40


# ── Split ────────────────────────────────────────────────────────────────────

def split_for_key(key: str) -> str:
    """dev or test, from a stable hash. Same key, same answer, forever."""
    digest = hashlib.sha256(f"{SPLIT_SALT}:{key}".encode("utf-8")).hexdigest()
    return "test" if int(digest[:8], 16) % 100 < TEST_PERCENT else "dev"


def primary_judgment(relevant: dict[str, int]) -> str | None:
    """The grade-2 judgment that decides the split (lowest id if several)."""
    top = sorted(pid for pid, grade in relevant.items() if grade >= 2)
    if top:
        return top[0]
    rest = sorted(relevant)
    return rest[0] if rest else None


def split_for_row(row: dict) -> str:
    """Split by the primary judgment; a negative (no judgment) by its own id."""
    primary = primary_judgment(row.get("relevant") or {})
    return split_for_key(primary if primary else f"query:{row['id']}")


# ── Text helpers ─────────────────────────────────────────────────────────────

def normalise_query(text: str) -> str:
    """For de-duplication only: case, whitespace and trailing punctuation."""
    return re.sub(r"\s+", " ", text.strip().lower()).rstrip(" ?.!")


def stable_id(prefix: str, text: str) -> str:
    return f"{prefix}-{hashlib.sha1(normalise_query(text).encode('utf-8')).hexdigest()[:10]}"


_TOKEN = re.compile(r"[a-z0-9]+")


def tokens(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


def ngrams(toks: list[str], n: int = 4) -> set[tuple[str, ...]]:
    return {tuple(toks[i:i + n]) for i in range(len(toks) - n + 1)}


# ── Dataset IO ───────────────────────────────────────────────────────────────

def validate_row(row: dict) -> None:
    """Raise on a malformed row: a bad label is worse than a missing one."""
    from app.retrieval.contracts import QUERY_TYPES

    missing = [f for f in REQUIRED_FIELDS if f not in row]
    assert not missing, f"row {row.get('id')} missing {missing}"
    assert row["query"].strip(), f"row {row['id']} has an empty query"
    assert row["query_type"] in QUERY_TYPES, f"row {row['id']}: bad query_type {row['query_type']!r}"
    assert row["origin"] in ORIGINS, f"row {row['id']}: bad origin {row['origin']!r}"
    assert row["status"] in STATUSES, f"row {row['id']}: bad status {row['status']!r}"
    assert row["split"] in ("dev", "test"), f"row {row['id']}: bad split {row['split']!r}"
    assert isinstance(row["relevant"], dict), f"row {row['id']}: relevant must be a dict"
    for pid, grade in row["relevant"].items():
        assert grade in (1, 2), f"row {row['id']}: grade {grade} for {pid} must be 1 or 2"
    if row["relevant"]:
        assert any(g == 2 for g in row["relevant"].values()), f"row {row['id']}: no grade-2 judgment"
    if row["origin"] in ("negative", "narrative_negative"):
        assert not row["relevant"], f"row {row['id']}: a negative cannot have relevant judgments"


def read_jsonl(path: Path) -> list[dict]:
    rows = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if line.strip():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise ValueError(f"{path}:{line_no}: {e}") from e
    return rows


def dumps_jsonl(rows: list[dict]) -> str:
    # sort_keys + fixed separators: the same rows always produce the same bytes,
    # which is what lets a hash stand for the content.
    return "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rows)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def recorded_test_hash() -> str | None:
    if not TEST_HASH_PATH.exists():
        return None
    return TEST_HASH_PATH.read_text(encoding="utf-8").split()[0].strip()


def check_test_frozen() -> tuple[bool, str]:
    """(ok, message). ok is False when test.jsonl differs from its recorded hash."""
    if not TEST_PATH.exists():
        return False, f"{TEST_PATH} does not exist — run eval/build_datasets.py"
    expected = recorded_test_hash()
    if expected is None:
        return False, f"{TEST_HASH_PATH} is missing — the test set was never frozen"
    actual = sha256_file(TEST_PATH)
    if actual != expected:
        return False, (f"test.jsonl hash {actual[:16]}... does not match the frozen "
                       f"{expected[:16]}... in test.sha256")
    return True, f"test set frozen, sha256 {actual[:16]}..."


def load_legacy_file(path: Path) -> list[dict]:
    """Read the old {"queries": [{query, expect, group}]} format as new-format rows."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = []
    for index, item in enumerate(payload["queries"], start=1):
        rows.append({
            "id": f"legacy-{index:02d}",
            "query": item["query"],
            "relevant": {item["expect"]: 2},
            "query_type": LEGACY_TYPES.get(item["query"], "unknown"),
            "origin": "legacy",
            "split": split_for_key(item["expect"]),
            "status": "confirmed",
            "notes": item.get("note", ""),
            "legacy_group": item.get("group", "-"),
        })
    return rows


def load_dataset(path: Path) -> list[dict]:
    """A .jsonl dataset, or an old-format queries.json, as validated rows."""
    if path.suffix == ".json":
        rows = load_legacy_file(path)
    else:
        rows = read_jsonl(path)
    for row in rows:
        validate_row(row)
    return rows


# The legacy file groups by "what it tests" (subject/paraphrase/issue/...);
# "subject" is not a query type, so each legacy query was typed by hand here.
# The original group is kept as legacy_group, so --by-group still reproduces
# the old breakdown.
LEGACY_TYPES: dict[str, str] = {
    "Is a claim relating to dower within the jurisdiction of a Family Court?": "issue",
    "dispute over wrong entries in the revenue record between spouses": "paraphrase",
    "trade mark assignment agreement was incorrectly relied upon": "issue",
    "who owns a brand name after a company is restructured": "paraphrase",
    "election petition where the winning margin was only sixty five votes": "paraphrase",
    "challenge to a narrow win in a provincial assembly constituency in Balochistan": "paraphrase",
    "general elections 2013 National Assembly seat NA-266 Nasirabad Jaffarabad": "entity",
    "evacuee land granted and later disputed in Tando Adam": "entity",
    "agricultural land allotted after partition and the title later questioned": "paraphrase",
    "seniority and promotion of police officers before a service tribunal": "issue",
    "lower school course dates determining a police officer's seniority": "paraphrase",
    "did the Service Tribunal have jurisdiction to entertain the service appeal": "issue",
    "civil servant denied a fair opportunity of hearing by the tribunal": "issue",
    "contempt application dismissed by the High Court of Balochistan": "entity",
    "when will this Court decline leave to appeal under Article 185(3)": "statute",
    "civil revision dismissed by the High Court of Balochistan at Quetta": "entity",
    "constitutional petitions decided by the High Court of Sindh at Karachi in 2021": "entity",
    "two service appeals raising common questions of law decided together": "paraphrase",
    "appeal allowed and the impugned judgment set aside with parties bearing their own costs": "disposition",
    "appeal dismissed with no order as to costs for want of merit": "disposition",
}


# ── Query-type heuristic (a proposal for the human, never a label) ───────────

_CASE_NO = re.compile(
    r"\b(c\.?\s?a\.?|c\.?\s?p\.?|civil appeal|civil petition|criminal appeal|crl\.?\s?a\.?|"
    r"constitution petition|writ petition|petition)\s*(no\.?)?\s*\d+(-[a-z])?\s*(/|of)\s*\d{2,4}\b",
    re.I,
)
_REPORTED = re.compile(r"\b(19|20)\d{2}\s+(scmr|pld|clc|ylr|mld|plc|ptd|pcrlj|sc)\b", re.I)
_STATUTE = re.compile(r"\b(article|section|s\.|order|rule)\s*\d+|\bact\b|\bordinance\b|\bppc\b|\bcrpc\b|\bcpc\b", re.I)
_DISPOSITION = re.compile(r"\b(dismissed|allowed|set aside|remanded|acquitted|costs|granted|disposed)\b", re.I)
_QUESTION = re.compile(r"^(is|are|was|were|can|could|does|did|do|when|whether|what|who|why|how|should|must)\b", re.I)
_PROPER = re.compile(r"\b(mst\.|vs\.?|v\.|versus)\b|\b[A-Z][a-z]+(?:[- ][A-Z][a-z]+){1,}", re.U)


def guess_query_type(query: str) -> str:
    """A cheap first guess shown on the review sheet; the human overrides it."""
    q = query.strip()
    if _CASE_NO.search(q) or _REPORTED.search(q):
        return "citation"
    if _STATUTE.search(q):
        return "statute"
    if _QUESTION.search(q):
        return "issue"
    if len(tokens(q)) <= 4:
        return "vague"
    if _PROPER.search(q[1:]):
        return "entity"
    if _DISPOSITION.search(q):
        return "disposition"
    return "paraphrase"


# ── Corpus (read-only) ───────────────────────────────────────────────────────

async def corpus_judgments() -> dict[str, dict]:
    """pdf_id -> {filename, title} for every judgment with nodes in MongoDB."""
    from app.database import connect_db, db

    if not db.is_connected:
        await connect_db()
    if not db.is_connected:
        return {}
    out: dict[str, dict] = {}
    async for node in db.nodes.find({"type": "parent"}, {"pdf_id": 1, "title": 1, "_id": 0}):
        out[node["pdf_id"]] = {"title": (node.get("title") or "").strip(), "filename": ""}
    async for doc in db.documents.find({}, {"pdf_id": 1, "filename": 1, "_id": 0}):
        if doc.get("pdf_id") in out:
            out[doc["pdf_id"]]["filename"] = doc.get("filename") or ""
    return out


async def judgment_text(pdf_id: str) -> dict[str, str]:
    """section_type -> text for one judgment."""
    from app.database import db

    sections: dict[str, str] = {}
    async for node in db.nodes.find({"pdf_id": pdf_id}, {"section_type": 1, "text": 1, "_id": 0}):
        sections[node.get("section_type") or "?"] = node.get("text") or ""
    return sections


# ── Pipeline ─────────────────────────────────────────────────────────────────

def quiet_pipeline() -> None:
    """Stop eval queries being written to the real-user query log (this process only)."""
    import app.retrieval.orchestrator as orchestrator

    orchestrator.record_query = lambda *args, **kwargs: None


async def run_query(query: str, top_k: int) -> dict:
    """One retrieve-only run: ranked ids, scores, abstention, latency."""
    import time

    from app.retrieval.orchestrator import MODE_RETRIEVE_ONLY, retrieve_and_answer

    started = time.perf_counter()
    result = await retrieve_and_answer(
        raw_query=query,
        top_k_judgments=top_k,
        top_k_sections=3,
        mode=MODE_RETRIEVE_ONLY,
    )
    elapsed = (time.perf_counter() - started) * 1000
    judgments = result.get("judgments") or []
    return {
        "ranked": [j["judgment_id"] for j in judgments],
        "scores": [float(j.get("similarity_score") or 0.0) for j in judgments],
        "filenames": [j.get("filename", "") for j in judgments],
        "no_results": bool(result.get("no_results")),
        "reranked": bool(result.get("reranked")),
        "latency_ms": elapsed,
    }


def _self_check() -> None:
    # Split is deterministic and roughly 60/40 over many keys.
    keys = [f"pdf-{i}" for i in range(2000)]
    first = [split_for_key(k) for k in keys]
    assert first == [split_for_key(k) for k in keys]
    share = first.count("test") / len(first)
    assert 0.35 < share < 0.45, share
    # Every query about one judgment shares a split.
    a = {"id": "x", "relevant": {"pdf-7": 2, "pdf-9": 1}}
    b = {"id": "y", "relevant": {"pdf-7": 2}}
    assert split_for_row(a) == split_for_row(b) == split_for_key("pdf-7")
    # Leakage n-grams.
    assert ("the", "court", "held", "that") in ngrams(tokens("The Court held that, finally"))
    assert guess_query_type("Civil Appeal No. 5-Q of 2014") == "citation"
    assert guess_query_type("Article 199 suo motu") == "statute"
    assert guess_query_type("Was the penalty proportionate?") == "issue"
    assert guess_query_type("family dispute") == "vague"
    print("evallib self-check passed")


if __name__ == "__main__":
    _self_check()
