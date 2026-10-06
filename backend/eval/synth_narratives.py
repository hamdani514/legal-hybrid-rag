"""
Generate case DESCRIPTIONS (narratives) of each judgment from several perspectives.

Why
---
Users now search by describing their own case in 40-150 words — what
happened, what each side claims, what the courts below held, sometimes the
outcome — and they are lawyers, victims or the opposing party. One judgment
must be findable from all of those tellings. synth_queries.py writes short
queries (10-25 words); a pipeline tuned on those can still fail on a
120-word story told by the losing side. So one LLM call per judgment writes
FOUR slots, two alternatives each:

    slot                  detail    voice
    appellant_lawyer      detailed  lawyer for the side that appealed to the Supreme Court
    opposing_party        detailed  the respondent, first person
    layperson             loose     a victim / affected person; plain words, no names, no case number
    layperson_other_side  loose     a second loose phrasing, from the other side

The first alternative in a slot that passes every check is kept; the second
is a spare so one leaked phrase does not cost a retry call (the free tier is
15 requests/min shared by every agent and user). Spares that also pass are
written with "spare": true and are not used by the dataset builder.

The judgment that produced a description is its grade-2 answer, by construction.

Checks (every rejection is logged to synthetic/narrative_rejections.jsonl)
-------------------------------------------------------------------------
* **length** 40-150 words.
* **case number**: never the case number, a reported citation, or a case key
  from the card ("5-Q of 2014", "2016 SCMR 900") — that is an exact lookup,
  not a description.
* **party names** (loose slots only): no token of the appellant's/respondent's
  name (institutional words like Province, Federation, Police excluded).
* **4-gram leakage**: a description that shares a word 4-gram with the
  judgment (all sections + the case card, which is itself derived from the
  judgment) tests string matching, not retrieval, and is rejected. Two
  exemptions, both narrow and both logged:
    - names/numbers (detailed slots only, as in synth_queries): a 4-gram made
      of tokens that are capitalised or digit-bearing in the description, plus
      at most two function words ("the Peshawar High Court", "Ministry of
      Foreign Affairs") — naming the party or the court IS what a lawyer does;
    - generic legal boilerplate (all slots): a 4-gram made ONLY of function
      words and the procedural vocabulary every judgment shares ("at the time
      of", "and the high court", "the trial court dismissed"). Calibrated on
      the owner's hand-written descriptions in narrative_baseline_v0.json
      (`--calibrate`, no LLM): against judgment + card the literal rule
      rejects 11/11 of the human-written DETAILED texts (0/5 loose); with the
      exemptions 9/11 are still rejected, each for a distinctive phrase ("in
      lieu of dower", "registered the trade mark", "margin of 65 votes", "the
      revenue record showed"), and the 2 rescued ones shared only "the
      Federal Service Tribunal" / "the high court had". So the rule stays
      strict where it matters; it is stricter than what a human lawyer writes
      after reading the judgment, which is why each slot gets two
      alternatives. --strict-leakage applies the literal rule.

Scale and resumability
----------------------
Rows are appended per judgment and every call is logged
(synthetic/narrative_calls.jsonl); a re-run skips judgments that already have
a successful call, so a run stopped by a rate limit resumes where it stopped.
--sample N picks a deterministic sample stratified by case_cards.subject
(synth_queries.choose_sample), --max-calls caps the LLM calls including
retries, --fill-missing spends one call per judgment whose slots were all
rejected, asking only for those slots.

    python eval/synth_narratives.py --dry-run
    python eval/synth_narratives.py --max-calls 14             # 11 judgments today
    python eval/synth_narratives.py --sample 200 --max-calls 220   # at 1,000
    python eval/synth_narratives.py --fill-missing --max-calls 20
    python eval/synth_narratives.py --recheck        # re-apply the checks to stored outputs, 0 LLM calls
    python eval/synth_narratives.py --calibrate      # the checks on the hand-written narratives, 0 LLM calls
    python eval/synth_narratives.py --self-check

Every call's parsed JSON is kept in narrative_calls.jsonl, so changing a check
never costs a call: edit the rule, run --recheck.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from loguru import logger

import evallib as E
import narrative_lib as N
from synth_queries import choose_sample, subjects_by_judgment

SECTION_ORDER = ("FACTS", "ARGUMENTS", "LEGAL_ISSUES", "ANALYSIS_RATIO", "FINAL_ORDER")
SECTION_CHARS = {"FACTS": 4000, "ARGUMENTS": 3000, "LEGAL_ISSUES": 800, "ANALYSIS_RATIO": 4500, "FINAL_ORDER": 1200}
MIN_WORDS, MAX_WORDS = 40, 150
MAX_TOKENS = 4000

# Function words and the procedural vocabulary every Supreme Court judgment
# uses. A 4-gram made only of these says nothing about WHICH judgment it is.
_FUNCTION = set("""
a an the and or but of to in on at by for from with without into onto over under after before
during since until upon about against between through within as than that this these those it its
is are was were be been being has have had do does did not no nor so such then there their they
them he she his her him we our us i my me you your who whom which what when where why how all any
each both either neither some more most other same own only also just very can could may might
must shall should will would one two
""".split())
_PROCEDURE = set("""
court courts high supreme trial appellate lower tribunal judge judges bench case cases suit suits
appeal appeals appealed appellant appellants respondent respondents petition petitions petitioner
filed file filing decree decreed decrees dismissed dismiss dismissal allowed allow set aside order
ordered orders held hold holding judgment judgments decision decided decide favour favor time
date year years side sides party parties claim claimed claims said says argued argue matter law
upheld uphold reversed reverse restored challenge challenged against property civil evidence failed counsel ground grounds back remand remanded
approached
""".split())
GENERIC = _FUNCTION | _PROCEDURE

# Words in a party caption that are not a person's or company's name.
_CAPTION_STOP = GENERIC | set("""
others another through secretary ministry province federation government pakistan punjab sindh
balochistan khyber pakhtunkhwa islamabad karachi lahore quetta peshawar police inspector general
chief officer board corporation municipal administrator district limited private ltd pvt services
deceased lrs mst mr mrs syed sardar mir department director collector revenue election commission
national assembly provincial post master gpo affairs foreign
""".split())

SYSTEM_PROMPT = """You write realistic case descriptions that people type into a Pakistani Supreme Court case-law search engine when they are looking for a judgment about a situation like their own. You are given ONE judgment (its case card and sections). Write descriptions of THIS case as different people would tell it.

