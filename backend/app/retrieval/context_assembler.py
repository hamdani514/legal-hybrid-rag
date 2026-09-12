"""
Context assembly for the retrieval pipeline.

STEP 8 of retrieval: flattens one expanded judgment (from
app.retrieval.context_expander) into a single formatted string, ordered the way
a judgment actually reads and trimmed to a token budget. Returns text. Nothing
else — no ChromaDB, no MongoDB, no file I/O.

Section naming
--------------
The ingestion classifier labels sections in upper case and calls the disposition
FINAL_ORDER, so those are the values used here. Lookups are case-insensitive, so
callers passing lower-case names still resolve correctly.

Token counting
--------------
Counting uses tiktoken's cl100k_base. This project generates with Groq's
llama-3.3-70b, whose tokenizer differs, so the count is a close approximation
rather than an exact figure — fine for budgeting, but leave headroom before a
hard model limit.
"""

import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import tiktoken
from loguru import logger

from app.config import settings

# The order a judgment reads in, regardless of retrieval score.
SECTION_ORDER = [
    "HEADER_CORAM",
    "FACTS",
    "ARGUMENTS",
    "LEGAL_ISSUES",
    "ANALYSIS_RATIO",
    "FINAL_ORDER",
]

# What to sacrifice first when over budget. The court's reasoning and its
# disposition are the last things to go; the bench listing is the first.
TRIM_PRIORITY = [
    "HEADER_CORAM",
    "ARGUMENTS",
    "FACTS",
    "LEGAL_ISSUES",
    "ANALYSIS_RATIO",
    "FINAL_ORDER",
]

MAX_TOKENS = settings.MAX_CONTEXT_TOKENS

ENCODING_NAME = "cl100k_base"
TRIM_MARKER = " [...trimmed]"
SUMMARY_HEADER = "=== CASE SUMMARY ==="

_encoding = tiktoken.get_encoding(ENCODING_NAME)


def count_tokens(text: str) -> int:
    """Return the number of tokens in `text`."""
    return len(_encoding.encode(text))


def _truncate_to_tokens(text: str, budget: int) -> str:
    """Cut `text` at a token boundary so it fits `budget`, marking the cut."""
    if budget <= 0:
        return ""

    tokens = _encoding.encode(text)
    if len(tokens) <= budget:
        return text

    marker_cost = count_tokens(TRIM_MARKER)
    keep = max(budget - marker_cost, 0)
    if keep == 0:
        return ""

    return _encoding.decode(tokens[:keep]).rstrip() + TRIM_MARKER


def _build_section_map(expanded: dict) -> dict[str, str]:
    """Flatten an expanded judgment into {section_type: text}.

    Directly retrieved sections win over expanded ones when both carry the same
    section type, since the retrieved copy is the passage that actually matched.
    """
    section_map: dict[str, str] = {}

    # Expanded first, so the retrieved pass overwrites them.
    for section in list(expanded.get("expanded_sections") or []) + list(
        expanded.get("retrieved_sections") or []
    ):
        section_type = (section.get("section_type") or "").strip().upper()
        text = (section.get("text") or "").strip()
        if section_type and text:
            section_map[section_type] = text

    return section_map


def _render(section_map: dict[str, str], summary: str) -> str:
    """Render the summary and sections into the final ordered string."""
    blocks: list[str] = []

    if summary:
        blocks.append(f"{SUMMARY_HEADER}\n{summary}")

    for section_type in SECTION_ORDER:
        text = section_map.get(section_type)
        if text:
            heading = section_type.replace("_", " ")
            blocks.append(f"=== {heading} ===\n{text}")

    return "\n\n".join(blocks)


def assemble_judgment_context(expanded: dict, max_tokens: int = MAX_TOKENS) -> str:
    """Assemble one expanded judgment into an ordered, budgeted context string.

    Args:
        expanded: One dict from
            :func:`app.retrieval.context_expander.expand_all_judgments`.
        max_tokens: The token budget for the returned string.

    Returns:
        The assembled context, trimmed if it exceeded the budget.
    """
    section_map = _build_section_map(expanded)

    root_node = expanded.get("root_node") or {}
    summary = (root_node.get("text") or "").strip()

    assembled = _render(section_map, summary)
    total = count_tokens(assembled)
    if total <= max_tokens:
        return assembled

    logger.info(
        f"Context for judgment_id={expanded.get('judgment_id')} is "
        f"{total} tokens, over the {max_tokens} budget; trimming."
    )

    # Trim one section at a time, least important first, and stop as soon as
    # the whole assembled string fits — later sections keep their full text.
    for section_type in TRIM_PRIORITY:
        if total <= max_tokens:
            break
        if section_type not in section_map:
            continue

        overshoot = total - max_tokens
        current = count_tokens(section_map[section_type])
        # Leave nothing behind only if this one section cannot cover the gap.
        target = max(current - overshoot, 0)

        section_map[section_type] = _truncate_to_tokens(section_map[section_type], target)
        if not section_map[section_type]:
            del section_map[section_type]

        assembled = _render(section_map, summary)
        total = count_tokens(assembled)

    # The summary is the last thing standing; trim it only if sections were not
    # enough to get under budget.
    if total > max_tokens and summary:
        overshoot = total - max_tokens
        summary = _truncate_to_tokens(summary, max(count_tokens(summary) - overshoot, 0))
        assembled = _render(section_map, summary)
        total = count_tokens(assembled)

    if total > max_tokens:
        logger.warning(
            f"Context for judgment_id={expanded.get('judgment_id')} is still "
            f"{total} tokens after trimming (budget {max_tokens})."
        )

    return assembled


