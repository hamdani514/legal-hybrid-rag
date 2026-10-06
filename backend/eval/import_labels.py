"""
Turn the human-filled real-query review sheet into confirmed dataset rows.

Why a separate step
-------------------
label_real_queries.py proposes; a person decides; this script records the
decision. Keeping them apart means a re-run of the proposer can never silently
overwrite a human judgment, and every confirmed label traces back to a line a
person typed in eval/labels/real_queries_review.md.

It is strict on purpose: a DECISION it cannot parse, a judgment id that matches
nothing or matches two judgments, or a TYPE outside QUERY_TYPES stops the
import with a list of the offending queries and writes nothing. A half-imported
sheet is worse than none, because nobody notices the missing rows.

    python eval/import_labels.py                 # sheet -> labels/real_queries_confirmed.jsonl
    python eval/import_labels.py --check         # parse and report only
    python eval/build_datasets.py                # then rebuild dev/test

Decision syntax (also printed at the top of the sheet):
    1 | 2 | 3            that numbered result is the answer (grade 2)
    1 3:1                #1 is the answer, #3 a relevant alternate (grade 1)
    3eff8217 5a06:1      by pdf_id prefix or filename instead of number
    NEG                  out of corpus; correct behaviour is abstention
    SKIP | LEGACY | ""   not imported
"""

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from loguru import logger

import evallib as E

_BLOCK = re.compile(r"^### (\S+)", re.M)
_CANDIDATE = re.compile(r"^\s+(\d+)\.\s+`([0-9a-f]+)`")


def parse_sheet(text: str) -> list[dict]:
    """One dict per query block: id, query, candidates (ordered prefixes), decision, type."""
    blocks = []
    starts = [m.start() for m in _BLOCK.finditer(text)]
    for start, end in zip(starts, starts[1:] + [len(text)]):
        chunk = text[start:end]
        lines = chunk.splitlines()
        block = {"id": lines[0][4:].split()[0], "query": None, "candidates": [], "decision": "", "type": ""}
        for line in lines[1:]:
            if line.startswith("QUERY:"):
                block["query"] = line[len("QUERY:"):].strip()
            elif line.startswith("DECISION:"):
                block["decision"] = line[len("DECISION:"):].strip()
            elif line.startswith("TYPE:"):
                block["type"] = line[len("TYPE:"):].strip()
            else:
                m = _CANDIDATE.match(line)
                if m:
                    block["candidates"].append(m.group(2))
        blocks.append(block)
    return blocks


def resolve(token: str, candidates: list[str], corpus: dict[str, dict]) -> str:
    """A decision token (number, id prefix or filename) -> full pdf_id. Raises ValueError."""
    if token.isdigit():
        index = int(token) - 1
        if not 0 <= index < len(candidates):
            raise ValueError(f"result #{token} does not exist (only {len(candidates)} shown)")
        token = candidates[index]
    lowered = token.lower()
    matches = [pid for pid in corpus if pid.lower().startswith(lowered)]
    if not matches:
        stem = lowered[:-4] if lowered.endswith(".pdf") else lowered
        matches = [pid for pid, meta in corpus.items()
                   if (meta.get("filename") or "").lower().removesuffix(".pdf").endswith(stem)]
    if len(matches) != 1:
        raise ValueError(f"{token!r} matches {len(matches)} judgments")
    return matches[0]


