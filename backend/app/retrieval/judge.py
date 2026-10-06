"""
Listwise LLM judge over the top reranked judgments (stage J of precision v2).

Why an LLM judge after the cross-encoder
----------------------------------------
The cross-encoder (MiniLM, MS MARCO) reads one passage at a time and was trained
on web questions. It is good at "does this passage answer this question" and
bad at the queries this product promises most: plain-English paraphrases with
no shared vocabulary ("a widow fought her husband's family over land given to
her as marriage payment" -> a dower case). On dev those are exactly the queries
the 0.20 relevance floor refuses. An LLM given each candidate's case card
(headnote, issues, holding) plus its best passage can recognise that the facts
match, and can also say when NONE of the candidates fits — which is the other
half of abstention.

Design, and the bias it guards against
--------------------------------------
* Listwise: one call ranks all <=10 candidates together, so the cost is one
  request per search (the Gemini free tier allows 15/min for the whole project).
* Position bias: LLMs over-prefer the first listed item. Candidates are shown
  in an order shuffled with a seed derived from the query, so the bias is not
  aligned with the reranker's order and the same query is judged the same way
  twice. Candidates get short labels (C1..Cn), not uuids, so the model cannot
  garble ids; labels are mapped back afterwards.
* Never trusted blindly: unknown labels are dropped, labels the model omitted
  are appended in reranker order, a missing relevant flag counts as "not
  relevant", and a response with no usable ranking AND no usable relevant map
  is rejected as garbage.
* Never blocks: the call runs under asyncio.wait_for(JUDGE_TIMEOUT, default
  6s). Timeout, error sentinel, unparsable output or any exception -> used=False
  and the caller keeps the reranker order. judge() never raises.
* Temperature: llm_responder._complete's fixed 0.1.

Off unless USE_LLM_JUDGE (checked by app.retrieval.pipeline_v2).
"""

import asyncio
import json
import random
import re
import sys
import time
import zlib
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from loguru import logger

from app.config import settings

DEFAULT_TIMEOUT = 6.0
MAX_TOKENS = 800
PASSAGE_CHARS = 700
HEADNOTE_CHARS = 600
CARD_FIELDS = ("case_display", "subject", "headnote", "issues", "holding")

SYSTEM_PROMPT = """You are a senior Pakistani lawyer screening search results.
A colleague searched an archive of Supreme Court of Pakistan judgments. You get
the search query and up to ten candidate judgments, each labelled C1, C2, ...
with its case card and one passage. Candidates are listed in RANDOM order.

Decide, for each candidate, whether it is RELEVANT: the judgment actually
decides, or substantially deals with, the legal question or the factual
situation the query describes. Sharing a word, a court, a province or a general
area of law is NOT enough. If the query is not about anything these judgments
decide, mark every candidate false — that is a correct and useful answer.

Return ONE JSON object and nothing else:
{"ranking": ["C3", "C1", ...],          every label, most relevant first
 "relevant": {"C1": true, "C2": false, ...},
 "reasons": {"C1": "one short line", ...}}"""


def judge_timeout() -> float:
    return float(getattr(settings, "JUDGE_TIMEOUT", DEFAULT_TIMEOUT) or DEFAULT_TIMEOUT)


# ── case cards ───────────────────────────────────────────────────────────────

_card_cache: dict[str, dict] = {}


async def load_cards(judgment_ids: list[str]) -> dict[str, dict]:
    """Case cards by judgment id, cached in-process. Missing cards are simply absent."""
    wanted = [j for j in judgment_ids if j not in _card_cache]
    if wanted:
        try:
            from app.database import connect_db, db

            if db.database is None:
                await connect_db()
            cursor = db.database.case_cards.find(
                {"judgment_id": {"$in": wanted}}, {"_id": 0, "judgment_id": 1, **{f: 1 for f in CARD_FIELDS}})
            async for card in cursor:
                _card_cache[card["judgment_id"]] = card
        except Exception as e:
            logger.warning(f"judge could not load case cards: {e}")
    return {j: _card_cache[j] for j in judgment_ids if j in _card_cache}


# ── prompt ───────────────────────────────────────────────────────────────────

def _trim(text: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0] + " ..."


def _as_list(value) -> list[str]:
    if isinstance(value, list):
        return [str(v) for v in value if v]
    return [str(value)] if value else []


