"""
Shared plumbing for the narrative (case-description) evaluation.

Why a separate module from evallib
----------------------------------
evallib defines the dataset format, the split rule and the frozen short-query
test set; every narrative script reuses those unchanged (one split rule for
the whole harness, so a judgment never sits in narrative_dev and in test at
the same time). What is specific to case descriptions lives here, because
three scripts must agree on it:

* **What a narrative row adds**: ``perspective`` (whose voice: the appellant's
  lawyer, the opposing party, a layperson, ...), ``detail`` ("detailed" |
  "loose") and the three narrative origins. ``query_type`` stays one of
  contracts.QUERY_TYPES ("paraphrase": a description in the user's own
  words), so run_eval.py can still load a narrative dataset.
* **How the hand-written narratives of narrative_baseline_v0.json become rows.**
  That file is frozen; the 23 descriptions and 2 party-misfire queries in it
  are re-read, never copied by hand, so the dataset and the reproduction run
  cannot drift from the frozen baseline.
* **How a description is run.** Through pipeline_v2.retrieve_v2 directly —
  not orchestrator.retrieve_and_answer — because (a) that is the ranking code
  under change, (b) it writes no query log, and (c) it exposes what a
  narrative user actually sees: the shown list after abstention and each
  result's confidence label ("high" = "Strong match", "medium" = "Possible
  match — verify"). The pre-abstention window (pipeline_v2.last_debug) is
  recorded too, so retrieval recall and the gate's decision can be told apart.
* **An LLM guard.** The free tier is 15 requests/min shared by five agents
  and real users. Retrieval should not call Gemini on the default config, but
  flags change under us; ``guard_llm`` counts every _complete call made during
  a measurement and, past a budget, makes it fail the way an unavailable LLM
  fails (the pipeline degrades, the run continues, and the count is reported).
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import evallib as E

NARRATIVE_SYNTH_PATH = E.SYNTH_DIR / "synthetic_narratives.jsonl"
NARRATIVE_REJECTIONS_PATH = E.SYNTH_DIR / "narrative_rejections.jsonl"
NARRATIVE_CALLS_PATH = E.SYNTH_DIR / "narrative_calls.jsonl"
NARRATIVE_NEGATIVES_PATH = E.EVAL_DIR / "narrative_negatives.json"
NARRATIVE_BASELINE_V0 = E.RESULTS_DIR / "narrative_baseline_v0.json"
NARRATIVE_DEV_PATH = E.DATASETS_DIR / "narrative_dev.jsonl"
NARRATIVE_TEST_PATH = E.DATASETS_DIR / "narrative_test.jsonl"
NARRATIVE_TEST_HASH_PATH = E.DATASETS_DIR / "narrative_test.sha256"
NARRATIVE_CANDIDATES_PATH = E.LABELS_DIR / "narrative_negative_candidates.json"

# The four slots the generator fills per judgment, in prompt order.
SYNTH_PERSPECTIVES = {
    "appellant_lawyer": "detailed",      # (a) the side that appealed to the Supreme Court, via its lawyer
    "opposing_party": "detailed",        # (b) the respondent, in their own voice
    "layperson": "loose",                # (c) a victim / affected person, plain words
    "layperson_other_side": "loose",     # (d) a second loose phrasing, from the other side
}
# Hand-written rows add voices the generator does not use.
PERSPECTIVES = tuple(SYNTH_PERSPECTIVES) + (
    "appellant_party", "respondent_lawyer", "third_person", "lawyer", "party",
)
DETAILS = ("detailed", "loose")
NARRATIVE_ORIGINS = ("synthetic_narrative", "narrative_negative", "hand_written")


def validate_narrative_row(row: dict) -> None:
    E.validate_row(row)
    assert row["origin"] in NARRATIVE_ORIGINS, f"row {row['id']}: not a narrative origin {row['origin']!r}"
    assert row.get("perspective") in PERSPECTIVES, f"row {row['id']}: bad perspective {row.get('perspective')!r}"
    assert row.get("detail") in DETAILS, f"row {row['id']}: bad detail {row.get('detail')!r}"
    if not row["relevant"]:
        assert "verify_at_scale" in row, f"row {row['id']}: a negative must say verify_at_scale"


# ── Hand-written rows (from the frozen narrative_baseline_v0.json) ──────────

# Voice of each hand-written description, by its position in the baseline file
# (read against the case cards: who appealed to the Supreme Court). Positional
# because the frozen file has no ids; _self_check asserts the count and kinds
# so an edit to the baseline cannot silently mislabel rows.
_HW_PERSPECTIVE = [
    # detailed (11)
    "respondent_lawyer",   # widow's lawyer; the widow is the respondent
    "appellant_party",     # the heirs, who appealed
    "opposing_party",      # the allottees' children (respondents)
    "appellant_party",     # the purchasers, who appealed
    "appellant_party",     # the clerk (appellant)
    "appellant_lawyer",    # Shezan Services' lawyer (appellant)
    "opposing_party",      # the embassy employee; the government appealed
    "appellant_party",     # the co-owner whose suit was time-barred (appellant)
    "opposing_party",      # the police officer; the department appealed
    "appellant_lawyer",    # the returned candidate's lawyer (appellant)
    "appellant_party",     # the contract Deputy District Attorney (appellant)
    # loose (5): third-person questions
    "third_person", "third_person", "third_person", "third_person", "third_person",
    # out of archive (7)
    "lawyer", "lawyer", "party", "third_person", "lawyer", "third_person", "party",
    # party misfire (2)
    "lawyer", "lawyer",
]


async def full_ids() -> dict[str, str]:
    """8-char prefix -> full pdf_id, for the corpus as it is now."""
    corpus = await E.corpus_judgments()
    out: dict[str, str] = {}
    for pid in corpus:
        assert pid[:8] not in out, f"pdf_id prefix collision on {pid[:8]}"
        out[pid[:8]] = pid
    return out


def hand_written_rows(prefix_to_id: dict[str, str]) -> list[dict]:
    """The 25 rows of narrative_baseline_v0.json as dataset rows (origin hand_written)."""
    baseline = json.loads(NARRATIVE_BASELINE_V0.read_text(encoding="utf-8"))
    src = baseline["rows"]
    assert len(src) == len(_HW_PERSPECTIVE) == 25, (len(src), len(_HW_PERSPECTIVE))
    counters: dict[str, int] = {}
    rows = []
    for item, perspective in zip(src, _HW_PERSPECTIVE):
        kind = item["kind"]
        family = ("detailed" if kind == "detailed" else "loose" if kind == "loose"
                  else "party" if kind == "party_misfire" else "ooa")
        counters[family] = counters.get(family, 0) + 1
        rid = f"hw-{family}-{counters[family]:02d}"
        if item["expect"]:
            pid = prefix_to_id.get(item["expect"])
            assert pid, f"{rid}: judgment {item['expect']} is not in the corpus"
            relevant, extra = {pid: 2}, {}
        else:
            domain = kind.split(":")[1].strip() if kind.startswith("out_of_archive") else "near"
            relevant = {}
            # Every hand-written out-of-archive situation is Pakistani law
            # (even the "far" bail/cheque/tax ones): at 3,000 judgments a real
            # match may exist, so each is a candidate positive, not a failure.
            extra = {"verify_at_scale": True, "domain": domain,
                     "topic": kind.split(":")[-1].strip() if ":" in kind else kind}
        row = {
            "id": rid,
            "query": item["query"],
            "relevant": relevant,
            "query_type": "paraphrase",
            "origin": "hand_written",
            "status": "confirmed",
            "notes": f"narrative_baseline_v0 row ({kind}); hand-written",
            "perspective": perspective,
            "detail": "detailed" if kind in ("detailed", "party_misfire") or kind.startswith("out_of_archive")
                      else "loose",
            "baseline_kind": kind,
            "baseline_shown": [s["judgment_id"] for s in item["shown"]],
            "baseline_confidence": item["shown"][0]["confidence"] if item["shown"] else None,
            "baseline_pinned_any": item["pinned_any"],
            "words": len(item["query"].split()),
            **extra,
        }
        row["split"] = E.split_for_row(row)
        rows.append(row)
    return rows


def negative_rows() -> list[dict]:
    """eval/narrative_negatives.json as dataset rows (origin narrative_negative)."""
    payload = json.loads(NARRATIVE_NEGATIVES_PATH.read_text(encoding="utf-8"))
    rows = []
    for item in payload["negatives"]:
        row = {
            "id": item["id"],
            "query": item["query"],
            "relevant": {},
            "query_type": "paraphrase",
            "origin": "narrative_negative",
            "status": "confirmed",
            "notes": f"hand-written {item['domain']}-domain out-of-archive description ({item['topic']})",
            "perspective": item["perspective"],
            "detail": item["detail"],
            "domain": item["domain"],
            "topic": item["topic"],
            "verify_at_scale": bool(item["verify_at_scale"]),
            "words": len(item["query"].split()),
        }
        row["split"] = E.split_for_row(row)
        rows.append(row)
    return rows


# ── LLM text, whatever _complete returns ────────────────────────────────────

_RATE_LIMIT = re.compile(r"\b429\b|resource[_ ]exhausted|rate[_ -]?limit|quota", re.I)


def llm_text(result) -> tuple[str, bool]:
    """(text, rate_limited) from _complete's result: a str today, maybe a structured result tomorrow."""
    text, status = "", ""
    if isinstance(result, str):
        text = result
    elif isinstance(result, dict):
        text = next((result[k] for k in ("text", "content", "answer") if isinstance(result.get(k), str)), "")
        status = str(result.get("status") or result.get("answer_status") or "")
    elif result is not None:
        text = next((getattr(result, k) for k in ("text", "content", "answer")
                     if isinstance(getattr(result, k, None), str)), "")
        status = str(getattr(result, "status", "") or getattr(result, "answer_status", "") or "")
    try:
        from app.retrieval.llm_responder import ERROR_RESPONSE
    except Exception:
        ERROR_RESPONSE = "Error: Could not generate answer."
    limited = "rate" in status.lower() or bool(_RATE_LIMIT.search(status))
    if text.strip() == ERROR_RESPONSE or status.lower() in ("error", "rate_limited"):
        return "", limited
    return text, limited


