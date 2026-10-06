"""
Case cards: one structured, grounded summary per judgment, in MongoDB `case_cards`.

Why this exists
---------------
Every judgment's ROOT node today carries a templated summary ("Appeal by X
against Y regarding the legal dispute…") that says nothing about the subject
matter, so nothing in the index tells an election appeal from a trade-mark one
at the judgment level. A case card fixes that: the deterministic caption facts
from app.ingestion.metadata_extractor plus ONE grounded LLM call for subject
(from the fixed SUBJECT_AREAS vocabulary), headnote, issues, holding and
keywords. The card feeds exact match, BM25/dense card retrieval, the contextual
chunk headers and the compare table. Its headnote is meant to replace the
templated root summary later; this module does NOT write to `nodes` — the
integrator decides that.

Grounding
---------
The prompt forbids inventing facts, names, dates or citations and tells the
model to leave unsupported fields empty. Because a prompt is not a guarantee,
a cheap post-check follows: every capitalised word and every date in the
headnote, holding and issues must occur in the source text; a sentence that
fails is dropped and logged. Metadata fields are never touched by the LLM.

The card wave
-------------
Bulk ingest makes judgments searchable WITHOUT cards; `--all` is the resumable
wave that fills them in afterwards (see card_wave below): only searchable,
non-failed judgments with a missing / metadata_only / outdated card; bounded
concurrency and backoff through the bulk LLMGuard; each saved card refreshes
that judgment's FTS row and card vector and moves it from "searchable" to
"complete"; a daily-quota 429 stops the wave cleanly for the next run. A card
whose LLM call failed is stored as metadata_only WITH card_error saying why.

Run:
    python -m app.ingestion.case_card --all                  # the wave; re-run daily until done
    python -m app.ingestion.case_card --all --limit 200      # at most 200 judgments today
    python -m app.ingestion.case_card --all --force          # rebuild every card
    python -m app.ingestion.case_card --pdf-id <id>          # one judgment
    python -m app.ingestion.case_card --show <judgment_id>
"""

import argparse
import asyncio
import contextvars
import json
import re
from datetime import datetime, timezone

from loguru import logger

from app.config import settings
from app.ingestion.metadata_extractor import (
    METADATA_VERSION,
    _clean,
    _flat,
    caption_text,
    extract_from_sources,
    load_sources,
)
from app.ingestion.bulk.llm_guard import DAILY_QUOTA_RE, RATE_LIMIT_RE
from app.retrieval.contracts import INDEX_REQUIRED_FOR_SEARCH, SUBJECT_AREAS

CARD_VERSION = 1
COLLECTION = "case_cards"

# Character budgets per section. ~13k characters ≈ 3.5k tokens: enough to see
# the facts, the question and the ratio, small enough to stay cheap at 3,000+
# judgments. ANALYSIS_RATIO keeps its head (the reasoning) and tail (the ratio).
SECTION_BUDGET = {
    "CAPTION": 2000,
    "FACTS": 3500,
    "LEGAL_ISSUES": 1000,
    "ANALYSIS_RATIO": 5000,
    "FINAL_ORDER": 1500,
}
MAX_OUTPUT_TOKENS = int(getattr(settings, "CASE_CARD_MAX_TOKENS", 900))
CALL_PAUSE_S = float(getattr(settings, "CASE_CARD_CALL_PAUSE_S", 1.0))
MAX_LLM_CALLS = int(getattr(settings, "CASE_CARD_MAX_LLM_CALLS", 16))

SYSTEM_PROMPT = f"""You write case cards for judgments of the Supreme Court of Pakistan, for lawyers.
You are given excerpts of ONE judgment. Return ONLY a JSON object with these keys:

  "subject":  exactly one of: {", ".join(SUBJECT_AREAS)}.
              Pick the area of law the dispute is about. Use "Other" if none fits.
  "headnote": 2-3 factual sentences: who sought what against whom, what the court below did,
              and what this Court decided. Plain, specific, no rhetoric.
  "issues":   list of the legal question(s) the Court decided, each one sentence.
  "holding":  1-2 sentences stating the Court's decision and the reason for it.
  "keywords": up to 8 short legal terms that a lawyer would search for this case.

STRICT RULES:
- Use ONLY the judgment text provided. Do NOT invent or infer facts, names, dates, numbers,
  courts, statutes or citations that are not written in the text.
- Every name, date and statute you mention must appear verbatim in the text.
- If the text does not support a field, leave it empty ("" or []). Empty is better than a guess.
- No markdown, no commentary, JSON only."""


