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
    Section 489-F PPC                lettered sections ("489-F", "22-A", "489F")
    Section 144(4) Elections Act 2017  a section of any other named Act
    Order 21 Rule 1 CPC              CPC orders, roman numerals converted
    Civil Servants Act 1973          named Acts, comma before the year dropped

The major codes are recognised by full name and by abbreviation:
PPC (Pakistan Penal Code), CrPC (Code of Criminal Procedure), CPC (Code of
Civil Procedure), QSO (Qanun-e-Shahadat Order), CNSA (Control of Narcotic
Substances Act), ATA (Anti-Terrorism Act).
"""

import re

_CODES: list[tuple[str, str]] = [
    (r"pakistan\s+penal\s+code|p\.?\s*p\.?\s*c\.?", "PPC"),
    (r"code\s+of\s+criminal\s+procedure|cr\.?\s*p\.?\s*c\.?", "CrPC"),
    (r"code\s+of\s+civil\s+procedure|c\.?\s*p\.?\s*c\.?", "CPC"),
    (r"qanun[-\s]e[-\s]shahadat(?:\s+order)?|q\.?\s*s\.?\s*o\.?", "QSO"),
    (r"control\s+of\s+narcotic\s+substances\s+act(?:,?\s*1997)?|c\.?\s*n\.?\s*s\.?\s*a\.?", "CNSA"),
    # The abbreviation only in capitals: lower-case "at a" is ordinary English.
    (r"anti[-\s]?terrorism\s+act(?:,?\s*1997)?|(?-i:A\.?\s*T\.?\s*A\.?)", "ATA"),
]
_CODE_ALT = "|".join(f"(?:{p})" for p, _ in _CODES)
_CODE_RES = [(re.compile(rf"^(?:{p})$", re.IGNORECASE), c) for p, c in _CODES]

# Sub-clauses: "(3)", "(1)(a)", "(b)(ii)".
_SUB = r"(?:\s*\(\s*[0-9a-z]{1,4}\s*\))*"

# A section number, with the letter Pakistani statutes add: "489-F", "22-A",
# "489F". The letter must end the word ("5Act" is not section 5-A).
_NUM = r"\d{1,4}(?:-?[A-Za-z](?![A-Za-z]))?"

_ARTICLE_RE = re.compile(
    rf"\b(?:articles?|arts?\.)\s*(\d{{1,3}}[A-Z]?{_SUB})",
    re.IGNORECASE,
)

_SECTION_RE = re.compile(
    rf"\b(?:sections?|secs?\.|ss?\.|u/s\.?)\s*({_NUM}{_SUB})"
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

# Several sections sharing one code, as FIRs and judgments write them:
# "Sections 448/380 PPC", "sections 302, 324 and 34 PPC", "302/34 P.P.C.".
# Every number gets the code named at the end.
_SECTION_LIST_RE = re.compile(
    rf"\b(?:sections?|secs?\.|ss?\.|u/s\.?)\s*"
    rf"({_NUM}{_SUB}(?:\s*(?:/|,|&|\band\b)\s*{_NUM}{_SUB})+)"
    rf"\s*(?:of\s+the|of|,)?\s*({_CODE_ALT})",
    re.IGNORECASE,
)
_LIST_ITEM_RE = re.compile(rf"{_NUM}{_SUB}", re.IGNORECASE)

# A section of a named Act that is not one of the codes above: "section 144(4)
# of the Elections Act, 2017", "section 122 of the Income Tax Ordinance 2001".
# The Act's name must be capitalised (so "of the said Act" is not one); the
# year is optional. Case-sensitive except for the word "section".
_SECTION_OF_ACT_RE = re.compile(
    rf"\b(?i:sections?|secs?\.|ss?\.)\s*({_NUM}{_SUB})\s*,?\s+of\s+(?:the\s+)?"
    rf"({_CAP}(?:\s+(?:{_CAP}|{_CONNECTOR})){{0,9}}?\s+(?:Act|Ordinance|Order|Rules|Regulations|Code))"
    r"(?:\s*,?\s*((?:18|19|20)\d{2})\b)?"
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


def _clean_num(value: str) -> str:
    """A section number in canonical form: '489F' / '489-f' -> '489-F', and
    sub-clauses as _clean_sub: '302 (b)' -> '302(b)'."""
    value = _clean_sub(value)
    m = re.match(r"(\d{1,4})-?([A-Za-z])(?![A-Za-z])(.*)$", value)
    return f"{m.group(1)}-{m.group(2).upper()}{m.group(3)}" if m else value


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

    # Lists first, so "Sections 302/34 PPC" keeps its reading order.
    for m in _SECTION_LIST_RE.finditer(text):
        code = _code(m.group(2))
        if code:
            for item in _LIST_ITEM_RE.findall(m.group(1)):
                add(f"Section {_clean_num(item)} {code}")

    for m in _SECTION_RE.finditer(text):
        code = _code(m.group(2))
        if code:
            add(f"Section {_clean_num(m.group(1))} {code}")

    for m in _SECTION_OF_ACT_RE.finditer(text):
        words = m.group(2).split()
        while words and words[0].lower() in _LEADING_NOISE:
            words.pop(0)
        name = " ".join(words)
        if len(words) < 2 or _code(name) or _code(f"{name} {m.group(3) or ''}".strip()):
            continue   # one of the codes above: already added in its short form
        add(" ".join(x for x in ("Section", _clean_num(m.group(1)), name, m.group(3)) if x))

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
        # Lettered sections, common in Pakistani codes.
        ("under section 489-F PPC", ["Section 489-F PPC"]),
        ("section 489F of the PPC", ["Section 489-F PPC"]),
        ("a petition under section 22-A Cr.P.C.", ["Section 22-A CrPC"]),
        ("section 337-A(i) PPC", ["Section 337-A(i) PPC"]),
        # Sections of other named Acts.
        ("section 144(4) of the Elections Act, 2017", ["Section 144(4) Elections Act 2017"]),
        ("section 122 of the Income Tax Ordinance, 2001", ["Section 122 Income Tax Ordinance 2001"]),
        ("section 32 of the Customs Act", ["Section 32 Customs Act"]),
        ("section 7 of the Anti-Terrorism Act, 1997", ["Section 7 ATA"]),
        ("section 7 ATA", ["Section 7 ATA"]),
        ("convicted u/s 302 PPC", ["Section 302 PPC"]),
        ("section 302 of the Pakistan Penal Code", ["Section 302 PPC"]),   # a code: short form only
        # Lists sharing one code.
        ("a case registered under Sections 448/380 PPC", ["Section 448 PPC", "Section 380 PPC"]),
        ("u/s 302/34 P.P.C.", ["Section 302 PPC", "Section 34 PPC"]),
        ("sections 302(b), 324 and 34 PPC", ["Section 302(b) PPC", "Section 324 PPC", "Section 34 PPC"]),
        ("sections 489-F/420 PPC", ["Section 489-F PPC", "Section 420 PPC"]),
        # Not sections.
        ("section 302 at a later stage", []),
        ("section 5 of the said Act", []),
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
