"""
Assemble eval/datasets/narrative_{dev,test}.jsonl, and (once, at 3,000) freeze narrative_test.

Why a separate builder
----------------------
build_datasets.py owns the short-query dev/test files and their frozen hash;
the narrative set has a different life cycle. Its test split must NOT be
frozen on today's 11 judgments — the number that matters is measured on the
3,000-judgment corpus — so freezing is an explicit, separate act (--freeze)
rather than a side effect of building. Until then narrative_test.jsonl is
rebuilt freely and carries no hash.

Sources (rows are built, never hand-edited)
-------------------------------------------
    origin               source                                         label
    synthetic_narrative  eval/synthetic/synthetic_narratives.jsonl       by construction (spares excluded)
    hand_written         eval/results/narrative_baseline_v0.json (frozen) the owner's 16 positives,
                                                                         7 out-of-archive, 2 party misfires
    narrative_negative   eval/narrative_negatives.json                   hand-written, relevant {}

The split is evallib's: by the judgment's pdf_id hash for positives, by the
row id for negatives. Every description of one judgment therefore lands in
one split, the 11 judgments already assigned never move as the corpus grows,
and narrative_dev / dev.jsonl agree on which judgments are dev.

    python eval/build_narrative_datasets.py              # rebuild both files (test not frozen)
    python eval/build_narrative_datasets.py --check      # counts only, write nothing
    python eval/build_narrative_datasets.py --freeze     # ONCE, at 3,000: write narrative_test.sha256
    python eval/build_narrative_datasets.py --allow-test-changes   # rebuild a frozen narrative_test deliberately

After --freeze, a rebuild that would change narrative_test.jsonl is refused
(same rule as build_datasets.py), and run_narrative_eval.py refuses --split
test/all on a file that no longer matches its hash.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from loguru import logger

import evallib as E
import narrative_lib as N


def synthetic_rows(corpus: set[str]) -> tuple[list[dict], int]:
    """Primary (non-spare) generated rows whose judgment is still in the corpus."""
    if not N.NARRATIVE_SYNTH_PATH.exists():
        return [], 0
    rows, dropped = [], 0
    for row in E.read_jsonl(N.NARRATIVE_SYNTH_PATH):
        if row.get("spare"):
            continue
        if row["source_judgment"] not in corpus:
            dropped += 1  # judgment deleted from the corpus since generation
            continue
        rows.append(dict(row))
    return rows, dropped


async def collect() -> tuple[list[dict], dict]:
    prefix = await N.full_ids()
    corpus = set(prefix.values())
    synth, dropped_missing = synthetic_rows(corpus)
    sources = [("synthetic_narrative", synth), ("hand_written", N.hand_written_rows(prefix)),
               ("narrative_negative", N.negative_rows())]
    seen_text, seen_id, rows, dropped = set(), set(), [], Counter()
    for name, source_rows in sources:
        for row in source_rows:
            key = E.normalise_query(row["query"])
            if key in seen_text:
                dropped[name] += 1
                continue
            assert row["id"] not in seen_id, f"duplicate id {row['id']}"
            seen_text.add(key)
            seen_id.add(row["id"])
            row["split"] = E.split_for_row(row)
            N.validate_narrative_row(row)
            rows.append(row)
    info = {"duplicates_dropped": dict(dropped), "synthetic_dropped_not_in_corpus": dropped_missing,
            "corpus": len(corpus)}
    return rows, info


def print_counts(rows: list[dict]) -> None:
    def table(key: str, values) -> None:
        by = Counter((r["split"], r[key]) for r in rows)
        print(f"\n  {key:<22}{'dev':>6}{'test':>6}{'all':>6}")
        for v in values:
            d, t = by[("dev", v)], by[("test", v)]
            if d or t:
                print(f"  {v:<22}{d:>6}{t:>6}{d + t:>6}")

    table("origin", N.NARRATIVE_ORIGINS)
    table("perspective", N.PERSPECTIVES)
    table("detail", N.DETAILS)
    pos = [r for r in rows if r["relevant"]]
    neg = [r for r in rows if not r["relevant"]]
    print(f"\n  positives {len(pos)} | negatives {len(neg)} "
          f"(near-domain verify_at_scale {sum(1 for r in neg if r.get('verify_at_scale'))}, "
          f"far {sum(1 for r in neg if not r.get('verify_at_scale'))})")
    judgments = {s: {E.primary_judgment(r["relevant"]) for r in pos if r["split"] == s} for s in ("dev", "test")}
    assert not (judgments["dev"] & judgments["test"]), "a judgment appears in both splits"
    per_j = Counter(E.primary_judgment(r["relevant"]) for r in pos if r["origin"] == "synthetic_narrative")
    print(f"  judgments: dev {len(judgments['dev'])}, test {len(judgments['test'])} (disjoint); "
          f"synthetic descriptions per judgment: {dict(sorted(Counter(per_j.values()).items()))}")


def recorded_hash() -> str | None:
    if not N.NARRATIVE_TEST_HASH_PATH.exists():
        return None
    return N.NARRATIVE_TEST_HASH_PATH.read_text(encoding="utf-8").split()[0].strip()


def check_frozen() -> tuple[bool | None, str]:
    """(True frozen+matching | False frozen+changed | None not frozen, message)."""
    expected = recorded_hash()
    if expected is None:
        return None, "narrative_test is NOT frozen yet (freeze once, at 3,000 judgments)"
    if not N.NARRATIVE_TEST_PATH.exists():
        return False, f"{N.NARRATIVE_TEST_PATH.name} is missing but a hash is recorded"
    actual = E.sha256_file(N.NARRATIVE_TEST_PATH)
    if actual != expected:
        return False, f"narrative_test.jsonl {actual[:16]}... differs from frozen {expected[:16]}..."
    return True, f"narrative_test frozen, sha256 {actual[:16]}..."


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="Report counts; write nothing.")
    parser.add_argument("--freeze", action="store_true", help="Record narrative_test.sha256 (do this ONCE, at 3,000).")
    parser.add_argument("--allow-test-changes", action="store_true", help="Rewrite a frozen narrative_test.jsonl.")
    args = parser.parse_args()
    logger.remove()

    rows, info = await collect()
    rows.sort(key=lambda r: r["id"])
    dev = [r for r in rows if r["split"] == "dev"]
    test = [r for r in rows if r["split"] == "test"]
    print(f"corpus {info['corpus']} judgments | {len(rows)} rows ({len(dev)} dev, {len(test)} test) | "
          f"duplicates dropped {info['duplicates_dropped'] or 'none'} | "
          f"synthetic rows for deleted judgments {info['synthetic_dropped_not_in_corpus']}")
    print_counts(rows)
    if args.check:
        print(f"\n  {check_frozen()[1]}")
        return 0

    new_test = E.dumps_jsonl(test)
    frozen, message = check_frozen()
    if frozen is not None and N.NARRATIVE_TEST_PATH.exists():
        unchanged = N.NARRATIVE_TEST_PATH.read_text(encoding="utf-8") == new_test
        if not unchanged and not args.allow_test_changes:
            print(f"\nREFUSED: the rebuilt narrative test set differs from the frozen {N.NARRATIVE_TEST_PATH.name}. "
                  "Re-run with --allow-test-changes if that is intended (it re-freezes the hash).")
            return 2

    E.DATASETS_DIR.mkdir(parents=True, exist_ok=True)
    N.NARRATIVE_DEV_PATH.write_text(E.dumps_jsonl(dev), encoding="utf-8")
    N.NARRATIVE_TEST_PATH.write_text(new_test, encoding="utf-8")
    if args.freeze or frozen is not None:
        digest = E.sha256_file(N.NARRATIVE_TEST_PATH)
        N.NARRATIVE_TEST_HASH_PATH.write_text(f"{digest}  narrative_test.jsonl\n", encoding="utf-8")
        ok, message = check_frozen()
        assert ok, message
    else:
        message = check_frozen()[1]
    print(f"\nwrote {N.NARRATIVE_DEV_PATH.name} ({len(dev)}), {N.NARRATIVE_TEST_PATH.name} ({len(test)}); {message}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
