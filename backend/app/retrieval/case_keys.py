"""
Case-number parsing and normalisation — a shared contract.

Why this lives in Wave 0 and not with either agent
--------------------------------------------------
Exact-match retrieval only works if the indexing side (metadata extraction from
HEADER_CORAM) and the query side (the query analyzer) turn the same case into
the SAME key. If one writes "CA-5-Q-2014" and the other looks up
"C.A.5-Q/2014", a lawyer typing the exact citation gets a dense-search guess
instead of the case. So there is exactly one normaliser, and both sides call it.

The formats it has to absorb
----------------------------
Judgment headers and real user queries write the same citation many ways:

    CIVIL APPEAL NO. 5-Q OF 2014          header, upper case
    CIVIL APPEAL NO.43-Q OF 2018          no space after "NO."
    Civil Appeals No.26-K to 38-K of 2021 a range, one judgment
    CIVIL APPEALS NOS.06 AND 724 OF 2016  a conjunction, leading zero
    Civil Petition No. 34-Q of 2019       petition for leave to appeal
    Civil Appeal No. 1 of 2020            no registry letter
    C.A. 23-P/2017                        abbreviated, slash year
    C.P.L.A. 34-Q/2019                    abbreviated petition
    Crl.A. 12-L of 2019                   criminal appeal

All of these normalise to `TYPE-NUMBER[-REGISTRY]-YEAR`:

    CA-5-Q-2014   CA-43-Q-2018   CA-26-K-2021 ... CA-38-K-2021
    CA-6-2016  CA-724-2016   CP-34-Q-2019   CA-1-2020   CA-23-P-2017   CRA-12-L-2019

Registry letters are the Supreme Court's branch registries: K Karachi,
L Lahore, P Peshawar, Q Quetta. Islamabad cases carry none.
"""

import re

# Longest first, so "civil petition for leave to appeal" wins over "civil petition".
# Each entry: (regex for the case-type phrase, normalised type code).
_TYPE_PATTERNS: list[tuple[str, str]] = [
    (r"civil\s+petitions?\s+for\s+leave\s+to\s+appeal", "CP"),
    (r"criminal\s+petitions?\s+for\s+leave\s+to\s+appeal", "CRP"),
    (r"civil\s+review\s+petitions?", "REVP"),
    (r"criminal\s+review\s+petitions?", "CRREVP"),
    (r"civil\s+misc(?:ellaneous)?\.?\s+applications?", "CMA"),
    (r"constitution(?:al)?\s+petitions?", "CONSTP"),
    (r"human\s+rights\s+cases?", "HRC"),
    (r"suo\s+motu\s+cases?", "SMC"),
    (r"jail\s+petitions?", "JP"),
    (r"civil\s+appeals?", "CA"),
    (r"civil\s+petitions?", "CP"),
    (r"criminal\s+appeals?", "CRA"),
    (r"criminal\s+petitions?", "CRP"),
    # Abbreviations. Dots and spaces are optional throughout.
    (r"c\.?\s*p\.?\s*l\.?\s*a\.?", "CP"),
    (r"crl?\.?\s*p\.?\s*l\.?\s*a\.?", "CRP"),
    (r"c\.?\s*r\.?\s*p\.?", "REVP"),
    (r"c\.?\s*m\.?\s*a\.?", "CMA"),
    (r"const\.?\s*p\.?", "CONSTP"),
    (r"s\.?\s*m\.?\s*c\.?", "SMC"),
    (r"h\.?\s*r\.?\s*c\.?", "HRC"),
    (r"crl?\.?\s*a\.?", "CRA"),
    (r"crl?\.?\s*p\.?", "CRP"),
    (r"c\.?\s*a\.?", "CA"),
    (r"c\.?\s*p\.?", "CP"),
]

# One case number: digits, an optional registry letter, as in "5-Q", "43-Q", "1".
# The registry suffix accepts any capital: K/L/P/Q are the Supreme Court's branch
# registries, but other series carry their own (H.R.C. No. 36629-S of 2018), and
# a suffix the parser refuses is a citation that can never be matched.
_NUM = r"0*(\d{1,5})\s*(?:-\s*([A-Z])\b)?"

# "No.", "Nos.", "Number", with or without the dot and space.
_NO = r"(?:nos?\.?|numbers?)?\s*"