Return ONLY a JSON object. Each requested key maps to a list of TWO alternative descriptions, each an object {"text": "...", "mentions_outcome": true|false}. The two alternatives must be worded differently from each other.

Keys:
"appellant_lawyer": the lawyer for the side that appealed to the Supreme Court ("my client ..."). Detailed, 70-130 words. The facts, what each side claims, what the courts or tribunal below decided. Legal terms and party names are allowed.
"opposing_party": the respondent in the Supreme Court telling it in the first person ("I"/"we"), from their side. Detailed, 70-130 words. Facts, what they say, what the other side says, what the courts below decided.
"layperson": an ordinary person affected by the dispute (a victim or a family member) telling it in plain everyday words. Loose, 45-90 words. Few legal terms. NO names of people or companies, NO case numbers, NO dates, NO section numbers.
"layperson_other_side": the same rules as "layperson", but told by someone on the OTHER side from the "layperson" text, in different words.

Rules for every description:
- NEVER copy four or more consecutive words from the judgment or the case card. Restate every idea in your own words; avoid the judgment's distinctive phrases and legal terms of art. A real client does not talk like the judgment: say "the land papers listed them as owners" rather than "the revenue record showed", "they said I came too late" rather than "the suit was time barred". Even common phrases must be reworded if the judgment uses them.
- NEVER include the case number, a law-report citation, or the date of the judgment.
- Stay faithful to the facts; do not invent facts that contradict the judgment.
- About half of all descriptions should state the Supreme Court's final outcome, and when they do it must be correct (given below as SUPREME COURT OUTCOME). The others stop at what the courts below decided. "mentions_outcome" says whether the text states the Supreme Court's outcome.
- Write as a real person would type it: natural, specific, not a summary of the judgment."""


# ── Checks ──────────────────────────────────────────────────────────────────

def leaked_ngrams(text: str, source_grams: set, exempt_names: bool, strict: bool = False) -> tuple[list[str], list[str]]:
    """(rejecting 4-grams, exempted 4-grams) the text shares with the source."""
    name_like: dict[str, bool] = {}
    for word in text.split():
        for tok in E.tokens(word):
            name_like[tok] = name_like.get(tok, False) or word[:1].isupper() or any(c.isdigit() for c in word)
    hits, exempt = [], []
    for gram in sorted(E.ngrams(E.tokens(text), 4)):
        if gram not in source_grams:
            continue
        phrase = " ".join(gram)
        # A name may carry its articles: "the Peshawar High Court", "Ministry of Foreign Affairs".
        names = sum(1 for t in gram if name_like.get(t, False))
        if not strict and exempt_names and names >= 2 and all(name_like.get(t, False) or t in _FUNCTION for t in gram):
            exempt.append(f"name:{phrase}")
        elif not strict and all(t in GENERIC for t in gram):
            exempt.append(f"generic:{phrase}")
        else:
            hits.append(phrase)
    return hits, exempt


def party_name_tokens(card: dict) -> set[str]:
    """Lower-cased name tokens of the parties, institutional words removed."""
    out = set()
    for key in ("appellant", "respondent"):
        for tok in E.tokens(str(card.get(key) or "")):
            if len(tok) >= 3 and tok not in _CAPTION_STOP and not tok.isdigit():
                out.add(tok)
    return out


def case_number_hits(text: str, card: dict) -> list[str]:
    """Case numbers / citations / card case keys present in the text."""
    hits = [m.group(0) for m in E._CASE_NO.finditer(text)] + [m.group(0) for m in E._REPORTED.finditer(text)]
    hits += [m.group(0) for m in re.finditer(r"\b\d+\s*-\s*[A-Z]\b\s*(of|/)\s*\d{2,4}", text)]
    low = text.lower()
    for key in _as_list(card.get("case_keys")) + _as_list(card.get("citations")):
        key = str(key)
        number = re.search(r"\d+(-[A-Za-z])?", key)
        if key.lower() in low:
            hits.append(key)
        elif number and re.search(rf"\b{re.escape(number.group(0))}\b", text) and "-" in number.group(0):
            hits.append(number.group(0))
    return hits


def _as_list(value) -> list:
    if isinstance(value, list):
        return value
    if isinstance(value, str) and value.strip().startswith("["):
        try:
            import ast
            parsed = ast.literal_eval(value)
            return parsed if isinstance(parsed, list) else []
        except (ValueError, SyntaxError):
            return []
    return [value] if value else []


def check_description(text: str, detail: str, source_grams: set, card: dict, strict: bool) -> tuple[list[str], dict]:
    """(reasons it is rejected, details) for one description."""
    reasons, info = [], {}
    words = len(text.split())
    info["words"] = words
    if not MIN_WORDS <= words <= MAX_WORDS:
        reasons.append(f"length {words} not in {MIN_WORDS}-{MAX_WORDS}")
    numbers = case_number_hits(text, card)
    if numbers:
        reasons.append("case number")
        info["case_numbers"] = numbers
    if detail == "loose":
        names = sorted(t for t in party_name_tokens(card) if re.search(rf"\b{re.escape(t)}\b", text.lower()))
        if names:
            reasons.append("party name in a loose description")
            info["names"] = names
    leaks, exempt = leaked_ngrams(text, source_grams, exempt_names=(detail == "detailed"), strict=strict)
    if leaks:
        reasons.append("4-gram leakage")
        info["ngrams"] = leaks
    if exempt:
        info["exempted_ngrams"] = exempt
    return reasons, info


# ── Prompt ──────────────────────────────────────────────────────────────────

async def load_card(pid: str) -> dict:
    from app.database import db

    if not db.is_connected:
        return {}
    card = await db.database.case_cards.find_one({"judgment_id": pid}, {"_id": 0, "llm_raw": 0})
    return card or {}


def build_prompt(card: dict, sections: dict[str, str], slots: list[str]) -> str:
    lines = ["CASE CARD"]
    for key in ("subject", "appellant", "respondent", "lower_court", "headnote", "issues", "holding"):
        value = card.get(key)
        if value:
            lines.append(f"{key}: {value if not isinstance(value, list) else '; '.join(map(str, value))}")
    outcome = card.get("outcome") or "see FINAL_ORDER"
    lines.append(f"SUPREME COURT OUTCOME: {outcome}")
    if not card:
        lines.append("(no case card yet: read the parties and outcome from the sections)")
    parts = []
    for key in SECTION_ORDER:
        text = (sections.get(key) or "").strip()
        if text:
            parts.append(f"[{key}]\n{text[:SECTION_CHARS[key]]}")
    return ("\n".join(lines) + "\n\nJUDGMENT SECTIONS\n\n" + "\n\n".join(parts)
            + f"\n\nReturn the JSON object now with exactly these keys: {', '.join(slots)}.")


async def call_llm(user_prompt: str) -> tuple[dict | None, bool]:
    """(parsed JSON or None, rate_limited). Imports at call time: another agent is changing these modules."""
    from app.retrieval import llm_responder

    try:
        from app.retrieval.comparator import _parse
    except Exception:
        _parse = None
    try:
        raw = await llm_responder._complete(SYSTEM_PROMPT, user_prompt, MAX_TOKENS)
    except Exception as e:  # a structured limiter may raise instead of returning a sentinel
        return None, bool(N._RATE_LIMIT.search(str(e)))
    text, limited = N.llm_text(raw)
    if not text:
        return None, limited
    parsed = _parse(text) if _parse else None
    if parsed is None:
        try:
            start, end = text.find("{"), text.rfind("}")
            parsed = json.loads(text[start:end + 1]) if start != -1 else None
        except json.JSONDecodeError:
            parsed = None
    return (parsed if isinstance(parsed, dict) else None), limited


# ── Main ────────────────────────────────────────────────────────────────────

async def judgment_material(pid: str) -> tuple[dict, dict, set]:
    """(card, sections, source 4-grams over judgment + card) for one judgment."""
    card = await load_card(pid)
    sections = await E.judgment_text(pid)
    card_text = " ".join(str(card.get(k) or "") for k in ("headnote", "issues", "holding", "keywords"))
    return card, sections, E.ngrams(E.tokens(" ".join(sections.values()) + " " + card_text), 4)


async def recheck(corpus: dict, subjects: dict, strict: bool) -> int:
    """Rebuild synthetic_narratives.jsonl + narrative_rejections.jsonl from the call log's stored outputs.

    A rule change (length, names, leakage exemptions) must never cost LLM calls:
    every call's parsed JSON is in narrative_calls.jsonl, so the checks are
    simply re-run. Calls are replayed in log order; a slot filled by an earlier
    call is not re-filled by a later --fill-missing call. Judgments whose call
    has no stored output keep their current rows.
    """
    calls_log = E.read_jsonl(N.NARRATIVE_CALLS_PATH) if N.NARRATIVE_CALLS_PATH.exists() else []
    old_rows = E.read_jsonl(N.NARRATIVE_SYNTH_PATH) if N.NARRATIVE_SYNTH_PATH.exists() else []
    old_rej = E.read_jsonl(N.NARRATIVE_REJECTIONS_PATH) if N.NARRATIVE_REJECTIONS_PATH.exists() else []
    replayable = {c["source_judgment"] for c in calls_log if c.get("ok") and c.get("parsed")}
    rows = [r for r in old_rows if r["source_judgment"] not in replayable]
    rejects = [r for r in old_rej if r["source_judgment"] not in replayable]
    filled: dict[str, set] = {}
    material: dict[str, tuple] = {}
    for call in calls_log:
        pid = call["source_judgment"]
        if pid not in replayable or not (call.get("ok") and call.get("parsed")):
            continue
        if pid not in corpus:
            logger.warning(f"{pid[:8]} is no longer in the corpus; dropped")
            continue
        if pid not in material:
            material[pid] = await judgment_material(pid)
        card, _, grams = material[pid]
        slots = [s for s in call["slots"] if s not in filled.setdefault(pid, set())]
        new_rows, new_rej = process(pid, call["parsed"], slots, grams, card, subjects.get(pid), strict,
                                    call.get("model", "?"), stamp=call.get("at"))
        for row in new_rows:
            N.validate_narrative_row(row)
        filled[pid] |= {r["perspective"] for r in new_rows if not r["spare"]}
        rows += new_rows
        rejects += new_rej
    N.NARRATIVE_SYNTH_PATH.write_text(E.dumps_jsonl(rows), encoding="utf-8")
    N.NARRATIVE_REJECTIONS_PATH.write_text(E.dumps_jsonl(rejects), encoding="utf-8")
    primary = [r for r in rows if not r.get("spare")]
    print(f"recheck: replayed {len(replayable)} judgments | kept {len(primary)} (+{len(rows) - len(primary)} spare) "
          f"| rejected alternatives {len(rejects)}")
    return 0


def _append(path: Path, rows: list[dict]) -> None:
    if rows:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(E.dumps_jsonl(rows))


def _alternatives(value) -> list[dict]:
    """Accept [{"text", "mentions_outcome"}...], ["text"...] or a single string/object."""
    if isinstance(value, (str, dict)):
        value = [value]
    out = []
    for item in value or []:
        if isinstance(item, str):
            out.append({"text": item.strip(), "mentions_outcome": None})
        elif isinstance(item, dict) and isinstance(item.get("text"), str):
            mo = item.get("mentions_outcome")
            out.append({"text": item["text"].strip(), "mentions_outcome": mo if isinstance(mo, bool) else None})
    return out


def process(pid: str, parsed: dict, slots: list[str], source_grams: set, card: dict, subject, strict: bool,
            model: str, stamp: str | None = None) -> tuple[list[dict], list[dict]]:
    """(rows, rejections) for one judgment's LLM output."""
    split = E.split_for_key(pid)
    rows, rejects = [], []
    stamp = stamp or datetime.now().isoformat(timespec="seconds")
    rule = "strict" if strict else "names+generic-exempt"
    for slot in slots:
        detail = N.SYNTH_PERSPECTIVES[slot]
        alternatives = _alternatives(parsed.get(slot))
        if not alternatives:
            rejects.append({"source_judgment": pid, "perspective": slot, "alt": 0, "text": "",
                            "reasons": ["missing"], "leakage_rule": rule, "at": stamp})
            continue
        kept_one = False
        for alt, item in enumerate(alternatives[:2], start=1):
            text = item["text"]
            reasons, info = check_description(text, detail, source_grams, card, strict)
            if reasons:
                rejects.append({"source_judgment": pid, "perspective": slot, "alt": alt, "text": text,
                                "reasons": reasons, **info, "leakage_rule": rule, "at": stamp})
                logger.warning(f"rejected {slot}#{alt} for {pid[:8]}: {reasons} {info.get('ngrams', [])[:3]}")
                continue
            rows.append({
                "id": f"nar-{pid[:8]}-{slot}" + ("" if not kept_one else "-spare"),
                "query": text,
                "relevant": {pid: 2},
                "query_type": "paraphrase",
                "origin": "synthetic_narrative",
                "split": split,
                "status": "confirmed",
                "notes": "label by construction (described from this judgment); text not human-reviewed",
                "perspective": slot,
                "detail": detail,
                "source_judgment": pid,
                "subject": subject,
                "mentions_outcome": item["mentions_outcome"],
                "words": info["words"],
                "alternative": alt,
                "spare": kept_one,
                "exempted_ngrams": info.get("exempted_ngrams", []),
                "leakage_rule": rule,
                "model": model,
                "generated_at": stamp,
            })
            kept_one = True
    return rows, rejects


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sample", type=int, help="Judgments to sample (stratified by case_cards.subject).")
    parser.add_argument("--max-calls", type=int, default=14, help="Hard cap on LLM calls, retries included.")
    parser.add_argument("--sleep", type=float, default=4.5, help="Seconds between calls (>=4 on the free tier).")
    parser.add_argument("--fill-missing", action="store_true",
                        help="One call per judgment whose generated slots were all rejected, for those slots only.")
    parser.add_argument("--strict-leakage", action="store_true", help="No generic-phrase or name exemption.")
    parser.add_argument("--dry-run", action="store_true", help="Print the plan; make no LLM call.")
    parser.add_argument("--only", help="Comma-separated pdf_id prefixes: restrict the plan to these judgments.")
    parser.add_argument("--recheck", action="store_true",
                        help="Re-apply the checks to every stored LLM output (no LLM call) and rewrite the outputs.")
    args = parser.parse_args()
    assert args.sleep >= 4.0, "the free tier needs >= 4s between calls"

    logger.remove()
    logger.add(sys.stderr, level="WARNING")

    corpus = await E.corpus_judgments()
    assert corpus, "no judgments in MongoDB (is it running?)"
    subjects = await subjects_by_judgment()
    sample = choose_sample(list(corpus), subjects, args.sample)

    existing = E.read_jsonl(N.NARRATIVE_SYNTH_PATH) if N.NARRATIVE_SYNTH_PATH.exists() else []
    calls_log = E.read_jsonl(N.NARRATIVE_CALLS_PATH) if N.NARRATIVE_CALLS_PATH.exists() else []
    succeeded = {c["source_judgment"] for c in calls_log if c.get("ok")}
    have_slots: dict[str, set] = {}
    for row in existing:
        if not row.get("spare"):
            have_slots.setdefault(row["source_judgment"], set()).add(row["perspective"])

    if args.recheck:
        return await recheck(corpus, subjects, args.strict_leakage)
    if args.fill_missing:
        plan = [(pid, [s for s in N.SYNTH_PERSPECTIVES if s not in have_slots.get(pid, set())])
                for pid in sample if pid in succeeded]
        plan = [(pid, slots) for pid, slots in plan if slots]
    else:
        plan = [(pid, list(N.SYNTH_PERSPECTIVES)) for pid in sample if pid not in succeeded]
    if args.only:
        prefixes = tuple(p.strip() for p in args.only.split(",") if p.strip())
        plan = [(pid, slots) for pid, slots in plan if pid.startswith(prefixes)]
    print(f"corpus {len(corpus)} | subjects from case_cards: {'yes' if subjects else 'no'} | sample {len(sample)} | "
          f"already generated {len(succeeded & set(sample))} | to call {len(plan)} | cap {args.max_calls}")
    if args.dry_run:
        for pid, slots in plan:
            print(f"  would call for {pid[:8]} {corpus[pid].get('filename', ''):<34} [{subjects.get(pid, '-')}] "
                  f"split={E.split_for_key(pid)} slots={','.join(slots)}")
        print(f"\n  expected LLM calls: {len(plan)} (+ retries on rate limits); "
              f"~{len(plan) * (args.sleep + 8) / 60:.0f} min at one call per {args.sleep + 8:.0f}s")
        return 0

    from app.config import settings
    model = getattr(settings, "GEMINI_MODEL", "?")
    calls = kept = rejected = 0
    for pid, slots in plan:
        if calls >= args.max_calls:
            print(f"stopping: LLM call budget {args.max_calls} reached")
            break
        card, sections, source_grams = await judgment_material(pid)
        prompt = build_prompt(card, sections, slots)

        parsed, backoff = None, 20.0
        for attempt in range(1, 4):
            if calls >= args.max_calls:
                break
            calls += 1
            parsed, limited = await call_llm(prompt)
            _append(N.NARRATIVE_CALLS_PATH, [{"source_judgment": pid, "attempt": attempt, "ok": bool(parsed),
                                              "rate_limited": limited, "slots": slots, "model": model,
                                              "parsed": parsed,
                                              "at": datetime.now().isoformat(timespec="seconds")}])
            await asyncio.sleep(args.sleep)
            if parsed:
                break
            wait = 65.0 if limited else backoff
            logger.warning(f"{pid[:8]}: no JSON on attempt {attempt} (rate limited: {limited}); waiting {wait:.0f}s")
            await asyncio.sleep(wait)
            backoff *= 2
        if not parsed:
            print(f"  {pid[:8]}: FAILED (calls so far {calls}); re-run to resume")
            continue

        rows, rejects = process(pid, parsed, slots, source_grams, card, subjects.get(pid), args.strict_leakage, model)
        for row in rows:
            N.validate_narrative_row(row)
        _append(N.NARRATIVE_SYNTH_PATH, rows)
        _append(N.NARRATIVE_REJECTIONS_PATH, rejects)
        primary = [r for r in rows if not r["spare"]]
        kept += len(primary)
        rejected += len(rejects)
        missing = [s for s in slots if s not in {r["perspective"] for r in primary}]
        print(f"  {pid[:8]} {corpus[pid].get('filename', ''):<34} kept {len(primary)}/{len(slots)} "
              f"(+{len(rows) - len(primary)} spare) rejected {len(rejects)}"
              + (f"  MISSING {','.join(missing)}" if missing else ""))

    print(f"\nLLM calls {calls} | descriptions kept {kept} | alternatives rejected {rejected} "
          f"(see {N.NARRATIVE_REJECTIONS_PATH.relative_to(E.BACKEND_DIR)})")
    return 0


