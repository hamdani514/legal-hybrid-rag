"""
Assemble eval/datasets/{dev,test}.jsonl from every labelled source, and freeze test.

Why
---
The evaluation set is built, never hand-edited: every row comes from one of
four sources, each with its own provenance, and this script is the only thing
that writes the dataset files. Re-running it after new labels arrive is how
the set grows.

    origin     source                                       status
    legacy     eval/queries.json (read, never modified)      confirmed
    real       eval/labels/real_queries_confirmed.jsonl      confirmed (by a human, via import_labels.py)
    synthetic  eval/synthetic/synthetic_queries.jsonl        confirmed (label by construction)
    negative   eval/negatives.json                           confirmed (hand-written)

Real queries the human has not yet confirmed are NOT included: their only
label would be the system's own top-1, and scoring a system against its own
output measures nothing.

Duplicates (same query text after normalisation) keep the first source in the
order above, so a real query that is also a legacy query appears once.

The freeze
----------
test.jsonl is the number reported once, at the end. If it already exists with
a recorded hash and the rebuilt content differs, the script refuses unless
--allow-test-changes is given — the point is that growing the dataset is a
deliberate, visible act, not a side effect. When it does write test.jsonl it
records the new SHA-256 in test.sha256, which run_eval.py checks.

    python eval/build_datasets.py                       # rebuild; refuses to change a frozen test set
    python eval/build_datasets.py --allow-test-changes  # e.g. after the 3,000-judgment ingest
    python eval/build_datasets.py --check               # report counts, write nothing
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import evallib as E


def negatives_rows() -> list[dict]:
    payload = json.loads(E.NEGATIVES_PATH.read_text(encoding="utf-8"))
    rows = []
    for item in payload["negatives"]:
        rows.append({
            "id": item["id"],
            "query": item["query"],
            "relevant": {},
            "query_type": item.get("query_type", "unknown"),
            "origin": "negative",
            "status": "confirmed",
            "notes": f"hand-written {item['kind']} out-of-corpus query",
            "kind": item["kind"],
            "verify_at_scale": bool(item.get("verify_at_scale")),
        })
    return rows


def collect() -> tuple[list[dict], dict[str, int]]:
    sources = [
        ("legacy", E.load_legacy_file(E.LEGACY_PATH)),
        ("real", E.read_jsonl(E.REAL_CONFIRMED_PATH) if E.REAL_CONFIRMED_PATH.exists() else []),
        ("synthetic", E.read_jsonl(E.SYNTH_PATH) if E.SYNTH_PATH.exists() else []),
        ("negative", negatives_rows()),
    ]
    seen_text: set[str] = set()
    seen_id: set[str] = set()
    rows, dropped = [], Counter()
    for name, source_rows in sources:
        for row in source_rows:
            key = E.normalise_query(row["query"])
            if key in seen_text:
                dropped[name] += 1
                continue
            assert row["id"] not in seen_id, f"duplicate id {row['id']}"
            seen_text.add(key)
            seen_id.add(row["id"])
            row = dict(row)
            row["split"] = E.split_for_row(row)
            E.validate_row(row)
            rows.append(row)
    return rows, dict(dropped)


def print_counts(rows: list[dict]) -> None:
    by = Counter((r["split"], r["origin"]) for r in rows)
    origins = [o for o in E.ORIGINS if any(r["origin"] == o for r in rows)]
    print(f"\n  {'split':<6}" + "".join(f"{o:>11}" for o in origins) + f"{'total':>8}")
    for split in ("dev", "test"):
        line = f"  {split:<6}" + "".join(f"{by[(split, o)]:>11}" for o in origins)
        print(line + f"{sum(by[(split, o)] for o in origins):>8}")
    print(f"  {'all':<6}" + "".join(f"{sum(by[(s, o)] for s in ('dev', 'test')):>11}" for o in origins)
          + f"{len(rows):>8}")

    from app.retrieval.contracts import QUERY_TYPES
    types = Counter((r["split"], r["query_type"]) for r in rows)
    print(f"\n  {'query type':<12}{'dev':>6}{'test':>6}")
    for qt in QUERY_TYPES:
        if types[("dev", qt)] or types[("test", qt)]:
            print(f"  {qt:<12}{types[('dev', qt)]:>6}{types[('test', qt)]:>6}")

    judgments = {s: {E.primary_judgment(r["relevant"]) for r in rows if r["split"] == s and r["relevant"]}
                 for s in ("dev", "test")}
    assert not (judgments["dev"] & judgments["test"]), "a judgment appears in both splits"
    print(f"\n  judgments: dev {len(judgments['dev'])}, test {len(judgments['test'])} (disjoint)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--allow-test-changes", action="store_true",
                        help="Rewrite a frozen test.jsonl and record its new hash.")
    parser.add_argument("--check", action="store_true", help="Report counts; write nothing.")
    args = parser.parse_args()

    rows, dropped = collect()
    rows.sort(key=lambda r: r["id"])
    dev = [r for r in rows if r["split"] == "dev"]
    test = [r for r in rows if r["split"] == "test"]

    print(f"{len(rows)} rows ({len(dev)} dev, {len(test)} test); duplicates dropped: {dropped or 'none'}")
    print_counts(rows)
    if args.check:
        return 0

    new_test = E.dumps_jsonl(test)
    if E.TEST_PATH.exists() and E.recorded_test_hash():
        unchanged = E.TEST_PATH.read_text(encoding="utf-8") == new_test
        if not unchanged and not args.allow_test_changes:
            print(f"\nREFUSED: the rebuilt test set differs from the frozen {E.TEST_PATH.name}. "
                  "Re-run with --allow-test-changes if that is intended (it re-freezes the hash).")
            return 2

    E.DATASETS_DIR.mkdir(parents=True, exist_ok=True)
    E.DEV_PATH.write_text(E.dumps_jsonl(dev), encoding="utf-8")
    E.TEST_PATH.write_text(new_test, encoding="utf-8")
    digest = E.sha256_file(E.TEST_PATH)
    E.TEST_HASH_PATH.write_text(f"{digest}  test.jsonl\n", encoding="utf-8")
    ok, message = E.check_test_frozen()
    assert ok, message
    print(f"\nwrote {E.DEV_PATH.name} ({len(dev)}), {E.TEST_PATH.name} ({len(test)}); {message}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