# ── LLM call budget ──────────────────────────────────────────────────────────

class _Budget:
    """Hard cap on LLM calls for one process; the Gemini quota is shared."""

    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.used = 0

    def take(self) -> bool:
        if self.used >= self.limit:
            return False
        self.used += 1
        return True


_budget = _Budget(MAX_LLM_CALLS)


# ── Prompt ───────────────────────────────────────────────────────────────────

def _trim(text: str, budget: int, keep_tail: int = 0) -> str:
    text = _flat(text)
    if len(text) <= budget:
        return text
    if keep_tail:
        return text[: budget - keep_tail] + " […] " + text[-keep_tail:]
    return text[:budget] + " […]"


def build_prompt(raw: str | None, sections: dict[str, str]) -> str:
    caption, _ = caption_text(raw, sections)
    parts = [("HEADER", _trim(caption, SECTION_BUDGET["CAPTION"]))]
    for st, tail in (("FACTS", 0), ("LEGAL_ISSUES", 0), ("ANALYSIS_RATIO", 2000), ("FINAL_ORDER", 0)):
        text = sections.get(st) or ""
        if st == "FINAL_ORDER":
            # Often a signature block; the operative paragraph closes the raw text.
            text = text[-SECTION_BUDGET[st]:]
            if raw and len(_flat(text)) < 200:
                text = _clean(raw)[-SECTION_BUDGET[st]:]
        if text.strip():
            parts.append((st, _trim(text, SECTION_BUDGET[st], tail)))
    body = "\n\n".join(f"=== {name} ===\n{text}" for name, text in parts)
    return f"JUDGMENT EXCERPTS:\n\n{body}\n\nReturn the JSON case card."


# ── Groundedness check ───────────────────────────────────────────────────────
# Words that may legitimately be capitalised without appearing in the text
# (sentence starts, generic legal nouns). REVALIDATE on the full corpus.
_GENERIC = {
    "the", "a", "an", "this", "that", "these", "it", "its", "in", "on", "of", "for", "and", "but", "or",
    "court", "supreme", "high", "appeal", "appeals", "appellant", "appellants", "respondent", "respondents",
    "petition", "petitioner", "petitioners", "tribunal", "judgment", "order", "pakistan", "constitution",
    "article", "section", "act", "rules", "ordinance", "civil", "criminal", "however", "whether", "while",
    "after", "since", "because", "although", "thus", "hence", "accordingly", "held", "holding", "having",
    "consequently", "therefore", "further", "also", "where", "when", "which", "who", "whom",
}
_CAP_WORD = re.compile(r"\b[A-Z][a-zA-Z'\-]{2,}\b")
_DATE_IN = re.compile(r"\b\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b|\b(?:19|20)\d{2}\b")


def _sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?])\s+(?=[A-Z])", text.strip()) if s]


def _unsupported(sentence: str, source_lower: str, source_flat: str) -> list[str]:
    bad = []
    for word in _CAP_WORD.findall(sentence):
        word = re.sub(r"['’]s$|['’]$", "", word)  # "Tribunal's" -> "Tribunal"
        if word.lower() in _GENERIC:
            continue
        if word.lower() not in source_lower:
            bad.append(word)
    for d in _DATE_IN.findall(sentence):
        if d not in source_flat:
            bad.append(d)
    return bad