def assemble_all_judgments(
    expanded_list: list[dict],
    max_tokens_per_judgment: int | None = None,
) -> list[dict]:
    """Assemble every expanded judgment, splitting the budget between them.

    Args:
        expanded_list: The list from
            :func:`app.retrieval.context_expander.expand_all_judgments`.
        max_tokens_per_judgment: Per-judgment budget. When omitted, the global
            budget is divided evenly across the judgments.

    Returns:
        One dict per judgment with ``judgment_id``, ``filename``, ``context``
        and ``token_count``.
    """
    if not expanded_list:
        return []

    per_judgment = max_tokens_per_judgment or max(MAX_TOKENS // len(expanded_list), 1)

    results: list[dict] = []
    for expanded in expanded_list:
        context = assemble_judgment_context(expanded, max_tokens=per_judgment)
        root_node = expanded.get("root_node") or {}

        results.append({
            "judgment_id": expanded.get("judgment_id", ""),
            # Node documents carry no filename; it lives in the `documents`
            # collection. `title` is the case name and is the usable label.
            "filename": root_node.get("filename", ""),
            "heading": root_node.get("title", ""),
            "context": context,
            "token_count": count_tokens(context),
        })

    logger.info(
        f"Context assembled for {len(results)} judgments, "
        f"{per_judgment} token budget each"
    )
    return results


if __name__ == "__main__":
    fake_expanded = {
        "judgment_id": "test_001",
        "root_node": {"text": "This is a bail case summary.", "section_type": "ROOT"},
        "retrieved_sections": [
            {"section_type": "ANALYSIS_RATIO", "text": "The court held that...", "score": 0.91, "is_directly_retrieved": True},
            {"section_type": "FINAL_ORDER", "text": "Appeal allowed.", "score": 0.88, "is_directly_retrieved": True},
        ],
        "expanded_sections": [
            {"section_type": "FACTS", "text": "The accused was arrested...", "score": 0.0, "is_directly_retrieved": False}
        ],
    }

    result = assemble_judgment_context(fake_expanded)
    print(result)
    print(f"\nToken count: {count_tokens(result)}")

    # Order must follow SECTION_ORDER, not retrieval score.
    assert result.index("FACTS") < result.index("ANALYSIS RATIO") < result.index("FINAL ORDER")
    assert result.startswith(SUMMARY_HEADER)

    # A retrieved section must win over an expanded one of the same type.
    clash = {
        "judgment_id": "test_002",
        "root_node": None,
        "retrieved_sections": [{"section_type": "FACTS", "text": "RETRIEVED", "score": 0.9, "is_directly_retrieved": True}],
        "expanded_sections": [{"section_type": "FACTS", "text": "EXPANDED", "score": 0.0, "is_directly_retrieved": False}],
    }
    assembled = assemble_judgment_context(clash)
    assert "RETRIEVED" in assembled and "EXPANDED" not in assembled, "dedup kept the wrong copy"

    # Trimming must respect the budget and sacrifice HEADER_CORAM before FINAL_ORDER.
    big = {
        "judgment_id": "test_003",
        "root_node": {"text": "summary."},
        "retrieved_sections": [
            {"section_type": s, "text": ("word " * 400), "score": 0.5, "is_directly_retrieved": True}
            for s in SECTION_ORDER
        ],
        "expanded_sections": [],
    }
    trimmed = assemble_judgment_context(big, max_tokens=300)
    print(f"\nTrim test: {count_tokens(trimmed)} tokens (budget 300)")
    assert count_tokens(trimmed) <= 300, "trimming did not respect the budget"
    assert TRIM_MARKER.strip() in trimmed, "no trim marker emitted"

    header_part = trimmed.split("=== FINAL ORDER ===")[0]
    assert "=== FINAL ORDER ===" in trimmed, "the disposition was cut before less important sections"
    print("\nOK: ordering, de-duplication and trimming verified.")
