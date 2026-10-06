"""
Statute-reference parsing and normalisation — a shared contract.

Same reasoning as app.retrieval.case_keys: the ingestion side (extracting what
a judgment cites) and the query side (extracting what a lawyer asks about) must
produce identical strings, or "s.302 PPC" in a query never meets "Section 302 of
the Pakistan Penal Code" in a judgment.

Canonical forms
---------------
    Article 199                      constitutional articles
    Article 185(3)                   sub-clauses kept, they change the meaning
    Section 302 PPC                  sections of the major codes, by abbreviation
    Section 497 CrPC
    Order 21 Rule 1 CPC              CPC orders, roman numerals converted
    Civil Servants Act 1973          named Acts, comma before the year dropped

The major codes are recognised by full name and by abbreviation:
PPC (Pakistan Penal Code), CrPC (Code of Criminal Procedure), CPC (Code of
Civil Procedure), QSO (Qanun-e-Shahadat Order), CNSA (Control of Narcotic
Substances Act).
"""

import re

_CODES: list[tuple[str, str]] = [
    (r"pakistan\s+penal\s+code|p\.?\s*p\.?\s*c\.?", "PPC"),
    (r"code\s+of\s+criminal\s+procedure|cr\.?\s*p\.?\s*c\.?", "CrPC"),
    (r"code\s+of\s+civil\s+procedure|c\.?\s*p\.?\s*c\.?", "CPC"),
    (r"qanun[-\s]e[-\s]shahadat(?:\s+order)?|q\.?\s*s\.?\s*o\.?", "QSO"),
    (r"control\s+of\s+narcotic\s+substances\s+act(?:,?\s*1997)?|c\.?\s*n\.?\s*s\.?\s*a\.?", "CNSA"),
]
_CODE_ALT = "|".join(f"(?:{p})" for p, _ in _CODES)
_CODE_RES = [(re.compile(rf"^(?:{p})$", re.IGNORECASE), c) for p, c in _CODES]

# Sub-clauses: "(3)", "(1)(a)", "(b)(ii)".
_SUB = r"(?:\s*\(\s*[0-9a-z]{1,4}\s*\))*"

_ARTICLE_RE = re.compile(
    rf"\b(?:articles?|arts?\.)\s*(\d{{1,3}}[A-Z]?{_SUB})",
    re.IGNORECASE,
)

_SECTION_RE = re.compile(
    rf"\b(?:sections?|secs?\.|ss?\.)\s*(\d{{1,4}}[A-Z]?{_SUB})"
    rf"(?:\s*(?:of\s+the|of|,)?\s*({_CODE_ALT}))?",
    re.IGNORECASE,
)

_ORDER_RULE_RE = re.compile(
    rf"\border\s+([IVXLC]+|\d{{1,3}})\s*,?\s*rules?\s+(\d{{1,3}}{_SUB})"
    rf"(?:\s*(?:of\s+the|of|,)?\s*({_CODE_ALT}))?",
    re.IGNORECASE,
)

# A named Act or Ordinance with a year: "Civil Servants Act, 1973". Names may
# contain lowercase connectors ("Representation of the People Act"), but must
# start on a capitalised word, so a sentence fragment is not swallowed whole.
_CAP = r"[A-Z][A-Za-z()'\-]*"
_CONNECTOR = r"(?:of|the|and|for|on|in|to)"
_ACT_RE = re.compile(
    rf"\b({_CAP}(?:\s+(?:{_CAP}|{_CONNECTOR})){{0,9}}?\s+(?:Act|Ordinance|Order|Rules))"
    r"\s*,?\s*((?:18|19|20)\d{2})\b"
)

_ROMAN = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}

# Words that begin a capitalised phrase but are not part of an Act's name.
_LEADING_NOISE = {"the", "under", "of", "in", "and", "by", "per", "vide", "see", "within", "whether"}


def _roman_to_int(value: str) -> int:
    value = value.upper()
    if value.isdigit():
        return int(value)
    total, prev = 0, 0
    for ch in reversed(value):
        n = _ROMAN.get(ch, 0)
        total = total - n if n < prev else total + n
        prev = max(prev, n)
    return total


def _code(phrase: str | None) -> str | None:
    if not phrase:
        return None
    compact = re.sub(r"\s+", " ", phrase.strip())
    for pattern, code in _CODE_RES:
        if pattern.match(compact):
            return code
    return None


def _clean_sub(value: str) -> str:
    """'185 (3)' -> '185(3)', '9 (1) (a)' -> '9(1)(a)'."""
    return re.sub(r"\s+", "", value)


def parse_statutes(text: str) -> list[str]:
    """Every statutory reference in `text`, normalised, in order, de-duplicated.

    A bare "section 9" with no code named is dropped: without the code it cannot
    be matched against anything and would only add noise to retrieval.
    """
    if not text:
        return []

    found: list[str] = []

    def add(item: str) -> None:
        if item not in found:
            found.append(item)

    for m in _ARTICLE_RE.finditer(text):
        add(f"Article {_clean_sub(m.group(1))}")

    for m in _SECTION_RE.finditer(text):
        code = _code(m.group(2))
        if code:
            add(f"Section {_clean_sub(m.group(1))} {code}")

    for m in _ORDER_RULE_RE.finditer(text):
        code = _code(m.group(3)) or "CPC"  # Order/Rule references are CPC by convention
        add(f"Order {_roman_to_int(m.group(1))} Rule {_clean_sub(m.group(2))} {code}")

    for m in _ACT_RE.finditer(text):
        words = m.group(1).split()
        while words and words[0].lower() in _LEADING_NOISE:
            words.pop(0)
        if len(words) >= 2:
            add(f"{' '.join(words)} {m.group(2)}")

    return found


if __name__ == "__main__":
    cases = [
        ("under Article 199 of the Constitution", ["Article 199"]),
        ("Article 185(3) of the Constitution", ["Article 185(3)"]),
        ("Art. 184 (3)", ["Article 184(3)"]),
        ("section 302 PPC", ["Section 302 PPC"]),
        ("s.302 PPC", ["Section 302 PPC"]),
        ("Section 302 of the Pakistan Penal Code", ["Section 302 PPC"]),
        ("section 497 Cr.P.C.", ["Section 497 CrPC"]),
        ("Section 9(c) of the CNSA", ["Section 9(c) CNSA"]),
        ("Order XXI Rule 1 CPC", ["Order 21 Rule 1 CPC"]),
        ("the Civil Servants Act, 1973", ["Civil Servants Act 1973"]),
        ("under the Representation of the People Act, 1976", ["Representation of the People Act 1976"]),
        ("Service Tribunals Act 1973", ["Service Tribunals Act 1973"]),
        ("section 9 alone names no code", []),
        ("bail granted despite murder charges", []),
    ]
    failures = 0
    for text, expected in cases:
        got = parse_statutes(text)
        ok = all(e in got for e in expected) and (expected or not got)
        failures += not ok
        print(f"  {'OK  ' if ok else 'FAIL'} {text[:52]:<52} -> {got}")

    # The contract: query phrasing and judgment phrasing must meet.
    assert parse_statutes("s.302 PPC") == parse_statutes(
        "Section 302 of the Pakistan Penal Code"
    ), "query and judgment phrasings did not normalise identically"
    print("\n  query and judgment phrasings normalise identically  OK")

    assert failures == 0, f"{failures} statute formats failed"
    print(f"\nOK: {len(cases)} statute formats normalised.")
