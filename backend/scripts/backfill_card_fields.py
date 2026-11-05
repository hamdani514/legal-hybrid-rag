"""
Fill case-card fields the card builder left empty, from the judgment's own text.

The result filters (decision, date, judge) can only match what a card records,
so a card with no bench never matches a judge filter. This reads the judgment's
header and final order and fills:

  bench          the judges named in the header (MR. JUSTICE ..., CJ)
  decision_date  a LABELLED date only: "Announced on", "Date of decision",
                 "Date of hearing". Never "judgment dated ...", which is the lower
                 court's decision being appealed.
  outcome        only when the final order states exactly one result
                 ("appeal is dismissed"). Mixed or unclear orders stay unknown:
                 a wrong label would be worse than none.

    cd backend && venv/Scripts/python.exe -m scripts.backfill_card_fields            # report only
    cd backend && venv/Scripts/python.exe -m scripts.backfill_card_fields --apply    # write

Only empty fields are ever filled; nothing the card already says is changed.
Each filled field is marked in `filled_from_text`, so it can be reviewed or undone.
"""

from __future__ import annotations

import asyncio
import collections
import re
import sys
from datetime import datetime, timezone

from app.database import close_db, connect_db, db

MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"], 1)}
DATE = (r"(\d{1,2})\s*[./-]\s*(\d{1,2})\s*[./-]\s*((?:19|20)\d{2})"
        r"|(\d{1,2})(?:st|nd|rd|th)?\s+(january|february|march|april|may|june|july|august|september|october|november|december),?\s+((?:19|20)\d{2})")
LABELLED_DATE = [
    ("decision", re.compile(r"(?:announced(?:\s+in\s+open\s+court)?(?:\s+on)?|date\s+of\s+(?:decision|judgment|announcement)|decided\s+on)\s*[:\-]?\s*(?:" + DATE + ")", re.I)),
    ("hearing", re.compile(r"date\s+of\s+hearing\s*[:\-]?\s*(?:" + DATE + ")", re.I)),
]
JUDGE_LINE = re.compile(r"^\s*(?:MR\.?|MRS\.?|MS\.?|MISS)?\s*JUSTICE\s+([A-Za-z][A-Za-z.'\- ]{3,60}?)\s*(?:,\s*(H?\.?C\.?J|A\.?C\.?J)\.?)?\s*$", re.M | re.I)
OUTCOMES = [
    ("partly_allowed", r"\bpartl?y\s+allowed\b|\ballowed\s+in\s+part\b|\bpartially\s+allowed\b"),
    ("remanded", r"\bremanded\b|\bremitted\s+back\b"),
    # Not "leave granted": that only means the appeal will be heard, not how it ended.
    ("allowed", r"\b(?:appeals?|petitions?)\s+(?:is|are)\s+(?:hereby\s+|accordingly\s+)?allowed\b"),
    ("dismissed", r"\b(?:appeals?|petitions?)\s+(?:is|are)\s+(?:hereby\s+|accordingly\s+)?dismissed\b|\bleave\s+(?:to\s+appeal\s+)?(?:is\s+)?(?:refused|declined)\b"),
    ("disposed", r"\b(?:appeals?|petitions?)\s+(?:is|are|stands?)\s+(?:hereby\s+|accordingly\s+)?disposed\s+of\b"),
]


def _date(match) -> str | None:
    g = match.groups()
    try:
        if g[0]:
            day, month, year = int(g[0]), int(g[1]), int(g[2])
        else:
            day, month, year = int(g[3]), MONTHS[g[4].lower()], int(g[5])
        datetime(year, month, day)
    except (TypeError, ValueError, KeyError):
        return None
    return f"{day:02d}.{month:02d}.{year}"


