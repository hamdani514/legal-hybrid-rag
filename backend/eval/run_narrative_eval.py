"""
Narrative (case-description) evaluation: can a user who DESCRIBES their case find the judgment?

    python eval/run_narrative_eval.py                         # narrative_dev (default)
    python eval/run_narrative_eval.py --save eval/results/runs/narrative_dev_current.json
    python eval/run_narrative_eval.py --hand-written-baseline # reproduce narrative_baseline_v0 row by row
    python eval/run_narrative_eval.py --split test            # ONLY at the 3,000 milestone, after --freeze
    python eval/run_narrative_eval.py --dataset path.jsonl --limit 10
    python eval/run_narrative_eval.py --override NARRATIVE_FACETS=false   # any pipeline_v2.opt() key, this run only
    python eval/run_narrative_eval.py --self-check

Why not run_eval.py
-------------------
run_eval.py scores short queries through orchestrator.retrieve_and_answer and
counts "correct" as rank 1 in a 50-deep list. A narrative user sees something
else: the SHOWN list after abstention, each result labelled "Strong match"
(confidence "high") or "Possible match — verify" ("medium"), and the plan's
targets are stated in those terms. This runner calls
pipeline_v2.retrieve_v2 directly (no query log, no answer generation) and
reads parent_results[i]["confidence"]. run_eval.py --dataset
eval/datasets/narrative_dev.jsonl still loads the file, if the old metrics
are wanted.

Metrics
-------
* **Case findability** — the plan's headline: share of judgments shown FIRST
  by >= 2 of their descriptions; also >= 1, all, and a majority. Reported for
  the generated descriptions alone (up to 4 per judgment: appellant's lawyer,
  opposing party, two loose layperson tellings) and for all origins.
* **p@1 / recall@5 over descriptions**, split by perspective, detail and
  origin. "shown" = what the user sees (abstention counts as a miss);
  "window" = the ranked list before the abstention gate
  (pipeline_v2.last_debug), so a retrieval miss and a gate refusal can be
  told apart.
* **Out of archive** — leaks (a judgment shown), leaks labelled "high" (the
  free-tier target is 0), refusal rate. A leak by a near-domain row marked
  verify_at_scale is a CANDIDATE POSITIVE (at 1,000/3,000 judgments a real
  match may exist): it is listed for human review in
  eval/labels/narrative_negative_candidates.json and counted apart from the
  far-domain failures — never silently as either.
* **Confidence labels** of the top shown result, for correct vs wrong tops,
  and for leaks. The owner's policy: without the LLM judge a narrative's top
  result should be at most "medium"; this table shows whether it is.
* **Latency** p50/p95 of retrieve_v2 (no answer generation); target p95 <= 4 s.
* **Party pinning** on the two party-misfire rows (hand-written).

What the numbers can and cannot tell you
----------------------------------------
On 11 judgments, n is tiny: 7 dev judgments, ~40 dev descriptions. Wilson
intervals are printed beside the headline proportions. The numbers are a
regression baseline for the round-2 changes, not an estimate of quality at
3,000 judgments — that is the frozen narrative_test, run once.

LLM calls: retrieval must not need Gemini on the default config. Every
_complete call made during the run is counted and, past --llm-budget
(default 0), fails the way an unavailable LLM fails; the count is reported.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import statistics
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import evallib as E
import narrative_lib as N
from run_eval import percentile, wilson_interval

CONFIG_PREFIXES = ("USE_", "V2_", "NARRATIVE", "JUDGE_", "QUERY_ANALYZER_USE_LLM", "RERANK")
LABELS = ("high", "medium", "related", None)


# ── Scoring ─────────────────────────────────────────────────────────────────

def score_row(item: dict, run: dict) -> dict:
    expect = E.primary_judgment(item["relevant"]) if item["relevant"] else None
    shown, window = run["shown"], run["window"]
    relevant = set(item["relevant"])
    row = {
        "id": item["id"],
        "query": item["query"],
        "origin": item["origin"],
        "perspective": item.get("perspective"),
        "detail": item.get("detail"),
        "split": item["split"],
        "positive": bool(item["relevant"]),
        "expect": expect,
        "shown": shown[:5],
        "confidence": run["confidence"][:5],
        "scores": run["scores"][:5],
        "top_label": run["confidence"][0] if shown else None,
        "window_top": window[:5],
        "abstained": not shown,
        "pinned_any": run["pinned_any"],
        "top_pinned": run["top_pinned"],
        "top_n_first": run["top_n_first"],
        "top_n_lists": run["top_n_lists"],
        "is_narrative": run.get("is_narrative"),
        "message": run.get("message"),
        "latency_ms": round(run["latency_ms"], 1),
    }
    if row["positive"]:
        row["rank_shown"] = next((i + 1 for i, p in enumerate(shown) if p in relevant), 0)
        row["rank_window"] = next((i + 1 for i, p in enumerate(window) if p in relevant), 0)
        row["hit1"] = row["rank_shown"] == 1
        row["hit1_window"] = row["rank_window"] == 1
        row["r5_shown"] = 1 <= row["rank_shown"] <= 5
        row["r5_window"] = 1 <= row["rank_window"] <= 5
    else:
        row["domain"] = item.get("domain")
        row["topic"] = item.get("topic")
        row["verify_at_scale"] = bool(item.get("verify_at_scale"))
        row["leaked"] = bool(shown)
        row["leak_high"] = bool(shown) and run["confidence"][0] == "high"
        row["candidate"] = row["leaked"] and row["verify_at_scale"]
        row["failure"] = row["leaked"] and not row["verify_at_scale"]
    return row


def _share(k: int, n: int) -> dict:
    lo, hi = wilson_interval(k, n)
    return {"k": k, "n": n, "value": (k / n) if n else None, "ci95": [round(lo, 3), round(hi, 3)]}


def findability(pos: list[dict]) -> dict:
    by_j: dict[str, list[dict]] = defaultdict(list)
    for r in pos:
        by_j[r["expect"]].append(r)
    per = {}
    for jid, rows in sorted(by_j.items()):
        found = sum(1 for r in rows if r["hit1"])
        per[jid] = {"descriptions": len(rows), "found_first": found,
                    "missed": [r["id"] for r in rows if not r["hit1"]]}
    n = len(per)
    return {
        "judgments": n,
        "at_least_1": _share(sum(1 for v in per.values() if v["found_first"] >= 1), n),
        "at_least_2": _share(sum(1 for v in per.values() if v["found_first"] >= 2), n),
        "majority": _share(sum(1 for v in per.values() if v["found_first"] * 2 > v["descriptions"]), n),
        "all": _share(sum(1 for v in per.values() if v["found_first"] == v["descriptions"]), n),
        "judgments_with_fewer_than_2_descriptions": [j for j, v in per.items() if v["descriptions"] < 2],
        "per_judgment": per,
    }


def group_metrics(rows: list[dict], key: str) -> dict:
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        groups[str(r[key])].append(r)
    out = {}
    for name, members in sorted(groups.items()):
        pos = [r for r in members if r["positive"]]
        neg = [r for r in members if not r["positive"]]
        out[name] = {
            "n_pos": len(pos), "n_neg": len(neg),
            "p_at_1": (sum(r["hit1"] for r in pos) / len(pos)) if pos else None,
            "recall_at_5": (sum(r["r5_shown"] for r in pos) / len(pos)) if pos else None,
            "recall_at_5_window": (sum(r["r5_window"] for r in pos) / len(pos)) if pos else None,
            "refused_pos": (sum(r["abstained"] for r in pos) / len(pos)) if pos else None,
            "leaks": sum(r["leaked"] for r in neg) if neg else None,
            "leaks_high": sum(r["leak_high"] for r in neg) if neg else None,
        }
    return out


def aggregate(rows: list[dict]) -> dict:
    pos = [r for r in rows if r["positive"]]
    neg = [r for r in rows if not r["positive"]]
    synth = [r for r in pos if r["origin"] == "synthetic_narrative"]
    lat = sorted(r["latency_ms"] for r in rows)
    correct = [r for r in pos if r["hit1"]]
    wrong_top = [r for r in pos if r["shown"] and not r["hit1"]]
    leaked = [r for r in neg if r["leaked"]]
    return {
        "n_rows": len(rows), "n_positive": len(pos), "n_negative": len(neg),
        "findability_synthetic": findability(synth) if synth else None,
        "findability_all": findability(pos) if pos else None,
        "p_at_1": _share(sum(r["hit1"] for r in pos), len(pos)),
        "p_at_1_window": _share(sum(r["hit1_window"] for r in pos), len(pos)),
        "recall_at_5": _share(sum(r["r5_shown"] for r in pos), len(pos)),
        "recall_at_5_window": _share(sum(r["r5_window"] for r in pos), len(pos)),
        "mrr_window": (sum(1 / r["rank_window"] for r in pos if r["rank_window"]) / len(pos)) if pos else None,
        "false_refusal": _share(sum(r["abstained"] for r in pos), len(pos)),
        "wrong_top_shown": _share(len(wrong_top), len(pos)),
        "by_perspective": group_metrics(rows, "perspective"),
        "by_detail": group_metrics(rows, "detail"),
        "by_origin": group_metrics(rows, "origin"),
        "out_of_archive": {
            "n": len(neg),
            "leaks": _share(len(leaked), len(neg)),
            "leaks_high": sum(r["leak_high"] for r in neg),
            "refusal_rate": _share(sum(r["abstained"] for r in neg), len(neg)),
            "far_domain_failures": [r["id"] for r in neg if r["failure"]],
            "near_domain_candidates": [r["id"] for r in neg if r["candidate"]],
            "by_domain": {d: {"n": sum(1 for r in neg if r["domain"] == d),
                              "leaks": sum(1 for r in neg if r["domain"] == d and r["leaked"]),
                              "leaks_high": sum(1 for r in neg if r["domain"] == d and r["leak_high"])}
                          for d in sorted({str(r["domain"]) for r in neg})},
        },
        "confidence_labels": {
            "correct_top": dict(Counter(str(r["top_label"]) for r in correct)),
            "wrong_top": dict(Counter(str(r["top_label"]) for r in wrong_top)),
            "leaked_top": dict(Counter(str(r["top_label"]) for r in leaked)),
        },
        "party_pinning": {"rows": [r["id"] for r in rows if r["id"].startswith("hw-party")],
                          "pinned": [r["id"] for r in rows if r["id"].startswith("hw-party") and r["pinned_any"]]},
        "latency_ms": {"p50": statistics.median(lat) if lat else 0.0, "p95": percentile(lat, 0.95),
                       "max": lat[-1] if lat else 0.0},
    }


# ── Reporting ───────────────────────────────────────────────────────────────

def _f(x, d: int = 3) -> str:
    return "-" if x is None else f"{x:.{d}f}"


def _s(share: dict) -> str:
    if not share or not share["n"]:
        return "-"
    return f"{share['value']:.3f}  ({share['k']}/{share['n']}, 95% CI [{share['ci95'][0]:.2f}, {share['ci95'][1]:.2f}])"


def report(agg: dict, rows: list[dict]) -> None:
    print(f"\n  rows {agg['n_rows']}  ({agg['n_positive']} descriptions of archived judgments, "
          f"{agg['n_negative']} out of archive)")
    for name, key in (("generated only", "findability_synthetic"), ("all origins", "findability_all")):
        f = agg[key]
        if not f:
            continue
        print(f"\n  case findability ({name}, {f['judgments']} judgments) — shown first by:")
        print(f"    >= 2 descriptions   {_s(f['at_least_2'])}   <- plan target >= 0.90 at 3,000")
        print(f"    >= 1 description    {_s(f['at_least_1'])}")
        print(f"    a majority          {_s(f['majority'])}")
        print(f"    all descriptions    {_s(f['all'])}")
        if f["judgments_with_fewer_than_2_descriptions"]:
            print(f"    (fewer than 2 descriptions: {[j[:8] for j in f['judgments_with_fewer_than_2_descriptions']]})")
    print(f"\n  p@1 shown            {_s(agg['p_at_1'])}   <- target >= 0.85")
    print(f"  p@1 before the gate  {_s(agg['p_at_1_window'])}")
    print(f"  recall@5 shown       {_s(agg['recall_at_5'])}   <- target >= 0.95")
    print(f"  recall@5 before gate {_s(agg['recall_at_5_window'])}")
    print(f"  MRR before the gate  {_f(agg['mrr_window'])}")
    print(f"  false refusals       {_s(agg['false_refusal'])}")
    print(f"  wrong judgment first {_s(agg['wrong_top_shown'])}")

    for title, key in (("perspective", "by_perspective"), ("detail", "by_detail"), ("origin", "by_origin")):
        print(f"\n  {title:<22}{'pos':>5}{'p@1':>7}{'r@5':>7}{'r@5win':>8}{'refuse':>8}{'neg':>5}{'leaks':>7}{'high':>6}")
        for name, m in agg[key].items():
            print(f"  {name:<22}{m['n_pos']:>5}{_f(m['p_at_1'], 2):>7}{_f(m['recall_at_5'], 2):>7}"
                  f"{_f(m['recall_at_5_window'], 2):>8}{_f(m['refused_pos'], 2):>8}{m['n_neg']:>5}"
                  f"{'-' if m['leaks'] is None else m['leaks']:>7}{'-' if m['leaks_high'] is None else m['leaks_high']:>6}")

    o = agg["out_of_archive"]
    if o["n"]:
        print(f"\n  out of archive ({o['n']}): leaks {_s(o['leaks'])}")
        print(f"    shown as 'high' (Strong match): {o['leaks_high']}   <- must be 0 on the free tier")
        print(f"    refusal rate {_s(o['refusal_rate'])}")
        print(f"    by domain: {o['by_domain']}")
        if o["far_domain_failures"]:
            print(f"    far-domain FAILURES: {o['far_domain_failures']}")
        if o["near_domain_candidates"]:
            print(f"    near-domain leaks = CANDIDATE positives for review ({len(o['near_domain_candidates'])}):")
            for r in rows:
                if not r["positive"] and r["candidate"]:
                    print(f"      {r['id']:<18} -> {r['shown'][0][:8]} [{r['top_label']}] {r['query'][:60]}")
    c = agg["confidence_labels"]
    print(f"\n  top-label distribution: correct tops {c['correct_top']} | wrong tops {c['wrong_top']} "
          f"| leaks {c['leaked_top']}")
    pp = agg["party_pinning"]
    if pp["rows"]:
        print(f"  party-misfire rows pinned: {len(pp['pinned'])}/{len(pp['rows'])} {pp['pinned']}")
    lat = agg["latency_ms"]
    print(f"  latency (retrieve_v2) p50 {lat['p50']:.0f}ms  p95 {lat['p95']:.0f}ms  max {lat['max']:.0f}ms"
          f"   <- target p95 <= 4000ms")

    missed = [r for r in rows if r["positive"] and not r["hit1"]]
    if missed:
        print(f"\n  descriptions NOT shown first ({len(missed)}):")
        for r in missed:
            where = ("refused" + (f", window rank {r['rank_window']}" if r["rank_window"] else ", not in window")
                     if r["abstained"] else f"shown {r['shown'][0][:8]} [{r['top_label']}], window rank {r['rank_window']}")
            print(f"    {r['id']:<36} {r['expect'][:8]}  {where}")


def hand_written_summary(rows: list[dict]) -> dict:
    """The narrative_baseline_v0 summary computed the same way, on this run."""
    def ids(prefix):
        return [r for r in rows if r["id"].startswith(prefix)]
    det, loose, ooa, party = ids("hw-detailed"), ids("hw-loose"), ids("hw-ooa"), ids("hw-party")
    return {
        "detailed_right_first": f"{sum(r['hit1'] for r in det)}/{len(det)}",
        "loose_right_first": f"{sum(r['hit1'] for r in loose)}/{len(loose)}",
        "out_of_archive_leaked": f"{sum(r['leaked'] for r in ooa)}/{len(ooa)}",
        "out_of_archive_shown_high": sum(r["leak_high"] for r in ooa),
        "party_misfire_pinned": f"{sum(r['pinned_any'] for r in party)}/{len(party)}",
    }


def compare_to_baseline(rows: list[dict], items: dict[str, dict]) -> list[dict]:
    """Rows whose shown-top or label changed since narrative_baseline_v0."""
    changes = []
    for r in rows:
        item = items[r["id"]]
        before_top = (item.get("baseline_shown") or [None])[0]
        now_top = r["shown"][0] if r["shown"] else None
        if before_top != now_top or item.get("baseline_confidence") != r["top_label"] \
                or item.get("baseline_pinned_any") != r["pinned_any"]:
            changes.append({"id": r["id"], "before": [before_top and before_top[:8], item.get("baseline_confidence"),
                                                      item.get("baseline_pinned_any")],
                            "now": [now_top and now_top[:8], r["top_label"], r["pinned_any"]],
                            "query": r["query"][:70]})
    return changes


def record_candidates(rows: list[dict], run_label: str, overrides: dict) -> int:
    cands = [r for r in rows if not r["positive"] and r["candidate"]]
    if not cands:
        return 0
    existing = {}
    if N.NARRATIVE_CANDIDATES_PATH.exists():
        existing = {c["id"]: c for c in json.loads(N.NARRATIVE_CANDIDATES_PATH.read_text(encoding="utf-8"))["candidates"]}
    for r in cands:
        existing[r["id"]] = {"id": r["id"], "query": r["query"], "topic": r.get("topic"), "shown": r["shown"],
                             "confidence": r["confidence"], "seen_at": datetime.now().isoformat(timespec="seconds"),
                             "run": run_label, "overrides": overrides,
                             "action": "review: if the shown judgment decides this situation, relabel as a positive; "
                                       "otherwise keep it negative (a true leak)"}
    N.NARRATIVE_CANDIDATES_PATH.parent.mkdir(parents=True, exist_ok=True)
    N.NARRATIVE_CANDIDATES_PATH.write_text(
        json.dumps({"candidates": sorted(existing.values(), key=lambda c: c["id"])}, indent=2, ensure_ascii=False),
        encoding="utf-8")
    return len(cands)


def config_snapshot() -> dict:
    from app.config import settings
    from app.retrieval import pipeline_v2

    keys = sorted(k for k in type(settings).model_fields if k.startswith(CONFIG_PREFIXES))
    snap = {k: getattr(settings, k) for k in keys}
    snap.update({f"OVERRIDE:{k}": v for k, v in pipeline_v2.OVERRIDES.items()})
    return snap


# Files whose content decides what a narrative user sees. Other agents edit
# them concurrently, so every saved run records exactly which state it measured.
CODE_FILES = ("app/config.py", "app/retrieval/pipeline_v2.py", "app/retrieval/query_analyzer.py",
              "app/retrieval/exact_match.py", "app/retrieval/lexical.py", "app/retrieval/fusion.py",
              "app/retrieval/dense_cards.py", "app/retrieval/dense_chunks.py", "app/retrieval/reranker.py",
              "app/retrieval/categories.py", "app/retrieval/judge.py", "app/retrieval/contracts.py")


def code_state() -> dict:
    out = {}
    for rel in CODE_FILES:
        path = E.BACKEND_DIR / rel
        if path.exists():
            out[rel] = {"sha256": E.sha256_file(path)[:12],
                        "mtime": datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds")}
    return out


# ── Main ────────────────────────────────────────────────────────────────────

def load_items(args) -> tuple[list[dict], str, str]:
    import build_narrative_datasets as B

    if args.hand_written_baseline:
        return [], "narrative_baseline_v0.json (hand-written rows)", E.sha256_file(N.NARRATIVE_BASELINE_V0)
    paths = [args.dataset] if args.dataset else {
        "dev": [N.NARRATIVE_DEV_PATH], "test": [N.NARRATIVE_TEST_PATH],
        "all": [N.NARRATIVE_DEV_PATH, N.NARRATIVE_TEST_PATH]}[args.split]
    touches_test = any(p.resolve() == N.NARRATIVE_TEST_PATH.resolve() for p in paths)
    if touches_test:
        frozen, message = B.check_frozen()
        print(message)
        if frozen is False and not args.allow_test_changes:
            raise SystemExit("REFUSED: narrative_test.jsonl changed since it was frozen (--allow-test-changes).")
        print("WARNING: this run includes the narrative TEST split. Do not tune anything on these numbers.\n")
    rows, digest = [], hashlib.sha256()
    for path in paths:
        if not path.exists():
            raise SystemExit(f"{path} not found — run eval/build_narrative_datasets.py first")
        digest.update(path.read_bytes())
        rows.extend(E.read_jsonl(path))
    for row in rows:
        N.validate_narrative_row(row)
    desc = " + ".join(str(p.relative_to(E.BACKEND_DIR)) if p.is_relative_to(E.BACKEND_DIR) else str(p) for p in paths)
    return rows, desc, digest.hexdigest()


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--split", choices=("dev", "test", "all"), default="dev")
    parser.add_argument("--dataset", type=Path, help="Evaluate this narrative .jsonl instead of a split.")
    parser.add_argument("--hand-written-baseline", action="store_true",
                        help="Run the 25 hand-written rows of narrative_baseline_v0.json and diff against it.")
    parser.add_argument("--allow-test-changes", action="store_true")
    parser.add_argument("--top-k", type=int, default=10, help="top_k_judgments passed to retrieve_v2.")
    parser.add_argument("--limit", type=int, help="Only the first N rows (smoke test).")
    parser.add_argument("--llm-budget", type=int, default=0,
                        help="Gemini calls the pipeline may make during the run (beyond it they fail as unavailable).")
    parser.add_argument("--override", action="append", default=[], metavar="KEY=VALUE",
                        help="pipeline_v2.OVERRIDES entry for this run (JSON value, else string); repeatable. "
                             "E.g. --override NARRATIVE_FACETS=false --override NARRATIVE_MAX_CONFIDENCE=high")
    parser.add_argument("--save", type=Path, help="Write the results JSON here.")
    parser.add_argument("--label", help="Label stored in the --save file.")
    parser.add_argument("--verbose-log", action="store_true")
    args = parser.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    from loguru import logger
    if not args.verbose_log:
        logger.remove()
        logger.add(sys.stderr, level="ERROR")

    items, desc, sha = load_items(args)
    prefix = await N.full_ids()
    if args.hand_written_baseline:
        items = N.hand_written_rows(prefix)
    if args.limit:
        items = items[: args.limit]

    # retrieve_v2 writes no query log, and orchestrator (which does) is never imported here.
    # Import the LLM-using modules BEFORE guarding, so a name they bound at import is patched too.
    from app.retrieval import pipeline_v2  # noqa: F401
    for name in ("judge", "query_analyzer", "comparator"):
        try:
            __import__(f"app.retrieval.{name}")
        except Exception as e:
            print(f"note: app.retrieval.{name} did not import ({e}); continuing")
    guard = N.guard_llm(args.llm_budget)
    for spec in args.override:
        key, _, value = spec.partition("=")
        try:
            pipeline_v2.OVERRIDES[key.strip()] = json.loads(value)
        except json.JSONDecodeError:
            pipeline_v2.OVERRIDES[key.strip()] = value

    unreachable = [r["id"] for r in items if r["relevant"] and E.primary_judgment(r["relevant"]) not in prefix.values()]
    config = config_snapshot()
    state_before = code_state()
    print(f"corpus   : {len(prefix)} judgments")
    print(f"dataset  : {desc} ({len(items)} rows, sha256 {sha[:16]})")
    print(f"config   : " + ", ".join(f"{k}={v}" for k, v in config.items() if k.startswith(("USE_", "V2_CONF", "V2_AGR",
                                                                                           "V2_REL", "V2_FINAL", "NARR"))))
    if unreachable:
        print(f"WARNING  : {len(unreachable)} rows expect a judgment not in the corpus: {unreachable[:5]}")

    await N.run_narrative("warm-up: a tenant was evicted by the landlord and the High Court dismissed his petition", 3)
    started = time.perf_counter()
    rows = []
    for i, item in enumerate(items, start=1):
        run = await N.run_narrative(item["query"], args.top_k)
        row = score_row(item, run)
        rows.append(row)
        if row["positive"]:
            mark = "OK  " if row["hit1"] else ("REF " if row["abstained"] else "WRNG")
        else:
            mark = "NEG+" if row["abstained"] else ("HIGH" if row["leak_high"] else "LEAK")
        print(f"  [{i:>3}/{len(items)}] {mark} {row['top_label'] or '-':<7} {row['latency_ms']:>6.0f}ms "
              f"{row['id'][:30]:<30} {item['query'][:44]}")

    agg = aggregate(rows)
    report(agg, rows)
    summary, changes = None, None
    if args.hand_written_baseline or any(r["id"].startswith("hw-") for r in rows):
        hw_rows = [r for r in rows if r["id"].startswith("hw-")]
        summary = hand_written_summary(hw_rows)
        baseline = json.loads(N.NARRATIVE_BASELINE_V0.read_text(encoding="utf-8"))["summary"]
        print(f"\n  hand-written rows in this run ({len(hw_rows)}): {summary}")
        if args.hand_written_baseline:
            print(f"  narrative_baseline_v0 summary         : {baseline}")
            changes = compare_to_baseline(hw_rows, {it["id"]: it for it in items})
            print(f"  rows whose top / label / pinning changed vs v0: {len(changes)}")
            for c in changes:
                print(f"    {c['id']:<14} before {c['before']} -> now {c['now']}  {c['query'][:50]}")
    from app.retrieval import pipeline_v2 as _p2
    n_cand = record_candidates(rows, args.label or "unlabelled run", dict(_p2.OVERRIDES))
    if n_cand:
        print(f"\n  {n_cand} candidate positive(s) recorded in {N.NARRATIVE_CANDIDATES_PATH.relative_to(E.BACKEND_DIR)}")
    print(f"\n  LLM calls during the run: {guard.calls} made, {guard.blocked} blocked (budget {args.llm_budget})")
    print(f"  wall time {time.perf_counter() - started:.0f}s")
    if state_before != code_state():
        print("  WARNING: retrieval code changed on disk during this run (another agent's edit); "
              "the process measured the version imported at start.")

    if args.save:
        payload = {
            "label": args.label or f"narrative run {datetime.now().isoformat(timespec='seconds')}",
            "run_at": datetime.now().isoformat(timespec="seconds"),
            "corpus_judgments": len(prefix),
            "dataset": desc, "dataset_sha256": sha[:16],
            "entry_point": "app.retrieval.pipeline_v2.retrieve_v2", "top_k": args.top_k,
            "config": config,
            "code_state": state_before,
            "code_changed_during_run": state_before != code_state(),
            "llm_calls": {"made": guard.calls, "blocked": guard.blocked, "budget": args.llm_budget},
            "metrics": agg,
            "hand_written_summary": summary,
            "changes_vs_narrative_baseline_v0": changes,
            "rows": rows,
        }
        frozen = {p.resolve() for p in (E.RESULTS_DIR / "baseline_v1.json", N.NARRATIVE_BASELINE_V0)}
        assert args.save.resolve() not in frozen, "refusing to overwrite a frozen baseline"
        args.save.parent.mkdir(parents=True, exist_ok=True)
        args.save.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        print(f"  saved {args.save}")
    return 0


def _self_check() -> None:
    item = {"id": "nar-a-layperson", "query": "q", "relevant": {"A": 2}, "origin": "synthetic_narrative",
            "perspective": "layperson", "detail": "loose", "split": "dev"}

    def run(shown, conf, window, pinned=False):
        return {"shown": shown, "confidence": conf, "scores": [0.5] * len(shown), "window": window,
                "pinned_any": pinned, "top_pinned": pinned, "top_n_first": 3, "top_n_lists": 4,
                "latency_ms": 100.0}
    r1 = score_row(item, run(["A"], ["medium"], ["A", "B"]))
    r2 = score_row({**item, "id": "nar-a-x"}, run([], [], ["B", "A"]))
    r3 = score_row({**item, "id": "nar-b-y", "relevant": {"B": 2}}, run(["A"], ["high"], ["A", "B"]))
    assert r1["hit1"] and r1["rank_window"] == 1 and not r2["hit1"] and r2["abstained"] and r2["r5_window"]
    assert not r3["hit1"] and r3["rank_window"] == 2
    neg_near = score_row({**item, "id": "n1", "relevant": {}, "verify_at_scale": True, "domain": "near"},
                         run(["A"], ["high"], ["A"]))
    neg_far = score_row({**item, "id": "n2", "relevant": {}, "verify_at_scale": False, "domain": "far"},
                        run([], [], ["A"]))
    assert neg_near["candidate"] and neg_near["leak_high"] and not neg_near["failure"]
    assert neg_far["abstained"] and not neg_far["leaked"]
    agg = aggregate([r1, r2, r3, neg_near, neg_far])
    f = agg["findability_synthetic"]
    assert f["judgments"] == 2 and f["at_least_1"]["k"] == 1 and f["at_least_2"]["k"] == 0, f
    assert f["per_judgment"]["A"] == {"descriptions": 2, "found_first": 1, "missed": ["nar-a-x"]}
    assert agg["p_at_1"]["k"] == 1 and agg["p_at_1_window"]["k"] == 1 and agg["recall_at_5_window"]["k"] == 3
    assert agg["out_of_archive"]["leaks_high"] == 1 and agg["out_of_archive"]["near_domain_candidates"] == ["n1"]
    assert agg["confidence_labels"]["correct_top"] == {"medium": 1}
    assert agg["confidence_labels"]["wrong_top"] == {"high": 1}
    assert agg["by_detail"]["loose"]["n_pos"] == 3
    hw = [score_row({**item, "id": "hw-detailed-01"}, run(["A"], ["high"], ["A"])),
          score_row({**item, "id": "hw-ooa-01", "relevant": {}, "verify_at_scale": True}, run(["A"], ["high"], ["A"])),
          score_row({**item, "id": "hw-party-01", "relevant": {}, "verify_at_scale": True},
                    run(["A"], ["high"], ["A"], pinned=True))]
    s = hand_written_summary(hw)
    assert s == {"detailed_right_first": "1/1", "loose_right_first": "0/0", "out_of_archive_leaked": "1/1",
                 "out_of_archive_shown_high": 1, "party_misfire_pinned": "1/1"}, s
    print("run_narrative_eval self-check passed")


if __name__ == "__main__":
    if "--self-check" in sys.argv:
        _self_check()
        raise SystemExit(0)
    raise SystemExit(asyncio.run(main()))