async def calibrate() -> int:
    """Run the checks (no LLM) on the hand-written positives of narrative_baseline_v0.json."""
    logger.remove()
    prefix = await N.full_ids()
    rows = [r for r in N.hand_written_rows(prefix) if r["relevant"]]
    tally = {"strict": 0, "exempt": 0}
    for row in rows:
        pid = E.primary_judgment(row["relevant"])
        card = await load_card(pid)
        sections = await E.judgment_text(pid)
        card_text = " ".join(str(card.get(k) or "") for k in ("headnote", "issues", "holding", "keywords"))
        grams = E.ngrams(E.tokens(" ".join(sections.values()) + " " + card_text), 4)
        verdicts = {}
        for rule in ("strict", "exempt"):
            reasons, info = check_description(row["query"], row["detail"], grams, card, strict=(rule == "strict"))
            reasons = [r for r in reasons if not r.startswith("length")]  # hand-written loose rows are short
            verdicts[rule] = (reasons, info)
            tally[rule] += bool(reasons)
        s, x = verdicts["strict"], verdicts["exempt"]
        print(f"  {row['id']:<16} {row['detail']:<8} strict {'REJECT' if s[0] else 'pass  '} "
              f"exempt {'REJECT' if x[0] else 'pass  '}  {x[1].get('ngrams', [])} {x[1].get('names', [])} "
              f"exempted={x[1].get('exempted_ngrams', [])}")
    print(f"\n  hand-written positives rejected: strict rule {tally['strict']}/{len(rows)}, "
          f"with name+generic exemption {tally['exempt']}/{len(rows)} (length check ignored)")
    return 0