def bench_from(header: str) -> list[str]:
    judges = []
    for name, title in JUDGE_LINE.findall(header or ""):
        words = [w for w in re.split(r"\s+", name.strip(" .")) if w]
        if not 2 <= len(words) <= 6 or not all(re.fullmatch(r"[A-Za-z][A-Za-z.'\-]*", w) for w in words):
            continue  # OCR noise, not a name
        # ALL-CAPS headers become "Gulzar Ahmed"; names already in normal case keep their spelling.
        pretty = "Justice " + " ".join(w.capitalize() if w.isupper() and not re.fullmatch(r"[A-Z]\.", w) else w for w in words)
        if title:
            pretty += ", " + title.replace(".", "").upper()
        if pretty not in judges:
            judges.append(pretty)
    return judges


def date_from(texts: list[str]) -> tuple[str | None, str | None]:
    for kind, pattern in LABELLED_DATE:
        for text in texts:
            m = pattern.search(text or "")
            if m:
                found = _date(m)
                if found:
                    return found, kind
    return None, None


def outcome_from(final_order: str) -> str | None:
    text = (final_order or "")[-2500:]  # the operative part sits at the end
    hits = {name for name, pattern in OUTCOMES if re.search(pattern, text, re.I)}
    if "partly_allowed" in hits:
        hits -= {"allowed"}
    return hits.pop() if len(hits) == 1 else None


async def run(apply: bool) -> None:
    await connect_db()
    d = db.database
    missing = {"bench": {"$or": [{"bench": {"$exists": False}}, {"bench": None}, {"bench": []}, {"bench": ""}]},
               "decision_date": {"$or": [{"decision_date": {"$exists": False}}, {"decision_date": None}, {"decision_date": ""}]},
               "outcome": {"$or": [{"outcome": {"$exists": False}}, {"outcome": None}, {"outcome": ""}, {"outcome": "unknown"}]}}
    cards = d.case_cards.find({"$or": list(missing.values())}, {"judgment_id": 1, "bench": 1, "decision_date": 1, "outcome": 1})
    stats, samples, updates = collections.Counter(), collections.defaultdict(list), []
    async for card in cards:
        jid = card["judgment_id"]
        sections = {}
        async for node in d.nodes.find({"pdf_id": jid, "section_type": {"$in": ["HEADER_CORAM", "FINAL_ORDER"]}},
                                       {"section_type": 1, "text": 1}):
            sections.setdefault(node["section_type"], []).append(node.get("text") or "")
        header = "\n".join(sections.get("HEADER_CORAM", []))
        final = "\n".join(sections.get("FINAL_ORDER", []))
        fields = {}
        if not card.get("bench"):
            stats["bench missing"] += 1
            bench = bench_from(header)
            if bench:
                fields["bench"] = bench
        if not card.get("decision_date"):
            stats["date missing"] += 1
            found, kind = date_from([final, header])
            if found:
                fields["decision_date"] = found
                stats[f"date from {kind}"] += 1
        if card.get("outcome") in (None, "", "unknown"):
            stats["outcome unknown"] += 1
            outcome = outcome_from(final)
            if outcome:
                fields["outcome"] = outcome
        for k, v in fields.items():
            stats[f"{k} filled"] += 1
            if len(samples[k]) < 4:
                samples[k].append((jid[:8], v))
        if fields:
            updates.append((jid, fields))

    print("Cards with a field to fill:")
    for key in ("bench", "date", "outcome"):
        miss = stats[f"{key} missing" if key != "outcome" else "outcome unknown"]
        got = stats[f"{'decision_date' if key == 'date' else key} filled"]
        print(f"  {key:<8} missing {miss:>4}  can fill {got:>4}")
    print(f"  dates: {stats['date from decision']} labelled as the decision, {stats['date from hearing']} as the hearing")
    for k, rows in samples.items():
        print(f"  e.g. {k}: {rows}")

    if apply and updates:
        now = datetime.now(timezone.utc)
        for jid, fields in updates:
            await d.case_cards.update_one({"judgment_id": jid}, {"$set": {**fields, "filled_from_text": {
                "fields": sorted(fields), "at": now}}})
        print(f"\nwrote {len(updates)} cards")
    elif updates:
        print(f"\n{len(updates)} cards would change. Nothing written; run with --apply to write.")
    await close_db()


if __name__ == "__main__":
    asyncio.run(run("--apply" in sys.argv))
