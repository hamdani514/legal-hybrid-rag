"""
Retrieval evaluation harness.

Runs a labelled query set through the real pipeline and reports the numbers
that decide whether a change helped — and how sure we can be that it did.

    python eval/run_eval.py                          # dev split (default)
    python eval/run_eval.py --split all              # dev + test (test is hash-checked)
    python eval/run_eval.py --split test             # the reported number: run ONCE, at the end
    python eval/run_eval.py --dataset path.jsonl     # any dataset file
    python eval/run_eval.py --queries eval/queries.json   # the old 20-query file
    python eval/run_eval.py --ablate                 # one row per enabled stage, switched off
    python eval/run_eval.py --save eval/results/x.json    # comparable to baseline_v1.json
    python eval/run_eval.py --no-rerank              # bi-encoder only
    python eval/run_eval.py --collection legal_embeddings   # another index
    python eval/run_eval.py --compare                # with and without reranking
    python eval/run_eval.py --by-group               # break down by query type / legacy group

Metrics
-------
Positives (rows with relevant judgments; grade 2 = the answer, 1 = alternate):
precision@1 and @3 (a relevant judgment at rank 1 / in the top 3), recall@5,
@10, @50 (share of the relevant judgments retrieved), MRR, nDCG@10 on the
graded labels, and the false-refusal rate (the system abstained on a query it
can answer). Negatives (relevant {}): abstention recall (share correctly
refused) and abstention precision (share of all refusals that were right).
Latency p50/p95 over every query. Bootstrap 95% CIs for p@1 and recall@10.

Near-domain negatives marked verify_at_scale may become answerable once the
full corpus is ingested; one that retrieves a judgment is reported as a
candidate positive (eval/labels/negative_candidates.json), excluded from the
headline abstention recall, and counted in the strict figure printed beside it.

What these numbers can and cannot tell you
------------------------------------------
On ~100 queries a proportion near 0.85 carries a 95% interval of roughly +/-7
points; on the 20-query legacy set it was +/-17. The intervals are printed
next to every headline figure so they cannot be quietly ignored: a difference
inside them is not evidence.

The test split is frozen by hash (eval/datasets/test.sha256). Tuning against it
would make every reported number fiction, so --split test/all refuse to run if
test.jsonl has changed, unless --allow-test-changes.
"""

import argparse
import asyncio
import json
import math
import random
import statistics
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import evallib as E

QUERIES_PATH = E.LEGACY_PATH
BASELINE_PATH = E.RESULTS_DIR / "baseline_v1.json"
NEG_CANDIDATES_PATH = E.LABELS_DIR / "negative_candidates.json"
ABLATABLE = ("USE_QUERY_ANALYZER", "USE_EXACT_MATCH", "USE_BM25", "USE_CARDS",
             "USE_FUSION", "USE_LLM_JUDGE", "RERANK_ENABLED")
RECALL_KS = (5, 10, 50)


