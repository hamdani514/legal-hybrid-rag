"""
Generate synthetic evaluation queries from the judgments themselves.

Why
---
Real queries are the gold standard but there are only ~80 of them, and they
cluster on a handful of judgments. To measure retrieval across a 3,000-judgment
corpus we need queries about judgments nobody has searched for yet. One LLM
call per judgment writes three, each testing a different failure mode:

* paraphrase — the facts as a layperson would tell them, with none of the
  judgment's legal vocabulary. This is the query keyword search cannot answer.
* issue      — the legal question the Court decided, as a lawyer would ask it.
* entity     — a party, place, case number or statute a lawyer would type.

The judgment that produced a query is its grade-2 answer, by construction.

Leakage check
-------------
A query that copies a phrase from the judgment tests string matching, not
retrieval. Any query sharing a word 4-gram with the judgment's full text is
rejected and logged with the offending phrase. For entity queries only, a
4-gram made entirely of tokens that are names or numbers in the query (capitalised
or digit-bearing: "Mir Saleem Ahmed Khosa", "5 Q of 2014" is NOT exempt because
"of" is lower-case) is exempt, because naming the party IS the query; any
shared ordinary phrase still rejects it.

Scale
-----
Today it runs on all judgments (11 calls). At full corpus run it with
`--sample 150`: if Agent B's MongoDB `case_cards` collection exists the sample
is stratified by subject (proportional, at least one per subject), otherwise it
is a deterministic hash-ordered sample. The output file is appended to and
re-runs skip judgments already done, so a run killed by a rate limit resumes.

    python eval/synth_queries.py --dry-run            # show what would run
    python eval/synth_queries.py                      # every judgment
    python eval/synth_queries.py --sample 150 --max-calls 160

Training-data note: the split column is the judgment's split. Agent F must not
train on rows whose split is "test".
"""

import argparse
import asyncio
import hashlib
import json
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from loguru import logger

import evallib as E

KINDS = {"paraphrase": "paraphrase", "issue": "issue", "entity": "entity"}
REJECTIONS_PATH = E.SYNTH_DIR / "rejections.jsonl"
SECTION_ORDER = ("HEADER_CORAM", "FACTS", "LEGAL_ISSUES", "ANALYSIS_RATIO", "FINAL_ORDER")
PROMPT_CHARS = 9000

SYSTEM_PROMPT = """You write realistic search queries that a Pakistani lawyer or litigant would type into a case-law search engine to find ONE specific Supreme Court judgment. You are given that judgment. Return ONLY a JSON object with exactly these keys:

"paraphrase": 10-25 words describing what happened between the parties in plain everyday English, the way a non-lawyer client would tell it. Do NOT use any legal terms or any phrase from the judgment (no "appeal", "petition", "tribunal", "respondent", statute names, Latin, or court names). Use your own words for every idea.
"issue": one question (8-25 words) stating the legal question the Court decided, phrased the way a lawyer would ask a colleague. Rephrase; do not copy sentences from the judgment.
"entity": 3-10 words a lawyer would type to find this case by name: a party name, place, case number or statute, plus one or two words of topic. No full sentences.

Never copy four or more consecutive words from the judgment text."""


def leaked_ngrams(query: str, source_grams: set, exempt_names: bool) -> list[str]:
    """4-grams the query shares with the source (after the entity exemption)."""
    words = query.split()
    # Map each lower-cased token back to whether it looked like a name/number in the query.
    name_like: dict[str, bool] = {}
    for word in words:
        for tok in E.tokens(word):
            name_like[tok] = name_like.get(tok, False) or word[:1].isupper() or any(c.isdigit() for c in word)
    hits = []
    for gram in E.ngrams(E.tokens(query), 4):
        if gram not in source_grams:
            continue
        if exempt_names and all(name_like.get(t, False) for t in gram):
            continue
        hits.append(" ".join(gram))
    return hits


async def subjects_by_judgment() -> dict[str, str]:
    """pdf_id -> subject from Agent B's case_cards, if that collection exists."""
    from app.database import db

    if not db.is_connected:
        return {}
    names = await db.database.list_collection_names()
    if "case_cards" not in names:
        return {}
    out = {}
    async for card in db.database.case_cards.find({}, {"judgment_id": 1, "subject": 1, "_id": 0}):
        if card.get("judgment_id"):
            out[card["judgment_id"]] = card.get("subject") or "Other"
    return out


def _hash_order(pid: str) -> str:
    return hashlib.sha256(f"synth-sample:{pid}".encode()).hexdigest()


def choose_sample(pdf_ids: list[str], subjects: dict[str, str], n: int | None) -> list[str]:
    """Deterministic sample; stratified by subject when subjects are known."""
    ordered = sorted(pdf_ids, key=_hash_order)
    if not n or n >= len(ordered):
        return ordered
    if not subjects:
        return ordered[:n]
    groups: dict[str, list[str]] = defaultdict(list)
    for pid in ordered:
        groups[subjects.get(pid, "Other")].append(pid)
    # Proportional allocation, at least one per subject, largest remainders fill the rest.
    total = len(ordered)
    quota = {s: max(1, int(n * len(g) / total)) for s, g in groups.items()}
    while sum(quota.values()) > n:
        biggest = max(quota, key=lambda s: quota[s])
        quota[biggest] -= 1
    spare = n - sum(quota.values())
    for s in sorted(groups, key=lambda s: -(n * len(groups[s]) / total) % 1)[:spare]:
        quota[s] += 1
    chosen = []
    for s, group in groups.items():
        chosen.extend(group[: quota[s]])
    return sorted(chosen, key=_hash_order)