def ground(card: dict, source: str, judgment_id: str) -> dict:
    """Drop sentences whose names or dates are not in the source. Returns a report."""
    source_flat = _flat(source)
    source_lower = source_flat.lower()
    report = {"checked": 0, "dropped": []}

    for field in ("headnote", "holding"):
        kept = []
        for s in _sentences(card.get(field) or ""):
            report["checked"] += 1
            bad = _unsupported(s, source_lower, source_flat)
            if bad:
                logger.warning(f"{judgment_id}: dropped {field} sentence, unsupported {bad}: {s[:120]}")
                report["dropped"].append({"field": field, "tokens": bad, "sentence": s})
            else:
                kept.append(s)
        card[field] = " ".join(kept)

    kept_issues = []
    for issue in card.get("issues") or []:
        report["checked"] += 1
        bad = _unsupported(issue, source_lower, source_flat)
        if bad:
            logger.warning(f"{judgment_id}: dropped issue, unsupported {bad}: {issue[:120]}")
            report["dropped"].append({"field": "issues", "tokens": bad, "sentence": issue})
        else:
            kept_issues.append(issue)
    card["issues"] = kept_issues
    return report


def _normalise_llm(parsed: dict) -> dict:
    subject = str(parsed.get("subject") or "").strip()
    by_lower = {s.lower(): s for s in SUBJECT_AREAS}
    if subject.lower() not in by_lower:
        if subject:
            logger.warning(f"subject {subject!r} not in SUBJECT_AREAS; using 'Other'")
        subject = "Other"
    else:
        subject = by_lower[subject.lower()]

    def as_list(value) -> list[str]:
        if isinstance(value, str):
            value = [value] if value.strip() else []
        return [str(v).strip() for v in (value or []) if str(v).strip()]

    return {
        "subject": subject,
        "headnote": str(parsed.get("headnote") or "").strip(),
        "issues": as_list(parsed.get("issues")),
        "holding": str(parsed.get("holding") or "").strip(),
        "keywords": as_list(parsed.get("keywords"))[:8],
    }


# ── Rate-limit detection ─────────────────────────────────────────────────────
# llm_responder._complete swallows every exception and returns ERROR_RESPONSE,
# so a 429 looks exactly like bad JSON from the outside. Like the bulk parser
# guard (app/ingestion/bulk/llm_guard.py), we listen to the log record it emits
# and attribute it to the card call through a ContextVar, so concurrent card
# calls never see each other's errors. If _complete is later changed to raise
# (or to go through a shared limiter that raises), the exception text is
# classified the same way.

_rl_watch: contextvars.ContextVar[list | None] = contextvars.ContextVar("card_rl_watch", default=None)
_rl_sink_installed = False


def _install_rl_sink() -> None:
    global _rl_sink_installed
    if _rl_sink_installed:
        return

    def _sink(message) -> None:
        rec = message.record
        if rec["level"].no < 30 or not RATE_LIMIT_RE.search(rec["message"]):
            return
        hits = _rl_watch.get()
        if hits is not None:
            hits.append(rec["message"][:300])

    logger.add(_sink, level="WARNING",
               filter=lambda r: (r["name"] or "").startswith(("app.retrieval.llm_responder", "app.llm")))
    _rl_sink_installed = True


def _classify_failure(text: str) -> str:
    """'daily_quota' | 'rate_limited' for a rate-limit signature, else ''."""
    if not RATE_LIMIT_RE.search(text or ""):
        return ""
    return "daily_quota" if DAILY_QUOTA_RE.search(text) else "rate_limited"


async def _llm_card(prompt: str, judgment_id: str, attempts: int = 2) -> tuple[dict | None, str]:
    """Up to `attempts` grounded calls. Returns (parsed card fields, failure).

    failure is "" on success, else one of "rate_limited: …", "daily_quota: …",
    "budget", "bad_json", "error: …". A rate limit is never retried here with a
    short sleep — the caller (the card wave) owns backoff, so it can pause every
    concurrent call at once and stop cleanly when the daily quota is gone.
    """
    from app.retrieval.comparator import _parse
    from app.retrieval.llm_responder import ERROR_RESPONSE, _complete

    _install_rl_sink()
    failure = "error: no attempt made"
    for attempt in range(attempts):
        if not _budget.take():
            logger.error(f"{judgment_id}: LLM budget of {_budget.limit} calls exhausted")
            return None, "budget"
        if _budget.used > 1:
            await asyncio.sleep(CALL_PAUSE_S)
        hits: list[str] = []
        token = _rl_watch.set(hits)
        try:
            response = await _complete(SYSTEM_PROMPT, prompt, MAX_OUTPUT_TOKENS)
        except Exception as e:  # noqa: BLE001 - a raising limiter is a failure, not a crash
            response, hits = ERROR_RESPONSE, hits + [f"{type(e).__name__}: {e}"]
        finally:
            _rl_watch.reset(token)
        parsed = _parse(response) if response != ERROR_RESPONSE else None
        if parsed:
            return parsed, ""
        evidence = " | ".join(hits) or (response if response != ERROR_RESPONSE else "")
        kind = _classify_failure(evidence)
        if kind:
            logger.warning(f"{judgment_id}: card call {kind}: {evidence[:160]}")
            return None, f"{kind}: {evidence[:200]}"
        failure = "bad_json" if response != ERROR_RESPONSE else f"error: {evidence[:200] or 'LLM error'}"
        logger.warning(f"{judgment_id}: LLM attempt {attempt + 1} failed ({failure[:80]})")
        if attempt + 1 < attempts:
            await asyncio.sleep(5 * (attempt + 1))
    return None, failure