# ── LLM guard for measurement runs ──────────────────────────────────────────

class LLMGuard:
    """Counts _complete calls; past `budget`, returns the error sentinel instead."""

    def __init__(self, budget: int):
        self.budget = budget
        self.calls = 0
        self.blocked = 0


def guard_llm(budget: int) -> LLMGuard:
    """Wrap llm_responder._complete everywhere it has been imported (this process only)."""
    import app.retrieval.llm_responder as llm

    guard = LLMGuard(budget)
    original = llm._complete
    sentinel = getattr(llm, "ERROR_RESPONSE", "Error: Could not generate answer. Please try again.")

    async def counted(*args, **kwargs):
        if guard.calls >= guard.budget:
            guard.blocked += 1
            return sentinel
        guard.calls += 1
        return await original(*args, **kwargs)

    # Only the app's own modules: getattr on third-party lazy modules (transformers) has side effects.
    for name, module in list(sys.modules.items()):
        if not (name == "app" or name.startswith("app.")):
            continue
        try:
            if getattr(module, "_complete", None) is original:
                setattr(module, "_complete", counted)
        except Exception:
            pass
    return guard


# ── Running one description ─────────────────────────────────────────────────

async def run_narrative(query: str, top_k: int = 10) -> dict:
    """retrieve_v2 on one description: shown list + labels, pre-gate window, pinning, latency."""
    from app.retrieval import pipeline_v2

    started = time.perf_counter()
    out = await pipeline_v2.retrieve_v2(query, top_k_judgments=top_k, top_k_sections=1)
    elapsed = (time.perf_counter() - started) * 1000
    debug_rows = pipeline_v2.last_debug.get("rows") or []
    shown = out.get("parent_results") or []
    top_debug = next((r for r in debug_rows if shown and r["judgment_id"] == shown[0]["judgment_id"]), {})
    return {
        "shown": [p["judgment_id"] for p in shown],
        "confidence": [p.get("confidence") for p in shown],
        "scores": [round(float(p.get("score") or 0.0), 4) for p in shown],
        "window": [r["judgment_id"] for r in debug_rows],
        "window_relevance": [round(float(r.get("relevance") or 0.0), 4) for r in debug_rows],
        "pinned_any": any(r.get("pinned") for r in debug_rows),
        "top_pinned": bool(top_debug.get("pinned")),
        "top_n_first": top_debug.get("n_first"),
        "top_n_lists": top_debug.get("n_lists"),
        "no_results": bool(out.get("no_results")),
        "message": out.get("message"),
        "reranked": bool(out.get("reranked")),
        "judge_used": bool(out.get("judge_used")),
        "is_narrative": (out.get("analysis") or {}).get("is_narrative"),
        "latency_ms": elapsed,
    }