def wilson_interval(successes: int, total: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval — honest for small n, unlike the normal one."""
    if total == 0:
        return 0.0, 0.0
    p = successes / total
    denom = 1 + z**2 / total
    centre = (p + z**2 / (2 * total)) / denom
    margin = z * math.sqrt(p * (1 - p) / total + z**2 / (4 * total**2)) / denom
    return max(0.0, centre - margin), min(1.0, centre + margin)


def bootstrap_ci(values: list[float], resamples: int = 2000, seed: int = 13) -> tuple[float, float]:
    """95% percentile bootstrap of the mean, resampling queries. Seeded: reproducible."""
    if not values:
        return 0.0, 0.0
    rng = random.Random(seed)
    n = len(values)
    means = sorted(sum(values[rng.randrange(n)] for _ in range(n)) / n for _ in range(resamples))
    return means[int(0.025 * resamples)], means[min(resamples - 1, int(0.975 * resamples))]


def percentile(sorted_values: list[float], q: float) -> float:
    """Same nearest-rank rule as baseline_v1 used, so latencies stay comparable."""
    if not sorted_values:
        return 0.0
    return sorted_values[max(0, int(len(sorted_values) * q) - 1)]


def ndcg(ranked: list[str], relevant: dict[str, int], k: int = 10) -> float:
    dcg = sum((2 ** relevant.get(pid, 0) - 1) / math.log2(i + 2) for i, pid in enumerate(ranked[:k]))
    ideal = sorted(relevant.values(), reverse=True)[:k]
    idcg = sum((2 ** g - 1) / math.log2(i + 2) for i, g in enumerate(ideal))
    return dcg / idcg if idcg else 0.0


def score_row(item: dict, run: dict) -> dict:
    """Per-query metrics. 'rank' = 1-based rank of the first relevant judgment, 0 = none."""
    relevant = item["relevant"]
    ranked = run["ranked"]
    rank = next((i + 1 for i, pid in enumerate(ranked) if relevant.get(pid, 0) >= 1), 0)
    row = {
        "id": item["id"],
        "query": item["query"],
        "group": item.get("legacy_group") or item["query_type"],
        "query_type": item["query_type"],
        "origin": item["origin"],
        "split": item["split"],
        "positive": bool(relevant),
        "expect": E.primary_judgment(relevant),
        "rank": rank,
        "abstained": run["no_results"],
        "top": ranked[:5],
        "top_scores": [round(s, 4) for s in run["scores"][:5]],
        "latency_ms": run["latency_ms"],
        "reranked": run["reranked"],
    }
    if relevant:
        for k in RECALL_KS:
            row[f"recall_at_{k}"] = len(set(ranked[:k]) & set(relevant)) / len(relevant)
        row["ndcg_at_10"] = ndcg(ranked, relevant, 10)
    else:
        row["verify_at_scale"] = bool(item.get("verify_at_scale"))
    return row


async def evaluate(queries: list[dict], top_k: int = 50, label: str = "", corpus: set | None = None,
                   verbose: bool = True) -> dict:
    """Run every query and compute the aggregate metrics."""
    rows = []
    for index, item in enumerate(queries, start=1):
        run = await E.run_query(item["query"], top_k)
        row = score_row(item, run)
        rows.append(row)
        if verbose:
            if row["positive"]:
                mark = "OK  " if row["rank"] == 1 else ("ABST" if row["abstained"] else
                                                        (f"#{row['rank']:<3}" if row["rank"] else "MISS"))
            else:
                mark = "NEG+" if row["abstained"] else "NEG-"
            print(f"  [{index:>3}/{len(queries)}] {mark} {row['latency_ms']:>6.0f}ms  "
                  f"{row['origin'][:4]:<4} {item['query'][:58]}")
    return aggregate(rows, label, corpus)


def aggregate(rows: list[dict], label: str = "", corpus: set | None = None) -> dict:
    pos = [r for r in rows if r["positive"]]
    neg = [r for r in rows if not r["positive"]]
    n = len(pos)

    def mean(key: str, subset=pos) -> float:
        return sum(r[key] for r in subset) / len(subset) if subset else 0.0

    at1 = sum(1 for r in pos if r["rank"] == 1)
    hits1 = [1.0 if r["rank"] == 1 else 0.0 for r in pos]
    r10 = [r["recall_at_10"] for r in pos]
    latencies = sorted(r["latency_ms"] for r in rows)

    pending = [r for r in neg if not r["abstained"] and r.get("verify_at_scale")]
    neg_scored = [r for r in neg if r not in pending]
    abstained_all = [r for r in rows if r["abstained"]]

    result = {
        "label": label,
        "total": len(rows),
        "n_positive": n,
        "n_negative": len(neg),
        "p_at_1": at1 / n if n else 0.0,
        "p_at_1_n": at1,
        "p_at_3": sum(1 for r in pos if 1 <= r["rank"] <= 3) / n if n else 0.0,
        "recall_at_5": mean("recall_at_5"),
        "recall_at_10": mean("recall_at_10"),
        "recall_at_50": mean("recall_at_50"),
        "mrr": sum(1 / r["rank"] for r in pos if r["rank"]) / n if n else 0.0,
        "ndcg_at_10": mean("ndcg_at_10"),
        "false_refusal_rate": sum(1 for r in pos if r["abstained"]) / n if n else 0.0,
        "abstention_recall": (sum(1 for r in neg_scored if r["abstained"]) / len(neg_scored)) if neg_scored else None,
        "abstention_recall_strict": (sum(1 for r in neg if r["abstained"]) / len(neg)) if neg else None,
        "abstention_precision": (sum(1 for r in abstained_all if not r["positive"]) / len(abstained_all))
                                if abstained_all else None,
        "pending_negatives": [{"id": r["id"], "query": r["query"], "top": r["top"], "top_scores": r["top_scores"]}
                              for r in pending],
        "p50_ms": statistics.median(latencies) if latencies else 0.0,
        "p95_ms": percentile(latencies, 0.95),
        "p_at_1_ci95_bootstrap": bootstrap_ci(hits1),
        "recall_at_10_ci95_bootstrap": bootstrap_ci(r10),
        "p_at_1_ci95_wilson": wilson_interval(at1, n),
        "reranked": any(r["reranked"] for r in rows),
        "rows": rows,
    }
    if corpus is not None:
        unreachable = [r for r in pos if r["expect"] not in corpus]
        result["unreachable"] = [{"id": r["id"], "query": r["query"], "expect": r["expect"]} for r in unreachable]
        reachable = [r for r in pos if r["expect"] in corpus]
        result["p_at_1_reachable"] = (sum(1 for r in reachable if r["rank"] == 1) / len(reachable)) if reachable else 0.0
    return result


def _fmt(value, digits: int = 3) -> str:
    return "-" if value is None else f"{value:.{digits}f}"


def breakdown(rows: list[dict], key: str, title: str) -> None:
    groups: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        groups[row[key]].append(row)
    print(f"\n  {title:<14} {'n':>4} {'p@1':>6} {'r@10':>6} {'MRR':>6} {'nDCG':>6} {'abst':>6}")
    for name, members in sorted(groups.items()):
        pos = [r for r in members if r["positive"]]
        neg = [r for r in members if not r["positive"]]
        p1 = sum(1 for r in pos if r["rank"] == 1) / len(pos) if pos else None
        r10 = sum(r["recall_at_10"] for r in pos) / len(pos) if pos else None
        mrr = sum(1 / r["rank"] for r in pos if r["rank"]) / len(pos) if pos else None
        nd = sum(r["ndcg_at_10"] for r in pos) / len(pos) if pos else None
        ab = sum(1 for r in neg if r["abstained"]) / len(neg) if neg else None
        print(f"  {name:<14} {len(members):>4} {_fmt(p1, 2):>6} {_fmt(r10, 2):>6} {_fmt(mrr, 2):>6} "
              f"{_fmt(nd, 2):>6} {_fmt(ab, 2):>6}")


def report(result: dict, by_group: bool = False) -> None:
    """Print one evaluation's metrics."""
    lo, hi = result["p_at_1_ci95_bootstrap"]
    wlo, whi = result["p_at_1_ci95_wilson"]
    rlo, rhi = result["recall_at_10_ci95_bootstrap"]

    print(f"\n  {'queries':<22} {result['total']}  ({result['n_positive']} positive, {result['n_negative']} negative)")
    print(f"  {'reranked':<22} {result['reranked']}")
    print(f"  {'precision@1':<22} {result['p_at_1']:.3f}   95% CI bootstrap [{lo:.2f}, {hi:.2f}]"
          f"  wilson [{wlo:.2f}, {whi:.2f}]")
    print(f"  {'precision@3':<22} {result['p_at_3']:.3f}")
    print(f"  {'recall@5':<22} {result['recall_at_5']:.3f}")
    print(f"  {'recall@10':<22} {result['recall_at_10']:.3f}   95% CI bootstrap [{rlo:.2f}, {rhi:.2f}]")
    print(f"  {'recall@50':<22} {result['recall_at_50']:.3f}")
    print(f"  {'MRR':<22} {result['mrr']:.3f}")
    print(f"  {'nDCG@10':<22} {result['ndcg_at_10']:.3f}")
    print(f"  {'false-refusal rate':<22} {result['false_refusal_rate']:.3f}")
    pending = len(result["pending_negatives"])
    strict = _fmt(result["abstention_recall_strict"])
    print(f"  {'abstention recall':<22} {_fmt(result['abstention_recall'])}   "
          f"(strict, all negatives: {strict}; {pending} near-domain pending review)")
    print(f"  {'abstention precision':<22} {_fmt(result['abstention_precision'])}")
    print(f"  {'latency p50':<22} {result['p50_ms']:.0f}ms")
    print(f"  {'latency p95':<22} {result['p95_ms']:.0f}ms")

    if result.get("unreachable"):
        print(f"\n  {len(result['unreachable'])} positive(s) expect a judgment NOT in the corpus "
              f"(p@1 on the reachable rest: {result['p_at_1_reachable']:.3f}):")
        for row in result["unreachable"]:
            print(f"    {row['expect'][:8]}  {row['query'][:64]}")

    rows = result["rows"]
    breakdown(rows, "query_type", "by query type")
    breakdown(rows, "origin", "by origin")
    if by_group and any(r["group"] != r["query_type"] for r in rows):
        breakdown(rows, "group", "by group")

    missed = [r for r in rows if r["positive"] and r["rank"] != 1]
    if missed:
        print(f"\n  not ranked first ({len(missed)}):")
        for row in missed:
            where = "abstained" if row["abstained"] else (f"rank {row['rank']}" if row["rank"] else "not in top-k")
            print(f"    [{where}] {row['query'][:64]}")
    wrong_neg = [r for r in rows if not r["positive"] and not r["abstained"]]
    if wrong_neg:
        print(f"\n  negatives that retrieved a judgment ({len(wrong_neg)}):")
        for row in wrong_neg:
            tag = "pending review" if row.get("verify_at_scale") else "FAILURE"
            print(f"    [{tag}] {row['query'][:56]}  -> {row['top'][0][:8]} {row['top_scores'][0]:.2f}")


def legacy_check(result: dict) -> None:
    """The legacy subset against the frozen baseline_v1, query by query."""
    rows = [r for r in result["rows"] if r["origin"] == "legacy"]
    if not rows or not BASELINE_PATH.exists():
        return
    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    base_rank = {E.normalise_query(r["query"]): r["rank"] for r in baseline["per_query"]}
    at1 = sum(1 for r in rows if r["rank"] == 1)
    print(f"\n  legacy subset vs baseline_v1: p@1 {at1}/{len(rows)} = {at1 / len(rows):.3f} "
          f"(baseline {baseline['metrics']['p_at_1']:.3f} on n={baseline['n']})")
    changed = [(r, base_rank.get(E.normalise_query(r["query"]))) for r in rows]
    changed = [(r, b) for r, b in changed if b is not None and (r["rank"] == 1) != (b == 1)]
    for row, before in changed:
        print(f"    rank {before} -> {row['rank']}{' (abstained)' if row['abstained'] else ''}  {row['query'][:60]}")
    if len(rows) != baseline["n"]:
        print(f"    note: {len(rows)} legacy rows in this split vs {baseline['n']} in the baseline")


def save_results(path: Path, result: dict, args, settings, dataset_desc: str, dataset_sha: str,
                 corpus_n: int, ablation: list | None) -> None:
    payload = {
        "label": args.label or f"run {datetime.now().isoformat(timespec='seconds')}",
        "frozen_at": datetime.now().isoformat(timespec="seconds"),
        "corpus_judgments": corpus_n,
        "queries_file": dataset_desc,
        "queries_sha256": dataset_sha[:16],
        "split": args.split if not (args.dataset or args.queries) else None,
        "config": {key: getattr(settings, key, None) for key in (
            "CHROMA_COLLECTION", "EMBEDDING_MODEL", "RERANKER_MODEL", "RERANK_ENABLED", "RERANK_CANDIDATES",
            "RELEVANCE_THRESHOLD", "CHUNK_MAX_TOKENS") + ABLATABLE[:-1]},
        "top_k": args.top_k,
        "metrics": {key: result[key] for key in (
            "p_at_1", "p_at_3", "recall_at_5", "recall_at_10", "recall_at_50", "mrr", "ndcg_at_10",
            "false_refusal_rate", "abstention_recall", "abstention_recall_strict", "abstention_precision",
            "p50_ms", "p95_ms")},
        "p_at_1_ci95": [round(x, 3) for x in result["p_at_1_ci95_bootstrap"]],
        "p_at_1_ci95_wilson": [round(x, 3) for x in result["p_at_1_ci95_wilson"]],
        "recall_at_10_ci95": [round(x, 3) for x in result["recall_at_10_ci95_bootstrap"]],
        "n": result["n_positive"],
        "n_negative": result["n_negative"],
        "unreachable": result.get("unreachable", []),
        "pending_negatives": result["pending_negatives"],
        "ablation": ablation,
        "per_query": [{k: row.get(k) for k in ("id", "query", "group", "query_type", "origin", "split", "rank",
                                                "abstained", "top", "top_scores", "latency_ms")}
                      for row in result["rows"]],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    assert path.resolve() != BASELINE_PATH.resolve(), "refusing to overwrite the frozen baseline"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nsaved {path}")


def record_pending(result: dict) -> None:
    """Merge near-domain negatives that retrieved something into the review file."""
    if not result["pending_negatives"]:
        return
    existing = {}
    if NEG_CANDIDATES_PATH.exists():
        existing = {c["id"]: c for c in json.loads(NEG_CANDIDATES_PATH.read_text(encoding="utf-8"))["candidates"]}
    for item in result["pending_negatives"]:
        existing[item["id"]] = {**item, "seen_at": datetime.now().isoformat(timespec="seconds"),
                                "action": "review: relabel as positive, or set verify_at_scale false"}
    NEG_CANDIDATES_PATH.parent.mkdir(parents=True, exist_ok=True)
    NEG_CANDIDATES_PATH.write_text(json.dumps({"candidates": sorted(existing.values(), key=lambda c: c["id"])},
                                              indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n  {len(result['pending_negatives'])} candidate positive(s) recorded in {NEG_CANDIDATES_PATH}")


def load_rows(args) -> tuple[list[dict], str, str]:
    """(rows, description, sha256 of the source bytes)."""
    import hashlib

    if args.queries:
        paths = [args.queries]
    elif args.dataset:
        paths = [args.dataset]
    else:
        paths = {"dev": [E.DEV_PATH], "test": [E.TEST_PATH], "all": [E.DEV_PATH, E.TEST_PATH]}[args.split]
    rows, digest = [], hashlib.sha256()
    for path in paths:
        if not path.exists():
            raise SystemExit(f"{path} not found — run eval/build_datasets.py first")
        digest.update(path.read_bytes())
        rows.extend(E.load_dataset(path))
    if not args.include_proposed:
        rows = [r for r in rows if r["status"] == "confirmed"]
    return rows, " + ".join(str(p.relative_to(E.BACKEND_DIR)) if p.is_relative_to(E.BACKEND_DIR) else str(p)
                            for p in paths), digest.hexdigest()


def touches_test(args) -> bool:
    if args.queries:
        return False
    if args.dataset:
        return args.dataset.resolve() == E.TEST_PATH.resolve()
    return args.split in ("test", "all")


def ablation_table(full: dict, variants: list[tuple[str, dict]]) -> list[dict]:
    keys = (("p_at_1", "p@1"), ("recall_at_10", "r@10"), ("mrr", "MRR"), ("ndcg_at_10", "nDCG"),
            ("abstention_recall", "abst"), ("false_refusal_rate", "f-ref"))
    print("\n-- ablation " + "-" * 66)
    print(f"  {'config':<28}" + "".join(f"{name:>8}" for _, name in keys) + f"{'p50ms':>8}{'p95ms':>8}")
    table = []
    for name, res in [("all enabled", full)] + variants:
        cells = "".join(f"{_fmt(res[k]):>8}" for k, _ in keys)
        print(f"  {name:<28}{cells}{res['p50_ms']:>8.0f}{res['p95_ms']:>8.0f}")
        table.append({"config": name, **{k: res[k] for k, _ in keys}, "p50_ms": res["p50_ms"],
                      "p95_ms": res["p95_ms"]})
    print("\n  delta vs all enabled (negative = the stage was helping)")
    for name, res in variants:
        cells = "".join(f"{(res[k] or 0) - (full[k] or 0):>+8.3f}" for k, _ in keys)
        same = all(a["top"] == b["top"] and a["abstained"] == b["abstained"]
                   for a, b in zip(full["rows"], res["rows"]))
        print(f"  {name:<28}{cells}{'   (identical rankings: no effect?)' if same else ''}")
    return table


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--split", choices=("dev", "test", "all"), default="dev")
    parser.add_argument("--dataset", type=Path, help="Evaluate this .jsonl dataset instead of a split.")
    parser.add_argument("--queries", type=Path, help="Old-format queries.json (e.g. eval/queries.json).")
    parser.add_argument("--allow-test-changes", action="store_true",
                        help="Run on test.jsonl even if it no longer matches test.sha256.")
    parser.add_argument("--include-proposed", action="store_true", help="Also score status=proposed rows.")
    parser.add_argument("--no-rerank", action="store_true", help="Disable stage 3.5.")
    parser.add_argument("--collection", help="Evaluate a different Chroma collection.")
    parser.add_argument("--model", help="Evaluate a different embedding model.")
    parser.add_argument("--reranker", help="Evaluate a different cross-encoder.")
    parser.add_argument("--top-k", type=int, default=50, help="Judgments requested per query (recall@50 needs 50).")
    parser.add_argument("--by-group", action="store_true", help="Also break down by legacy group.")
    parser.add_argument("--compare", action="store_true", help="Run with and without reranking and show the delta.")
    parser.add_argument("--ablate", action="store_true", help="Re-run with each enabled USE_* stage switched off.")
    parser.add_argument("--save", type=Path, help="Write a results JSON comparable to baseline_v1.json.")
    parser.add_argument("--label", help="Label stored in the --save file.")
    parser.add_argument("--limit", type=int, help="Only the first N rows (smoke test).")
    parser.add_argument("--verbose-log", action="store_true", help="Keep the pipeline's INFO logging.")
    args = parser.parse_args()

    from loguru import logger
    if not args.verbose_log:
        logger.remove()
        logger.add(sys.stderr, level="WARNING")

    if touches_test(args):
        ok, message = E.check_test_frozen()
        if not ok and not args.allow_test_changes:
            print(f"REFUSED: {message}.\nThe test set is frozen; rebuild it deliberately with "
                  "eval/build_datasets.py --allow-test-changes, or pass --allow-test-changes here.")
            return 2
        print(f"{message}{'' if ok else '  (overridden by --allow-test-changes)'}")
        print("WARNING: this run includes the TEST split. Do not tune anything on these numbers.\n")

    # Settings must be adjusted BEFORE the pipeline modules import, because
    # they read the collection and model names at module load.
    from app.config import settings

    if args.collection:
        settings.CHROMA_COLLECTION = args.collection
    if args.model:
        settings.EMBEDDING_MODEL = args.model
    if args.reranker:
        settings.RERANKER_MODEL = args.reranker
    if args.no_rerank:
        settings.RERANK_ENABLED = False

    rows, dataset_desc, dataset_sha = load_rows(args)
    if any(r["origin"] in ("synthetic_narrative", "narrative_negative", "hand_written") for r in rows):
        print("note: this is a narrative dataset. Case findability, confidence labels and 'Strong match' leaks\n"
              "      are reported by eval/run_narrative_eval.py (retrieve_v2); this harness gives the old metrics.\n")
    if args.limit:
        rows = rows[: args.limit]

    E.quiet_pipeline()
    corpus = set(await E.corpus_judgments())

    from app.vectorstore.chroma_store import chroma_store

    enabled = [f for f in ABLATABLE if getattr(settings, f, False)]
    print(f"collection : {settings.CHROMA_COLLECTION} ({chroma_store.collection.count()} vectors)")
    print(f"corpus     : {len(corpus)} judgments in MongoDB")
    print(f"model      : {settings.EMBEDDING_MODEL}")
    print(f"reranker   : {settings.RERANKER_MODEL if settings.RERANK_ENABLED else 'disabled'}")
    print(f"stages on  : {', '.join(enabled) or 'none'}")
    print(f"dataset    : {dataset_desc} ({len(rows)} rows, sha256 {dataset_sha[:16]})\n")

    # One unscored query first: loading the embedder and cross-encoder takes
    # ~20s and would otherwise land on the first row's latency and the p95.
    await E.run_query("warm-up query", 5)

    started = time.perf_counter()
    if args.compare:
        print("-- without reranking " + "-" * 45)
        settings.RERANK_ENABLED = False
        baseline = await evaluate(rows, args.top_k, "no rerank", corpus)
        report(baseline, by_group=args.by_group)
        print("\n-- with reranking ------------------------------------------------")
        settings.RERANK_ENABLED = True
        reranked = await evaluate(rows, args.top_k, "rerank", corpus)
        report(reranked, by_group=args.by_group)
        print("\n-- delta ---------------------------------------------------------")
        for key, name in (("p_at_1", "precision@1"), ("p_at_3", "precision@3"), ("recall_at_5", "recall@5"),
                          ("recall_at_10", "recall@10"), ("mrr", "MRR"), ("ndcg_at_10", "nDCG@10")):
            before, after = baseline[key], reranked[key]
            print(f"  {name:<14} {before:.3f} -> {after:.3f}   {after - before:+.3f}")
        cost = reranked["p50_ms"] - baseline["p50_ms"]
        print(f"  {'latency p50':<14} {baseline['p50_ms']:.0f}ms -> {reranked['p50_ms']:.0f}ms   {cost:+.0f}ms")
        result = reranked
    else:
        result = await evaluate(rows, args.top_k, "run", corpus)
        report(result, by_group=args.by_group)
        legacy_check(result)

    ablation = None
    if args.ablate:
        if not enabled:
            print("\n--ablate: no USE_* stage (or RERANK_ENABLED) is enabled; nothing to switch off.")
        else:
            variants = []
            for flag in enabled:
                print(f"\n-- ablate: {flag}=False " + "-" * 40)
                setattr(settings, flag, False)
                try:
                    variants.append((f"-{flag}", await evaluate(rows, args.top_k, f"-{flag}", corpus, verbose=False)))
                finally:
                    setattr(settings, flag, True)
            ablation = ablation_table(result, variants)

    n = result["n_positive"]
    if n < 50:
        print(f"\n  WARNING: n={n} positives. The confidence interval is wider than most")
        print("  differences worth measuring. Treat this as directional only.")

    record_pending(result)
    if args.save:
        save_results(args.save, result, args, settings, dataset_desc, dataset_sha, len(corpus), ablation)
    print(f"\n  wall time {time.perf_counter() - started:.0f}s")
    return 0


def _self_check() -> None:
    assert abs(ndcg(["a", "b"], {"a": 2, "b": 1}) - 1.0) < 1e-9
    assert ndcg(["b", "a"], {"a": 2, "b": 1}) < 1.0
    assert ndcg(["x"], {"a": 2}) == 0.0
    lo, hi = bootstrap_ci([1.0] * 8 + [0.0] * 2)
    assert lo <= 0.8 <= hi and lo < hi
    assert bootstrap_ci([1.0, 0.0]) == bootstrap_ci([1.0, 0.0])
    item = {"id": "q", "query": "q", "relevant": {"a": 2, "c": 1}, "query_type": "issue",
            "origin": "real", "split": "dev"}
    row = score_row(item, {"ranked": ["b", "c", "a"], "scores": [0.9, 0.8, 0.7], "no_results": False,
                           "reranked": True, "latency_ms": 1.0})
    assert row["rank"] == 2 and row["recall_at_5"] == 1.0
    neg = score_row({**item, "id": "n", "relevant": {}, "verify_at_scale": True},
                    {"ranked": ["a"], "scores": [0.5], "no_results": False, "reranked": True, "latency_ms": 2.0})
    agg = aggregate([row, neg])
    assert agg["p_at_1"] == 0.0 and agg["mrr"] == 0.5 and len(agg["pending_negatives"]) == 1
    assert agg["abstention_recall"] is None and agg["abstention_recall_strict"] == 0.0
    # Baseline_v1's nearest-rank p95 rule.
    assert percentile(sorted(float(i) for i in range(20)), 0.95) == 18.0
    print("run_eval self-check passed")


if __name__ == "__main__":
    if "--self-check" in sys.argv:
        _self_check()
        raise SystemExit(0)
    raise SystemExit(asyncio.run(main()))