# ── Build / store ────────────────────────────────────────────────────────────

async def build_card(judgment_id: str, attempts: int = 2) -> dict:
    """Metadata + one grounded LLM call -> CaseCard. Does not write anything.

    A card whose LLM call failed is returned with card_status "metadata_only"
    and card_error saying why ("rate_limited: …", "daily_quota: …", "bad_json",
    …), so a degraded card is visible in MongoDB rather than silent.
    """
    src = await load_sources(judgment_id)
    raw, sections = src["raw"], src["sections"]
    card = extract_from_sources(judgment_id, raw, sections)
    card.update({"subject": "Other", "headnote": "", "issues": [], "holding": "", "keywords": []})

    parsed, failure = await _llm_card(build_prompt(raw, sections), judgment_id, attempts=attempts)
    if parsed is None:
        card["card_status"] = "metadata_only"
        card["card_model"] = ""
        card["card_error"] = failure
    else:
        card.update(_normalise_llm(parsed))
        # Pre-check LLM output kept for audit: shows what grounding removed.
        card["llm_raw"] = {k: card[k] for k in ("headnote", "issues", "holding")}
        source = (raw or "") + "\n" + "\n".join(sections.values())
        card["grounding"] = ground(card, source, judgment_id)
        card["card_status"] = "complete"
        card["card_model"] = getattr(settings, "GEMINI_MODEL", "") or "gemini-2.5-flash-lite"

    card["filename"] = src["filename"]
    card["metadata_version"] = METADATA_VERSION
    card["card_version"] = CARD_VERSION
    card["built_at"] = datetime.now(timezone.utc)
    return card


async def _collection():
    from app.database import connect_db, db

    if not db.is_connected:
        await connect_db()
    assert db.is_connected, "MongoDB not connected (MONGO_URL)"
    coll = db.database[COLLECTION]
    await coll.create_index("judgment_id", unique=True)
    await coll.create_index("case_keys")
    return coll


async def save_card(card: dict) -> None:
    coll = await _collection()
    await coll.replace_one({"judgment_id": card["judgment_id"]}, card, upsert=True)


def _is_current(existing: dict | None) -> bool:
    return bool(existing) and existing.get("card_version") == CARD_VERSION \
        and existing.get("metadata_version") == METADATA_VERSION \
        and existing.get("card_status") == "complete"


# ── The card wave ────────────────────────────────────────────────────────────
# Bulk ingest makes judgments searchable without cards (no LLM after the parse),
# so cards are filled in afterwards by this wave. Why it is shaped like this:
#
# * candidates: only documents whose required stores (tree, dense, fts) are all
#   recorded in index_status and that are not failed — a card for a judgment
#   that is not searchable, or whose parse failed, is a wasted Gemini call; run
#   `python -m app.indexing.check --repair` first so legacy documents have
#   index_status. Of those, only judgments with no card, a metadata_only card,
#   or an outdated card version.
# * concurrency + backoff through LLMGuard (the bulk parser's guard): one
#   semaphore, exponential backoff with jitter, and a shared cooldown so a 429
#   pauses every in-flight card call, not just the one that saw it.
# * daily quota: a 429 naming a per-day quota (or `--stop-after` consecutive
#   judgments that ran out of retries) stops the wave cleanly; nothing is lost,
#   the next run picks up exactly the judgments still missing a card.
# * after each saved card: index_judgment(build_card=False) refreshes that
#   judgment's FTS card row and card vector and records index_status (card,
#   card_vector), which moves the document from "searchable" to "complete".