# The year: "of 2014", "/2014", "of 2014.", "-2014".
_YEAR = r"(?:\s*(?:of|/|-)\s*)((?:19|20)\d{2})\b"

# A list of numbers: "26-K to 38-K", "06 and 724", "5-Q, 6-Q & 7-Q".
_NUM_LIST = rf"({_NUM}(?:\s*(?:,|&|and|to|-)\s*{_NUM})*)"

_TYPE_ALT = "|".join(f"(?:{p})" for p, _ in _TYPE_PATTERNS)

_CASE_RE = re.compile(
    rf"(?<![A-Za-z])({_TYPE_ALT})\s*{_NO}{_NUM_LIST}{_YEAR}",
    re.IGNORECASE,
)

_SINGLE_NUM_RE = re.compile(_NUM, re.IGNORECASE)
_TYPE_RES = [(re.compile(rf"^(?:{p})$", re.IGNORECASE), code) for p, code in _TYPE_PATTERNS]

_TYPE_DISPLAY = {
    "CA": "Civil Appeal", "CP": "Civil Petition", "CRA": "Criminal Appeal",
    "CRP": "Criminal Petition", "REVP": "Civil Review Petition",
    "CRREVP": "Criminal Review Petition", "CMA": "Civil Misc. Application",
    "CONSTP": "Constitution Petition", "HRC": "Human Rights Case",
    "SMC": "Suo Motu Case", "JP": "Jail Petition",
}


def _type_code(phrase: str) -> str | None:
    """Map a matched case-type phrase onto its normalised code."""
    compact = re.sub(r"\s+", " ", phrase.strip())
    for pattern, code in _TYPE_RES:
        if pattern.match(compact):
            return code
    return None


# Numbers and the word "to", in order, so ranges can be found anywhere in a list.
_LIST_TOKEN_RE = re.compile(rf"{_NUM}|\b(to)\b", re.IGNORECASE)

# A range wider than this is more likely a misread than 50+ connected cases.
_MAX_RANGE = 50


def _expand_list(number_list: str) -> list[tuple[str, str | None]]:
    """Turn "45 and 64 to 70" into 45, 64, 65 … 70.

    Every "a to b" span is expanded wherever it sits in the list, not only when
    the whole list is one range: "Civil Petitions No. 45 and 64 to 70" is a
    single judgment deciding eight petitions, and a citation of any of them must
    find it. A span is expanded only when both ends share a registry letter and
    the width is sane; otherwise just its endpoints are kept.
    """
    tokens: list[object] = []
    for m in _LIST_TOKEN_RE.finditer(number_list):
        if m.group(3):
            tokens.append("to")
        else:
            tokens.append((m.group(1), m.group(2).upper() if m.group(2) else None))

    out: list[tuple[str, str | None]] = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok == "to":
            i += 1
            continue
        nxt = tokens[i + 1] if i + 1 < len(tokens) else None
        end = tokens[i + 2] if i + 2 < len(tokens) else None
        if nxt == "to" and isinstance(end, tuple):
            (lo, reg_lo), (hi, reg_hi) = tok, end
            lo_i, hi_i = int(lo), int(hi)
            if reg_lo == reg_hi and 0 < hi_i - lo_i <= _MAX_RANGE:
                out.extend((str(n), reg_lo) for n in range(lo_i, hi_i + 1))
            else:
                out.extend([tok, end])
            i += 3
            continue
        out.append(tok)
        i += 1
    return out


def make_key(case_type: str, number: str | int, registry: str | None, year: int | str) -> str:
    """Build the canonical key, e.g. ``make_key("CA", 5, "Q", 2014) -> "CA-5-Q-2014"``."""
    number = str(int(str(number)))  # strip leading zeros: "06" -> "6"
    parts = [case_type.upper(), number]
    if registry:
        parts.append(registry.upper())
    parts.append(str(year))
    return "-".join(parts)


