"""
Query preprocessing for the Legal RAG retrieval pipeline.

STEP 1 of retrieval: takes a raw user query string and returns a cleaned
query string plus a structured intent dict.

This module is intentionally dependency-free with respect to the rest of the
system: no embeddings, no database calls, no file I/O.
"""

import re

from loguru import logger

# Keyword -> case_type. Order matters: the first matching entry wins, so more
# specific case types ("bail") are checked before broader ones ("criminal").
_CASE_TYPE_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("bail", ("bail",)),
    ("criminal", ("murder", "homicide")),
    ("civil", ("property", "possession")),
    ("constitutional", ("constitution", "fundamental")),
    ("writ", ("writ", "mandamus")),
]

_DEFAULT_CASE_TYPE = "general"

_POSITIVE_OUTCOME_KEYWORDS = ("granted", "allowed")
_NEGATIVE_OUTCOME_KEYWORDS = ("dismissed", "rejected")

# Earliest meaningful year for Pakistani jurisprudence (independence) through
# the current corpus horizon.
_MIN_YEAR = 1947
_MAX_YEAR = 2026

# Characters kept by clean_query: letters, digits, spaces, hyphens, periods,
# commas, question marks, and the citation punctuation / ( ) §. Everything else
# is dropped.
#
# The citation characters matter because they carry meaning in Pakistani legal
# references and dropping them corrupts the reference rather than simplifying
# it: "C.A. 23-P/2017" became "c.a. 23-p2017" (the slash fused number and year,
# so case_keys could no longer parse it), "Article 185(3)" became
# "article 1853", and "§ 9" lost its marker. Downstream consumers (case_keys,
# statutes, the FTS5 query builder) all expect these characters intact.
_DISALLOWED_CHARS = re.compile(r"[^a-zA-Z0-9 \-.,?/()§]")
_WHITESPACE_RUN = re.compile(r"\s+")
_FOUR_DIGIT = re.compile(r"\b\d{4}\b")


def clean_query(query: str) -> str:
    """Normalise a raw user query into a lowercase, whitespace-collapsed string.

    Args:
        query: The raw query as typed by the user.

    Returns:
        The cleaned query string.
    """
    # Collapse whitespace first so that newlines/tabs become spaces rather than
    # being stripped as disallowed characters (which would fuse words together).
    normalised = _WHITESPACE_RUN.sub(" ", query)
    stripped = _DISALLOWED_CHARS.sub("", normalised)
    return _WHITESPACE_RUN.sub(" ", stripped).strip().lower()


def extract_intent(query: str) -> dict:
    """Derive structured search intent from a raw user query.

    Args:
        query: The raw query as typed by the user (not the cleaned form).

    Returns:
        A dict with keys ``case_type`` (str), ``years_mentioned`` (list[int])
        and ``outcome_bias`` (str | None).
    """
    lowered = query.lower()

    case_type = _DEFAULT_CASE_TYPE
    for candidate, keywords in _CASE_TYPE_KEYWORDS:
        if any(keyword in lowered for keyword in keywords):
            case_type = candidate
            break

    years_mentioned = [
        year
        for year in (int(match) for match in _FOUR_DIGIT.findall(lowered))
        if _MIN_YEAR <= year <= _MAX_YEAR
    ]

    outcome_bias: str | None = None
    if any(keyword in lowered for keyword in _POSITIVE_OUTCOME_KEYWORDS):
        outcome_bias = "positive"
    elif any(keyword in lowered for keyword in _NEGATIVE_OUTCOME_KEYWORDS):
        outcome_bias = "negative"

    return {
        "case_type": case_type,
        "years_mentioned": years_mentioned,
        "outcome_bias": outcome_bias,
    }


def preprocess(query: str) -> tuple[str, dict]:
    """Run the full query preprocessing step.

    Args:
        query: The raw query as typed by the user.

    Returns:
        A ``(cleaned_query, intent)`` tuple.
    """
    cleaned = clean_query(query)
    intent = extract_intent(query)

    logger.debug(f"Query cleaned: {cleaned!r}")
    logger.debug(f"Query intent: {intent}")

    return cleaned, intent


if __name__ == "__main__":
    test_query = "Case where accused got bail in a murder case 2019, bail was granted"
    cleaned, intent = preprocess(test_query)
    print(f"Cleaned: {cleaned}")
    print(f"Intent:  {intent}")
    assert intent["case_type"] == "bail" and intent["years_mentioned"] == [2019]
    assert intent["outcome_bias"] == "positive"

    # Citation punctuation survives; everything else behaves as before.
    checks = [
        ("C.A. 23-P/2017", "c.a. 23-p/2017"),
        ("Article 185(3) of the Constitution", "article 185(3) of the constitution"),
        ("§ 9 of the Act", "§ 9 of the act"),
        ("s.302 PPC!!  murder\n\tcase", "s.302 ppc murder case"),
        ("What's the *holding*?", "whats the holding?"),
    ]
    for raw, expected in checks:
        got = clean_query(raw)
        assert got == expected, f"clean_query({raw!r}) = {got!r}, expected {expected!r}"
        print(f"  OK  {raw!r:<42} -> {got!r}")

    from app.retrieval.case_keys import case_keys
    assert case_keys(clean_query("C.A. 23-P/2017")) == ["CA-23-P-2017"]
    print("OK: clean_query keeps citations parseable.")