def candidate_block(label: str, card: dict | None, passage: str, heading: str = "") -> str:
    card = card or {}
    lines = [f"[{label}] {card.get('case_display') or _trim(heading, 120) or 'Untitled judgment'}"]
    if card.get("subject"):
        lines.append(f"Subject: {card['subject']}")
    if card.get("headnote"):
        lines.append(f"Headnote: {_trim(card['headnote'], HEADNOTE_CHARS)}")
    issues = _as_list(card.get("issues"))
    if issues:
        lines.append("Issues: " + "; ".join(_trim(i, 200) for i in issues[:3]))
    if card.get("holding"):
        lines.append(f"Holding: {_trim(card['holding'], 300)}")
    if passage:
        lines.append(f"Passage: {_trim(passage, PASSAGE_CHARS)}")
    return "\n".join(lines)


def build_prompt(query: str, ids: list[str], cards: dict[str, dict], passages: dict[str, str],
                 headings: dict[str, str] | None = None) -> tuple[str, dict[str, str]]:
    """The user prompt and the label -> judgment_id map (order shuffled, seeded by the query)."""
    headings = headings or {}
    shuffled = list(ids)
    random.Random(zlib.crc32(query.strip().lower().encode("utf-8"))).shuffle(shuffled)
    labels = {f"C{i + 1}": jid for i, jid in enumerate(shuffled)}
    blocks = [candidate_block(label, cards.get(jid), passages.get(jid, ""), headings.get(jid, ""))
              for label, jid in labels.items()]
    user = f"QUERY: {query.strip()}\n\nCANDIDATES:\n\n" + "\n\n".join(blocks) + "\n\nReturn the JSON object."
    return user, labels


# ── parsing and validation ──────────────────────────────────────────────────