def decide(block: dict, corpus: dict[str, dict]) -> tuple[str, dict | None]:
    """('skip'|'neg'|'pos', relevant). Raises ValueError on a bad decision."""
    from app.retrieval.contracts import QUERY_TYPES

    decision = block["decision"].strip()
    upper = decision.upper()
    if upper in ("", "SKIP", "LEGACY"):
        return "skip", None
    if block["type"] not in QUERY_TYPES:
        raise ValueError(f"TYPE {block['type']!r} is not one of {', '.join(QUERY_TYPES)}")
    if upper == "NEG":
        return "neg", {}
    relevant: dict[str, int] = {}
    for token in re.split(r"[\s,]+", decision):
        if not token:
            continue
        ref, _, grade_text = token.partition(":")
        grade = int(grade_text) if grade_text else 2
        if grade not in (1, 2):
            raise ValueError(f"grade {grade} in {token!r}; use 1 or 2")
        pid = resolve(ref, block["candidates"], corpus)
        relevant[pid] = max(grade, relevant.get(pid, 0))
    if not any(g == 2 for g in relevant.values()):
        raise ValueError("no grade-2 judgment: the first id without ':1' is the answer")
    return "pos", relevant


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sheet", type=Path, default=E.REAL_REVIEW_PATH)
    parser.add_argument("--proposed", type=Path, default=E.REAL_PROPOSED_PATH)
    parser.add_argument("--out", type=Path, default=E.REAL_CONFIRMED_PATH)
    parser.add_argument("--check", action="store_true", help="Parse and report; write nothing.")
    args = parser.parse_args()

    logger.remove()
    logger.add(sys.stderr, level="WARNING")

    blocks = parse_sheet(args.sheet.read_text(encoding="utf-8"))
    proposed = {}
    if args.proposed.exists():
        proposed = {q["id"]: q for q in json.loads(args.proposed.read_text(encoding="utf-8"))["queries"]}

    corpus = await E.corpus_judgments()
    # Judgments the sheet shows but Mongo no longer has still resolve by prefix.
    for entry in proposed.values():
        for hit in entry.get("top_all", []) + entry.get("below_floor", []):
            corpus.setdefault(hit["judgment_id"], {"filename": hit.get("filename", "")})

    rows, errors, counts = [], [], {"pos": 0, "neg": 0, "skip": 0}
    for block in blocks:
        if not block["query"]:
            errors.append(f"{block['id']}: no QUERY line")
            continue
        # Expand numbered candidates to full ids, using the proposal file when present.
        source = proposed.get(block["id"])
        if source:
            shown = source["below_floor"] if source["abstained"] else source["top"]
            full = [h["judgment_id"] for h in shown]
            if [f[:len(p)] for f, p in zip(full, block["candidates"])] == block["candidates"]:
                block["candidates"] = full
        try:
            kind, relevant = decide(block, corpus)
        except ValueError as e:
            errors.append(f"{block['id']} ({block['query'][:50]}): {e}")
            continue
        counts[kind] += 1
        if kind == "skip":
            continue
        row = {
            "id": block["id"],
            "query": block["query"],
            "relevant": relevant,
            "query_type": block["type"],
            "origin": "real",
            "status": "confirmed",
            "notes": "confirmed by human review of the real-query sheet"
                     + ("; out of corpus — abstention expected" if kind == "neg" else ""),
            "asked": (source or {}).get("count"),
        }
        row["split"] = E.split_for_row(row)
        E.validate_row(row)
        rows.append(row)

    print(f"{len(blocks)} blocks: {counts['pos']} positive, {counts['neg']} negative, "
          f"{counts['skip']} skipped/legacy/unfilled")
    if errors:
        print(f"\n{len(errors)} decision(s) could not be imported — fix them in the sheet and re-run:")
        for err in errors:
            print(f"  {err}")
        return 1
    if args.check:
        return 0
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(E.dumps_jsonl(sorted(rows, key=lambda r: r["id"])), encoding="utf-8")
    print(f"wrote {len(rows)} confirmed rows to {args.out}")
    return 0


def _self_check() -> None:
    corpus = {"3eff8217-aaaa": {"filename": "judgement_C_A_23-P_2017.pdf"},
              "5a06e4ef-bbbb": {"filename": "judgement_C_A_42-K_2016.pdf"}}
    block = {"id": "real-x", "query": "q", "candidates": ["3eff8217-aaaa", "5a06e4ef-bbbb"],
             "decision": "1 2:1", "type": "issue"}
    assert decide(block, corpus) == ("pos", {"3eff8217-aaaa": 2, "5a06e4ef-bbbb": 1})
    assert decide({**block, "decision": "C_A_42-K_2016"}, corpus) == ("pos", {"5a06e4ef-bbbb": 2})
    assert decide({**block, "decision": "neg"}, corpus) == ("neg", {})
    assert decide({**block, "decision": ""}, corpus) == ("skip", None)
    for bad in ("4", "2:1", "zzz", "1:3"):
        try:
            decide({**block, "decision": bad}, corpus)
        except ValueError:
            continue
        raise AssertionError(f"accepted bad decision {bad!r}")
    sheet = "### real-x  (asked 2x)\n\nQUERY: hello\n  1. `3eff8217` f.pdf  score 0.9\nDECISION: 1\nTYPE: issue\n"
    parsed = parse_sheet(sheet)[0]
    assert parsed["candidates"] == ["3eff8217"] and parsed["decision"] == "1" and parsed["query"] == "hello"
    print("import_labels self-check passed")


if __name__ == "__main__":
    if "--self-check" in sys.argv:
        _self_check()
        raise SystemExit(0)
    raise SystemExit(asyncio.run(main()))