def _self_check() -> None:
    grams = E.ngrams(E.tokens("At the time of the nikah the husband gave land in lieu of dower and the High Court "
                              "decreed the suit of Mst. Pakistan Bibi"), 4)
    hits, exempt = leaked_ngrams("At the time of marriage he handed over land in lieu of dower to her", grams, False)
    assert hits == ["in lieu of dower", "land in lieu of"], hits
    assert exempt == ["generic:at the time of"], exempt
    hits, _ = leaked_ngrams("At the time of marriage", grams, False, strict=True)
    assert hits == ["at the time of"], hits
    hits, exempt = leaked_ngrams("My client Mst. Pakistan Bibi won", grams, exempt_names=True)
    assert hits == [] and "name:mst pakistan bibi" not in exempt  # only a 3-gram: no 4-gram shared
    grams2 = E.ngrams(E.tokens("Mir Saleem Ahmed Khosa filed"), 4)
    assert leaked_ngrams("I am Mir Saleem Ahmed Khosa", grams2, True)[0] == []
    assert leaked_ngrams("I am Mir Saleem Ahmed Khosa", grams2, False)[0] == ["mir saleem ahmed khosa"]
    card = {"appellant": "Federation of Pakistan through Secretary, Ministry of Foreign Affairs",
            "respondent": "Ali Naseem", "case_keys": "['CA-5-Q-2014']", "citations": "['2016 SCMR 900']"}
    assert party_name_tokens(card) == {"ali", "naseem"}, party_name_tokens(card)
    assert case_number_hits("as in Civil Appeal No. 5-Q of 2014", card)
    assert case_number_hits("reported as 2016 SCMR 900", card)
    assert not case_number_hits("I worked there for 5 years and was paid 900 rupees", card)
    long_text = " ".join(["word"] * 60)
    reasons, info = check_description(long_text + " Naseem", "loose", set(), card, False)
    assert reasons == ["party name in a loose description"], reasons
    reasons, _ = check_description(long_text + " Naseem", "detailed", set(), card, False)
    assert reasons == [], reasons
    reasons, _ = check_description("too short", "detailed", set(), card, False)
    assert reasons and reasons[0].startswith("length"), reasons
    alts = _alternatives([{"text": "a", "mentions_outcome": True}, "b"])
    assert [a["text"] for a in alts] == ["a", "b"] and alts[1]["mentions_outcome"] is None
    parsed = {"appellant_lawyer": [{"text": long_text, "mentions_outcome": False},
                                   {"text": long_text + " again", "mentions_outcome": True}],
              "layperson": [{"text": "short", "mentions_outcome": False}]}
    rows, rejects = process("pdf-x", parsed, ["appellant_lawyer", "layperson", "opposing_party"], set(), card,
                            "Service law", False, "m")
    assert [r["id"] for r in rows] == ["nar-pdf-x-appellant_lawyer", "nar-pdf-x-appellant_lawyer-spare"], rows
    assert rows[1]["spare"] and not rows[0]["spare"]
    assert {r["perspective"] for r in rejects} == {"layperson", "opposing_party"}
    for row in rows:
        N.validate_narrative_row(row)
    print("synth_narratives self-check passed")


if __name__ == "__main__":
    if "--self-check" in sys.argv:
        _self_check()
        raise SystemExit(0)
    if "--calibrate" in sys.argv:
        raise SystemExit(asyncio.run(calibrate()))
    raise SystemExit(asyncio.run(main()))