def _self_check() -> None:
    assert llm_text("hello") == ("hello", False)
    assert llm_text({"text": "x", "status": "ready"}) == ("x", False)
    assert llm_text({"text": "", "status": "rate_limited"}) == ("", True)

    class R:
        text = "t"
        status = "ready"
    assert llm_text(R()) == ("t", False)
    rows = hand_written_rows({p: p + "-full" for p in
                              ("3eff8217", "5a06e4ef", "d40e2887", "4083a42e", "fa86ba1f", "adaeb488",
                               "3628e429", "49c42cc9", "2df8aea1")})
    kinds = [r["id"].split("-")[1] for r in rows]
    assert kinds.count("detailed") == 11 and kinds.count("loose") == 5, kinds
    assert kinds.count("ooa") == 7 and kinds.count("party") == 2, kinds
    for r in rows:
        validate_narrative_row(r)
        assert r["split"] == E.split_for_row(r)
    assert sum(1 for r in rows if r["relevant"]) == 16
    negs = negative_rows()
    assert len(negs) >= 40, len(negs)
    assert len({r["id"] for r in negs}) == len(negs)
    for r in negs:
        validate_narrative_row(r)
        assert 35 <= r["words"] <= 150, (r["id"], r["words"])
    assert all(r["verify_at_scale"] for r in negs if r["domain"] == "near")
    assert not any(r["verify_at_scale"] for r in negs if r["domain"] == "far")
    print("narrative_lib self-check passed")


if __name__ == "__main__":
    _self_check()