async def wave_candidates(force: bool = False, pdf_ids: list[str] | None = None) -> list[str]:
    from app.database import db

    coll = await _collection()
    q: dict = {f"index_status.{s}": True for s in INDEX_REQUIRED_FOR_SEARCH}
    q["status"] = {"$ne": "failed"}
    if pdf_ids:
        q["pdf_id"] = {"$in": pdf_ids}
    out = []
    async for d in db.documents.find(q, {"pdf_id": 1}).sort([("upload_date", 1), ("pdf_id", 1)]):
        existing = await coll.find_one({"judgment_id": d["pdf_id"]},
                                       {"card_version": 1, "metadata_version": 1, "card_status": 1})
        if force or not _is_current(existing):
            out.append(d["pdf_id"])
    return out


async def card_wave(force: bool = False, limit: int | None = None, concurrency: int = 1,
                    max_attempts: int = 4, base_delay: float = 20.0, stop_after: int = 3,
                    pdf_ids: list[str] | None = None) -> dict:
    """Build missing cards, refresh their indexes, stop cleanly on quota exhaustion."""
    from app.indexing.sync import index_judgment
    from app.ingestion.bulk.llm_guard import LLMGuard

    coll = await _collection()
    todo = await wave_candidates(force=force, pdf_ids=pdf_ids)
    if limit:
        todo = todo[:limit]
    guard = LLMGuard(concurrency=concurrency, max_attempts=max_attempts, base_delay=base_delay,
                     max_delay=max(base_delay * 8, 60.0))
    stop = asyncio.Event()
    stats = {"candidates": len(todo), "complete": 0, "metadata_only": 0, "skipped": 0,
             "retries": 0, "stopped": "", "llm_calls_before": _budget.used}
    consecutive_give_ups = 0

    async def one(jid: str) -> None:
        nonlocal consecutive_give_ups
        card = None
        for attempt in range(max_attempts):
            await guard.wait_cooldown()
            if stop.is_set():
                stats["skipped"] += 1
                return
            async with guard.sem:
                if stop.is_set():
                    stats["skipped"] += 1
                    return
                card = await build_card(jid, attempts=1)
            err = card.get("card_error", "")
            if card["card_status"] == "complete":
                consecutive_give_ups = 0
                break
            if err.startswith("daily_quota") or err == "budget":
                stats["stopped"] = "daily quota exhausted" if err.startswith("daily") else "LLM call budget reached"
                stop.set()
                break
            if err.startswith("rate_limited") and attempt + 1 < max_attempts:
                delay = guard.backoff_delay(attempt)
                guard.open_cooldown(delay)
                stats["retries"] += 1
                logger.warning(f"{jid}: rate limited; retry {attempt + 2}/{max_attempts} in {delay:.0f}s")
                continue
            if err.startswith(("bad_json", "error")) and attempt == 0:
                stats["retries"] += 1
                continue  # one more try for a malformed answer
            break
        if card is None:
            stats["skipped"] += 1
            return

        existing = await coll.find_one({"judgment_id": jid}, {"card_status": 1})
        keep_existing = bool(existing) and existing.get("card_status") == "complete"             and card["card_status"] != "complete"   # never replace a complete card with a degraded one
        if not keep_existing:
            await save_card(card)
        # FTS card row + card vector + index_status (card, card_vector, last_error).
        await index_judgment(jid, build_card=False)
        if card["card_status"] == "complete":
            stats["complete"] += 1
            logger.info(f"{jid}: {card['case_display']} | {card['subject']} | complete")
            # This card was the last missing store: the judgment is complete, so
            # its local PDF/text copy can go (only if Drive holds the original).
            from app.indexing.sync import prune_local_copies

            await prune_local_copies(jid)
        else:
            stats["metadata_only"] += 1
            if card.get("card_error", "").startswith("rate_limited") and not stop.is_set():
                consecutive_give_ups += 1
                if consecutive_give_ups >= stop_after:
                    stats["stopped"] = (f"{consecutive_give_ups} judgments in a row still rate-limited "
                                        f"after {max_attempts} attempts; treating the quota as exhausted")
                    stop.set()

    await asyncio.gather(*(one(j) for j in todo))
    stats["llm_calls"] = _budget.used - stats.pop("llm_calls_before")
    stats["remaining"] = len(await wave_candidates(pdf_ids=pdf_ids))
    return stats


