"""
Side-by-side comparison of several judgments.

When a query returns more than one authority, the useful next question is not
"what does each one say" but "where do they differ". This module turns a set of
judgment ids into one row per judgment with the same fields filled for each, so
the answer is a table rather than three essays the reader has to diff by eye.

Extraction, not generation
--------------------------
Every field is pulled from the judgment's own sections — the root node for the
case title, HEADER_CORAM for the bench and the date, FACTS, LEGAL_ISSUES and
FINAL_ORDER for the rest. The model's job is to compress what is there into a
table cell, never to supply anything that is missing. A field the judgment does
not record comes back as an em dash, which is information: a comparison that
quietly invents a date is worse than one with a gap in it.

Under a shared quota
--------------------
One row is one LLM call, so a ten-judgment comparison alone could spend most
of the free tier's 15 requests a minute. Calls go through the process-wide
limiter in llm_responder._complete; each row carries a ``status`` (ready /
rate_limited / error) so the client can say "busy" instead of showing a row of
dashes as if the judgment recorded nothing. A row depends only on its
judgment, not on any query, so successful rows are cached per judgment and a
second comparison of the same case costs nothing.
"""

import asyncio
import json
import re
import sys
from collections import OrderedDict
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from loguru import logger

from app.retrieval.contracts import ANSWER_ERROR, ANSWER_RATE_LIMITED, ANSWER_READY
from app.retrieval.llm_responder import ERROR_RESPONSE, _complete, status_of
from app.retrieval.orchestrator import build_judgment_context

# The columns of the comparison table, in the order they are shown. Each is
# something a researcher would actually line up across cases.
FIELDS = [
    ("case_number", "Case number"),
    ("date", "Date"),
    ("bench", "Bench"),
    ("parties", "Parties"),
    ("subject", "Subject"),
    ("key_facts", "Key facts"),
    ("legal_issue", "Legal issue"),
    ("reasoning", "Court's reasoning"),
    ("final_decision", "Final decision"),
]

MISSING = "—"

SYSTEM_PROMPT = """You extract structured comparison data from Pakistan Supreme
Court judgments.

Return ONLY a JSON object with exactly these keys:
  case_number, date, bench, parties, subject, key_facts, legal_issue,
  reasoning, final_decision

Rules:
- Every value must come from the judgment text you are given. Extract; do not
  infer, summarise beyond the text, or supply anything from general knowledge.
- If the judgment does not record a field, use "—". A gap is correct; an
  invented value is not.
- Keep each value to one sentence, except case_number, date, bench and parties
  which should be a short phrase.
- "parties" is appellant versus respondent, in that order.
- "subject" is the area of law in three or four words, e.g. "Service tribunal
  jurisdiction" or "Evacuee land title".
- "final_decision" is the disposition: allowed, dismissed, remanded, and on
  what terms.

Return the JSON object and nothing else - no prose, no code fence."""

MAX_TOKENS = 700

# Successful rows by judgment id, most recently used last.
ROW_CACHE_SIZE = 256
_row_cache: OrderedDict[str, dict] = OrderedDict()

# Models wrap JSON in a fence often enough to be worth handling rather than
# failing the whole comparison over.
_FENCE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def _parse(content: str) -> dict | None:
    """Pull a JSON object out of a model response."""
    if not content or content == ERROR_RESPONSE:
        return None

    candidate = content.strip()
    fenced = _FENCE.search(candidate)
    if fenced:
        candidate = fenced.group(1).strip()

    # Fall back to the outermost braces if there is prose around the object.
    if not candidate.startswith("{"):
        start, end = candidate.find("{"), candidate.rfind("}")
        if start == -1 or end == -1:
            return None
        candidate = candidate[start:end + 1]

    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError as e:
        logger.warning(f"Comparison row was not valid JSON: {e}")
        return None

    return parsed if isinstance(parsed, dict) else None


async def compare_one(judgment_id: str) -> dict:
    """Extract one judgment's comparison row.

    Args:
        judgment_id: The judgment to extract.

    Returns:
        A row with every key in FIELDS, plus `judgment_id` and `filename`.
        Missing fields carry an em dash rather than being absent.
    """
    cached = _row_cache.get(judgment_id)
    if cached is not None:
        _row_cache.move_to_end(judgment_id)
        return dict(cached)

    filename, context = await build_judgment_context(judgment_id)

    row = {key: MISSING for key, _ in FIELDS}
    row["judgment_id"] = judgment_id
    row["filename"] = filename
    row["status"] = ANSWER_ERROR

    if not context:
        logger.warning(f"No context to compare for judgment_id={judgment_id}")
        return row

    content = await _complete(
        SYSTEM_PROMPT,
        f"JUDGMENT:\n{context}\n\nReturn the JSON object.",
        MAX_TOKENS,
        label="compare",
    )
    status = status_of(content)
    if status != ANSWER_READY:
        row["status"] = status
        return row
    parsed = _parse(content)
    if parsed is None:
        logger.warning(f"Could not extract a comparison row for {judgment_id}")
        return row

    for key, _ in FIELDS:
        value = parsed.get(key)
        if isinstance(value, str) and value.strip():
            row[key] = value.strip()

    row["status"] = ANSWER_READY
    _row_cache[judgment_id] = dict(row)
    while len(_row_cache) > ROW_CACHE_SIZE:
        _row_cache.popitem(last=False)
    return row


async def compare_judgments(judgment_ids: list[str]) -> dict:
    """Build the comparison table for several judgments.

    Args:
        judgment_ids: The judgments to compare, in the order to display them.

    Returns:
        ``{"fields": [{key, label}], "rows": [...]}``. Rows keep the order of
        `judgment_ids` so the table matches the list the reader came from.
    """
    if not judgment_ids:
        return {"fields": [{"key": k, "label": l} for k, l in FIELDS], "rows": [], "rate_limited": False}

    logger.info(f"Comparing {len(judgment_ids)} judgments")
    rows = await asyncio.gather(*(compare_one(jid) for jid in judgment_ids))

    return {
        "fields": [{"key": key, "label": label} for key, label in FIELDS],
        "rows": list(rows),
        "rate_limited": any(r.get("status") == ANSWER_RATE_LIMITED for r in rows),
    }


if __name__ == "__main__":
    from app.database import connect_db
    from app.retrieval.index_loader import get_all_judgment_ids

    async def main() -> None:
        await connect_db()

        ids = get_all_judgment_ids()[:2]
        print(f"comparing: {ids}\n")

        table = await compare_judgments(ids)

        for row in table["rows"]:
            print(f"--- {row['filename'] or row['judgment_id'][:8]} ---")
            for field in table["fields"]:
                print(f"  {field['label']:<18} {str(row[field['key']])[:88]}")
            print()

        assert table["rows"], "no rows produced"
        assert len(table["rows"]) == len(ids), "a judgment was dropped"
        assert all(set(f["key"] for f in table["fields"]) <= set(r) for r in table["rows"]), \
            "a row is missing one of the table's fields"
        assert table["rows"][0]["judgment_id"] == ids[0], "row order does not match input"

        filled = sum(
            1 for r in table["rows"] for f in table["fields"] if r[f["key"]] != MISSING
        )
        total = len(table["rows"]) * len(table["fields"])
        print(f"fields extracted: {filled}/{total}")
        assert filled > total / 2, "most fields came back empty; check the prompt"

        print("OK: comparison table verified.")

    asyncio.run(main())