_FENCE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def _parse_json(content: str) -> dict | None:
    from app.retrieval.llm_responder import ERROR_RESPONSE

    if not content or content == ERROR_RESPONSE:
        return None
    text = content.strip()
    fenced = _FENCE.search(text)
    if fenced:
        text = fenced.group(1).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        parsed = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _truthy(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("true", "yes", "1", "relevant")


def validate(data: dict | None, labels: dict[str, str], fallback_order: list[str]) -> dict | None:
    """Map a parsed response back to judgment ids, or None if it is unusable."""
    if not data:
        return None
    norm = lambda label: str(label).strip().upper().strip("[]")  # noqa: E731
    raw_ranking = data.get("ranking") if isinstance(data.get("ranking"), list) else []
    raw_relevant = data.get("relevant") if isinstance(data.get("relevant"), dict) else {}
    raw_reasons = data.get("reasons") if isinstance(data.get("reasons"), dict) else {}
    ranking: list[str] = []
    for label in raw_ranking:
        jid = labels.get(norm(label))
        if jid and jid not in ranking:      # unknown labels dropped, duplicates ignored
            ranking.append(jid)
    relevant = {labels[norm(k)]: _truthy(v) for k, v in raw_relevant.items() if norm(k) in labels}
    if not ranking and not relevant:
        return None
    ranking += [jid for jid in fallback_order if jid not in ranking]   # missing -> reranker order
    relevant = {jid: relevant.get(jid, False) for jid in fallback_order}
    reasons = {labels[norm(k)]: _trim(v, 200) for k, v in raw_reasons.items() if norm(k) in labels and v}
    return {"ranking": ranking, "relevant": relevant, "reasons": reasons}


# ── entry point ──────────────────────────────────────────────────────────────

async def _call_llm(system_prompt: str, user_prompt: str, max_tokens: int) -> str:
    """The single seam to the LLM, so tests can replace it."""
    from app.retrieval.llm_responder import _complete

    return await _complete(system_prompt, user_prompt, max_tokens)


def _fallback(order: list[str], error: str, started: float) -> dict:
    return {"used": False, "ranking": list(order), "relevant": {}, "reasons": {}, "error": error,
            "latency_ms": (time.perf_counter() - started) * 1000}


async def judge(query: str, rows: list[dict], evidence: dict[str, list[dict]] | None = None,
                timeout: float | None = None) -> dict:
    """Judge the reranked shortlist. Never raises, never exceeds `timeout` (+ card lookup).

    Args:
        query: The query as typed.
        rows: The shortlist in reranker order, each with ``judgment_id`` (and
            optionally ``heading``). The caller caps it at JUDGE_TOP_N.
        evidence: judgment_id -> passages; the best-scored passage is shown.
        timeout: Seconds for the LLM call; defaults to JUDGE_TIMEOUT.

    Returns:
        {"used", "ranking" (judgment ids), "relevant" {id: bool}, "reasons"
        {id: str}, "error", "latency_ms"}. used=False means "keep the reranker
        order"; ranking is then that order unchanged.
    """
    started = time.perf_counter()
    order = [r["judgment_id"] for r in rows if r.get("judgment_id")]
    if not order:
        return _fallback(order, "no candidates", started)
    try:
        evidence = evidence or {}
        passages = {}
        for jid in order:
            scored = sorted(evidence.get(jid) or [], key=lambda p: -(p.get("scores") or {}).get("rerank", -1e9))
            chunk = next((p for p in scored if p.get("mongo_doc_id")), scored[0] if scored else None)
            passages[jid] = (chunk or {}).get("text", "")
        cards = await asyncio.wait_for(load_cards(order), timeout=2.0)
        user, labels = build_prompt(query, order, cards, passages,
                                    {r["judgment_id"]: r.get("heading", "") for r in rows})
        content = await asyncio.wait_for(_call_llm(SYSTEM_PROMPT, user, MAX_TOKENS),
                                         timeout=judge_timeout() if timeout is None else timeout)
    except asyncio.TimeoutError:
        logger.warning("LLM judge timed out; keeping reranker order")
        return _fallback(order, "timeout", started)
    except Exception as e:
        logger.warning(f"LLM judge failed ({e}); keeping reranker order")
        return _fallback(order, f"error: {e}", started)

    try:
        verdict = validate(_parse_json(content), labels, order)
    except Exception as e:
        verdict = None
        logger.warning(f"LLM judge output could not be validated ({e})")
    if verdict is None:
        from app.retrieval.llm_responder import ERROR_RESPONSE

        # _complete swallows provider errors (429, quota, network) and returns
        # its sentinel; keep that distinct from a model that answered badly.
        kind = "llm_error" if content == ERROR_RESPONSE else "garbage"
        logger.warning(f"LLM judge {kind}; keeping reranker order: {str(content)[:120]!r}")
        return _fallback(order, kind, started)
    verdict.update(used=True, error="", latency_ms=(time.perf_counter() - started) * 1000)
    return verdict


if __name__ == "__main__":
    logger.remove()
    rows = [{"judgment_id": j, "heading": f"Case {j}"} for j in ("A", "B", "C")]
    evidence = {"A": [{"text": "passage A", "mongo_doc_id": "n", "scores": {"rerank": 1.0}}]}
    _card_cache.update({j: {"judgment_id": j, "case_display": f"C.A. {j}"} for j in ("A", "B", "C")})
    user, labels = build_prompt("q", ["A", "B", "C"], _card_cache, {"A": "passage A"})
    assert sorted(labels.values()) == ["A", "B", "C"] and labels == build_prompt("q", ["A", "B", "C"], {}, {})[1]
    inverse = {v: k for k, v in labels.items()}

    async def fake(response=None, delay=0.0, exc=None):
        async def call(*_):
            if delay:
                await asyncio.sleep(delay)
            if exc:
                raise exc
            return response
        return call

    async def main() -> None:
        global _call_llm
        original = _call_llm

        # A hung judge returns within the timeout, in reranker order.
        _call_llm = await fake(delay=60)
        t0 = time.perf_counter()
        out = await judge("q", rows, evidence, timeout=0.5)
        took = time.perf_counter() - t0
        assert not out["used"] and out["ranking"] == ["A", "B", "C"] and out["error"] == "timeout"
        assert took < 1.5, took
        print(f"OK: hung judge -> fallback to reranker order in {took:.2f}s")

        # Empty / garbage / error sentinel / exception -> fallback.
        from app.retrieval.llm_responder import ERROR_RESPONSE
        for bad in ("", "not json at all", ERROR_RESPONSE, '{"foo": 1}', "[1, 2]", '{"ranking": ["C9"]}'):
            _call_llm = await fake(bad)
            out = await judge("q", rows, evidence)
            assert not out["used"] and out["ranking"] == ["A", "B", "C"], (bad, out)
        _call_llm = await fake(exc=RuntimeError("boom"))
        out = await judge("q", rows, evidence)
        assert not out["used"] and out["ranking"] == ["A", "B", "C"]
        print("OK: empty, garbage, sentinel, wrong-shape and raising judges all fall back")

        # Valid: labels mapped back, unknown dropped, missing appended in reranker order.
        response = json.dumps({"ranking": [inverse["C"], "C99", inverse["A"]],
                               "relevant": {inverse["C"]: True, inverse["A"]: "false"},
                               "reasons": {inverse["C"]: "decides the point"}})
        _call_llm = await fake("```json\n" + response + "\n```")
        out = await judge("q", rows, evidence)
        assert out["used"] and out["ranking"] == ["C", "A", "B"], out
        assert out["relevant"] == {"A": False, "B": False, "C": True}
        assert out["reasons"] == {"C": "decides the point"}
        print("OK: valid verdict mapped back; unknown label dropped; missing id appended; missing flag = false")
        _call_llm = original

    asyncio.run(main())