async def build_all(force: bool = False) -> dict:
    """Backwards-compatible name for the card wave."""
    return await card_wave(force=force)


def _print_card(card: dict) -> None:
    show = {k: v for k, v in card.items() if k not in ("_id", "case_refs")}
    print(json.dumps(show, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build grounded case cards into MongoDB `case_cards`.")
    parser.add_argument("--all", action="store_true", help="run the card wave over every eligible judgment")
    parser.add_argument("--force", action="store_true", help="rebuild even current cards")
    parser.add_argument("--pdf-id", action="append", help="restrict the wave to these judgments")
    parser.add_argument("--limit", type=int, default=None, help="at most N judgments this run")
    parser.add_argument("--concurrency", type=int, default=1, help="parallel card calls (free tier: 1)")
    parser.add_argument("--max-attempts", type=int, default=4, help="per judgment, on rate limits")
    parser.add_argument("--backoff-base", type=float, default=20.0, help="seconds; doubles per retry")
    parser.add_argument("--max-calls", type=int, default=None, help="hard cap on LLM calls this run")
    parser.add_argument("--show", metavar="JUDGMENT_ID")
    args = parser.parse_args()

    # Offline checks: subject vocabulary, groundedness filter, 429 classification.
    norm = _normalise_llm({"subject": "election law", "keywords": [str(i) for i in range(12)], "issues": "x"})
    assert norm["subject"] == "Election law" and len(norm["keywords"]) == 8 and norm["issues"] == ["x"]
    assert _normalise_llm({"subject": "Space law"})["subject"] == "Other"
    probe = {"headnote": "Mir Saleem Ahmed Khosa lost the election. Imran Khan filed it on 01.01.2015.",
             "holding": "", "issues": []}
    rep = ground(probe, "Mir Saleem Ahmed Khosa appellant election 2013", "selftest")
    assert probe["headnote"] == "Mir Saleem Ahmed Khosa lost the election.", probe["headnote"]
    assert len(rep["dropped"]) == 1
    assert _unsupported("It upheld the Tribunal's judgment.", "the tribunal held", "the tribunal held") == []
    assert _classify_failure("Gemini API call failed via m: 429 RESOURCE_EXHAUSTED") == "rate_limited"
    assert _classify_failure("429 quotaId: GenerateRequestsPerDayPerProjectPerModel-FreeTier") == "daily_quota"
    assert _classify_failure("Expecting value: line 1 column 1") == ""
    if args.max_calls is not None:
        _budget.limit = args.max_calls

    async def main() -> None:
        if args.show:
            coll = await _collection()
            card = await coll.find_one({"judgment_id": args.show})
            assert card, f"no card for {args.show}; run --all first"
            _print_card(card)
            return
        if args.all or args.pdf_id:
            from app.database import db

            print(f"card wave on db={db.database.name if db.database is not None else '?'} "
                  f"(call budget {_budget.limit})")
            stats = await card_wave(force=args.force, limit=args.limit, concurrency=args.concurrency,
                                    max_attempts=args.max_attempts, base_delay=args.backoff_base,
                                    pdf_ids=args.pdf_id)
            print(stats)
            if stats["stopped"]:
                print(f"STOPPED: {stats['stopped']}. Re-run tomorrow; finished cards are kept and "
                      f"the {stats['remaining']} remaining judgments are picked up automatically.")
            coll = await _collection()
            cards = await coll.find({}).to_list(None)
            assert all(c["subject"] in SUBJECT_AREAS for c in cards), "subject outside SUBJECT_AREAS"
            assert _budget.used <= _budget.limit
            print(f"cards: {len(cards)}  complete: {sum(c.get('card_status') == 'complete' for c in cards)}  "
                  f"llm calls this run: {stats['llm_calls']}  still missing: {stats['remaining']}")

    asyncio.run(main())