def parse_case_numbers(text: str) -> list[dict]:
    """Find every case citation in `text` and normalise it.

    Args:
        text: A judgment header, a user query, anything.

    Returns:
        One dict per case number found, in order of appearance, each with
        ``key``, ``type``, ``number``, ``registry``, ``year`` and ``display``.
        A range ("26-K to 38-K") expands to every number in it when the range
        is small; otherwise only its endpoints are returned.
    """
    if not text:
        return []

    found: list[dict] = []
    seen: set[str] = set()

    for match in _CASE_RE.finditer(text):
        case_type = _type_code(match.group(1))
        if not case_type:
            continue
        year = int(match.group(match.lastindex))
        number_list = match.group(2)

        numbers = _expand_list(number_list)
        if not numbers:
            continue

        for number, registry in numbers:
            key = make_key(case_type, number, registry, year)
            if key in seen:
                continue
            seen.add(key)
            registry_part = f"-{registry.upper()}" if registry else ""
            found.append({
                "key": key,
                "type": case_type,
                "number": str(int(number)),
                "registry": registry.upper() if registry else None,
                "year": year,
                "display": f"{_TYPE_DISPLAY.get(case_type, case_type)} No. "
                           f"{int(number)}{registry_part} of {year}",
            })

    return found


def case_keys(text: str) -> list[str]:
    """Just the normalised keys found in `text`."""
    return [ref["key"] for ref in parse_case_numbers(text)]


if __name__ == "__main__":
    # Every format below was seen in a real header or a real logged query.
    cases = [
        ("CIVIL APPEAL NO. 5-Q OF 2014", ["CA-5-Q-2014"]),
        ("CIVIL APPEAL NO.43-Q OF 2018", ["CA-43-Q-2018"]),
        ("Civil Appeal No. 1 of 2020", ["CA-1-2020"]),
        ("Civil Petition No. 34-Q of 2019", ["CP-34-Q-2019"]),
        ("CIVIL APPEALS NOS.06 AND 724 OF 2016", ["CA-6-2016", "CA-724-2016"]),
        ("Civil Appeals No.26-K to 28-K of 2021", ["CA-26-K-2021", "CA-27-K-2021", "CA-28-K-2021"]),
        ("C.A. 23-P/2017", ["CA-23-P-2017"]),
        ("C.A.23-P/2017", ["CA-23-P-2017"]),
        ("CA 5-Q/2014", ["CA-5-Q-2014"]),
        ("C.P.L.A. 34-Q/2019", ["CP-34-Q-2019"]),
        ("Crl.A. 12-L of 2019", ["CRA-12-L-2019"]),
        ("Criminal Petition No. 99-L of 2020", ["CRP-99-L-2020"]),
        ("Constitution Petition No. 39 of 2019", ["CONSTP-39-2019"]),
        ("Suo Motu Case No. 7 of 2017", ["SMC-7-2017"]),
        ("Civil Petition for Leave to Appeal No. 3-K of 2020", ["CP-3-K-2020"]),
        # Both reported by the metadata extractor on real captions.
        ("CIVIL PETITIONS NO.45 AND 64 TO 70 OF 2018",
         ["CP-45-2018", "CP-64-2018", "CP-65-2018", "CP-66-2018", "CP-67-2018",
          "CP-68-2018", "CP-69-2018", "CP-70-2018"]),
        ("H.R.C. NO. 36629-S OF 2018", ["HRC-36629-S-2018"]),
        # Must find nothing: no case type, or a year outside the window.
        ("bail granted despite murder charges", []),
        ("Article 199 of the Constitution", []),
        ("judgment dated 18.03.2014", []),
        # Header with a lower-court reference: the SC number comes first.
        ("CIVIL APPEAL NO. 23-P OF 2017 (On appeal against the judgment dated "
         "12.05.2017 passed by the Peshawar High Court in Civil Revision No. 699-P/2013)",
         ["CA-23-P-2017"]),
    ]

    failures = 0
    for text, expected in cases:
        got = case_keys(text)
        ok = got[: len(expected)] == expected if expected else got == []
        failures += not ok
        print(f"  {'OK  ' if ok else 'FAIL'} {text[:58]:<58} -> {got}")

    # Both sides of the exact-match contract must agree.
    header = case_keys("IN THE SUPREME COURT ... CIVIL APPEAL NO. 5-Q OF 2014 ...")
    query = case_keys("what did the court hold in C.A. 5-Q/2014")
    assert header == query == ["CA-5-Q-2014"], f"header {header} != query {query}"
    print("\n  header and query normalise to the same key  OK")

    assert failures == 0, f"{failures} case-number formats failed"
    print(f"\nOK: {len(cases)} formats normalised.")