def build_prompt(sections: dict[str, str]) -> str:
    parts, budget = [], PROMPT_CHARS
    for key in SECTION_ORDER:
        text = (sections.get(key) or "").strip()
        if not text or budget <= 0:
            continue
        piece = text[: max(budget, 0)]
        parts.append(f"[{key}]\n{piece}")
        budget -= len(piece)
    return "JUDGMENT:\n\n" + "\n\n".join(parts) + "\n\nReturn the JSON object now."


async def call_llm(user_prompt: str) -> dict | None:
    from app.retrieval.comparator import _parse
    from app.retrieval.llm_responder import _complete

    return _parse(await _complete(SYSTEM_PROMPT, user_prompt, 600))


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sample", type=int, help="Judgments to sample (stratified if case_cards exist).")
    parser.add_argument("--max-calls", type=int, default=15, help="Hard cap on LLM calls, retries included.")
    parser.add_argument("--sleep", type=float, default=1.0, help="Seconds between calls.")
    parser.add_argument("--dry-run", action="store_true", help="Print the plan; make no LLM call.")
    parser.add_argument("--out", type=Path, default=E.SYNTH_PATH)
    args = parser.parse_args()

    logger.remove()
    logger.add(sys.stderr, level="WARNING")

    corpus = await E.corpus_judgments()
    subjects = await subjects_by_judgment()
    sample = choose_sample(list(corpus), subjects, args.sample)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    existing = E.read_jsonl(args.out) if args.out.exists() else []
    done = {r["source_judgment"] for r in existing}
    todo = [pid for pid in sample if pid not in done]
    print(f"corpus {len(corpus)} | subjects from case_cards: {'yes' if subjects else 'no'} | "
          f"sample {len(sample)} | already done {len(sample) - len(todo)} | to do {len(todo)}")

    if args.dry_run:
        for pid in todo:
            print(f"  would generate for {pid[:8]} {corpus[pid].get('filename', '')} "
                  f"[{subjects.get(pid, '-')}] split={E.split_for_key(pid)}")
        return 0

    calls = kept = rejected = 0
    for pid in todo:
        if calls >= args.max_calls:
            print(f"stopping: LLM call budget {args.max_calls} reached")
            break
        sections = await E.judgment_text(pid)
        source_grams = E.ngrams(E.tokens(" ".join(sections.values())), 4)
        prompt = build_prompt(sections)

        parsed, backoff = None, 5.0
        for attempt in range(3):
            if calls >= args.max_calls:
                break
            calls += 1
            parsed = await call_llm(prompt)
            await asyncio.sleep(args.sleep)
            if parsed:
                break
            # _complete swallows the HTTP error; a 429 shows up as an empty parse.
            logger.warning(f"{pid[:8]}: no JSON on attempt {attempt + 1}; backing off {backoff:.0f}s")
            await asyncio.sleep(backoff)
            backoff *= 3
        if not parsed:
            print(f"  {pid[:8]}: FAILED after {calls} total calls")
            continue

        split = E.split_for_key(pid)
        new_rows, rejects = [], []
        for kind, query_type in KINDS.items():
            query = str(parsed.get(kind) or "").strip()
            if not query:
                rejects.append({"source_judgment": pid, "kind": kind, "query": "", "reason": "missing"})
                continue
            leaks = leaked_ngrams(query, source_grams, exempt_names=(kind == "entity"))
            if leaks:
                rejects.append({"source_judgment": pid, "kind": kind, "query": query,
                                "reason": "4-gram leakage", "ngrams": leaks})
                logger.warning(f"rejected {kind} for {pid[:8]}: shares {leaks[:3]} with the judgment")
                continue
            new_rows.append({
                "id": f"syn-{pid[:8]}-{kind}",
                "query": query,
                "relevant": {pid: 2},
                "query_type": query_type,
                "origin": "synthetic",
                "split": split,
                "status": "confirmed",
                "notes": "label by construction (generated from this judgment); query text not human-reviewed",
                "source_judgment": pid,
                "subject": subjects.get(pid),
                "generated_at": datetime.now().isoformat(timespec="seconds"),
            })
        with args.out.open("a", encoding="utf-8") as fh:
            fh.write(E.dumps_jsonl(new_rows))
        if rejects:
            with REJECTIONS_PATH.open("a", encoding="utf-8") as fh:
                fh.write(E.dumps_jsonl(rejects))
        kept += len(new_rows)
        rejected += len(rejects)
        print(f"  {pid[:8]} {corpus[pid].get('filename', ''):<32} kept {len(new_rows)} rejected {len(rejects)}")

    print(f"\nLLM calls {calls} | queries kept {kept} | rejected {rejected} (see {REJECTIONS_PATH.name})")
    return 0


def _self_check() -> None:
    grams = E.ngrams(E.tokens("the appellant Mir Saleem Ahmed Khosa filed an election petition before the tribunal"), 4)
    assert sorted(leaked_ngrams("an election petition before the court", grams, False)) == [
        "an election petition before", "election petition before the"]
    assert leaked_ngrams("Mir Saleem Ahmed Khosa vote case", grams, exempt_names=True) == []
    assert leaked_ngrams("Mir Saleem Ahmed Khosa vote case", grams, exempt_names=False)
    assert choose_sample(["a", "b", "c"], {}, 2) == choose_sample(["c", "b", "a"], {}, 2)
    subj = {f"p{i}": ("Bail" if i < 8 else "Tax") for i in range(10)}
    picked = choose_sample(list(subj), subj, 4)
    assert len(picked) == 4 and any(subj[p] == "Tax" for p in picked)
    print("synth_queries self-check passed")


if __name__ == "__main__":
    if "--self-check" in sys.argv:
        _self_check()
        raise SystemExit(0)
    raise SystemExit(asyncio.run(main()))
