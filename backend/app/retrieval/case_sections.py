"""
Which legal sections a case is about, and the "Section" filter.

Users asked for two things: every result should say which sections the case
turns on (Section 302 PPC, Section 497 CrPC ...), and the results should be
filterable by section.

Key sections
------------
A judgment's card lists every provision the judgment cites (``statutes``,
parsed from the full text): a median of 3 but up to 100+, most of them cited in
passing. What a case is ABOUT is what its summary talks about, so
``key_sections`` parses the card's issues, headnote and holding (written from
the judgment, grounded against it: case_card.py) and keeps the provisions:
sections, articles and CPC orders, in the order the summary raises them.

The section filter
------------------
``matches_sections(card, typed)``: a case matches when, for every term typed
(comma-separated: "302, 34" means both), one of its provisions (the cited list
plus the key sections) matches that term:

    302          any section 302 (302 PPC, 302(b) PPC, ...)
    302(b)       302(b) only, not 302(c)
    489-F / 489F the lettered section, written either way
    302 PPC      only the PPC's section 302
    Article 199  articles are asked for by name ("Art. 199" too)

Mirrored in frontend/src/user/lib/filters.js (matchesSections), which narrows a
conversation saved without its query; keep the two in step.
"""

from __future__ import annotations

import re

from app.retrieval.statutes import parse_statutes

MAX_KEY_SECTIONS = 6

_PROVISION_RE = re.compile(r"^(Section|Article|Order)\s")

# A canonical provision: kind, number (with any letter), sub-clauses, the rest
# ("PPC", "Income Tax Ordinance 2001", "Rule 1 CPC").
# The letter may lack its hyphen: lists stored by the earlier reader say
# "Section 377B PPC" / "337A(ii)" where the current one says "377-B".
_PARTS_RE = re.compile(r"^(Section|Article|Order)\s+(\d{1,4}(?:-?[A-Z](?![A-Z]))?)((?:\([0-9a-z]{1,4}\))*)\s*(.*)$", re.I)


def _num(value: str) -> str:
    """A section number in one form: "377b" / "377-B" -> "377-B"."""
    value = value.upper()
    return f"{value[:-1].rstrip('-')}-{value[-1]}" if value[-1:].isalpha() else value


def canonical(provision: str) -> str:
    """One spelling per provision: "Section 377B PPC" -> "Section 377-B PPC".
    Anything that is not a provision is returned as it is."""
    p = _PARTS_RE.match(provision or "")
    if not p:
        return provision
    kind = p.group(1).capitalize()
    number = _num(p.group(2))
    if kind != "Section":
        number = number.replace("-", "")   # the Constitution writes Article 10A, 25A, 63A
    return " ".join(x for x in (kind, number + p.group(3).lower(), p.group(4).strip()) if x)


def _canonical_list(items) -> list[str]:
    return list(dict.fromkeys(canonical(s) for s in items if isinstance(s, str)))

# A term the user typed: optional kind word, the number (letter written any
# way), sub-clauses, then any code or Act words.
_TERM_RE = re.compile(
    r"^\s*(?:(sections?|secs?\.?|ss?\.|s\.?|u/s\.?|articles?|arts?\.?|art|orders?)\s*)?"
    r"(\d{1,4})\s*(?:-?\s*([a-z])(?![a-z]))?\s*((?:\(\s*[0-9a-z]{1,4}\s*\))*)\s*(.*?)\s*$",
    re.I,
)

# Words that name the same code in a filter: "Cr.P.C." is "crpc", "Pakistan
# Penal Code" is "ppc", and so on (the same codes as statutes.py).
_CODE_WORDS = {
    "pakistanpenalcode": "ppc", "penalcode": "ppc",
    "codeofcriminalprocedure": "crpc", "criminalprocedurecode": "crpc",
    "codeofcivilprocedure": "cpc", "civilprocedurecode": "cpc",
    "qanuneshahadat": "qso", "qanuneshahadatorder": "qso",
    "controlofnarcoticsubstancesact": "cnsa", "antiterrorismact": "ata",
}


def _compact(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(text or "").lower())


def _code_key(text: str) -> str:
    key = _compact(text)
    return _CODE_WORDS.get(key, key)


def _summary_text(card: dict) -> str:
    issues = card.get("issues") or []
    if isinstance(issues, str):
        issues = [issues]
    return " ".join(str(x) for x in (*issues, card.get("headnote"), card.get("holding")) if x)


def _most_specific(found: list[str]) -> list[str]:
    """Drop a provision when a more specific form of it is listed too."""
    return [s for s in found if not any(o != s and _is_more_specific(o, s) for o in found)]


def key_sections(card: dict) -> list[str]:
    """The provisions the case is about, as its summary names them (at most
    MAX_KEY_SECTIONS), most specific form only: "Section 302(b) PPC" rather than
    both it and "Section 302 PPC"."""
    if not card:
        return []
    found = [s for s in parse_statutes(_summary_text(card)) if _PROVISION_RE.match(s)]
    return _most_specific(found)[:MAX_KEY_SECTIONS]


# Leave to appeal to the Supreme Court: cited by nearly every appeal, it says
# how the case arrived, not what it is about.
_PROCEDURAL = {"Article 185", "Article 185(2)", "Article 185(3)"}
MAX_CITED_SHOWN = 4


def case_sections(card: dict) -> dict:
    """What to show as the case's sections, and where it came from:

    {"sections": [...], "source": "summary"}  the summary names them (what the
                                              case is about)
    {"sections": [...], "source": "cited"}    the summary names none; the first
                                              provisions the judgment cites
                                              (sections before articles), so
                                              the UI says "cited", not "about"
    {"sections": [], "source": ""}            the judgment cites none
    """
    found = key_sections(card)
    if found:
        return {"sections": found, "source": "summary"}
    cited = [s for s in _canonical_list(card.get("statutes") or [])
             if _PROVISION_RE.match(s) and s not in _PROCEDURAL]
    cited.sort(key=lambda s: {"Section": 0, "Order": 1, "Article": 2}[s.split()[0]])   # stable
    cited = _most_specific(cited)[:MAX_CITED_SHOWN]
    return {"sections": cited, "source": "cited" if cited else ""}


def _is_more_specific(a: str, b: str) -> bool:
    """Is `a` the same provision as `b`, said more precisely? More sub-clauses
    ("Section 302(b) PPC" vs "Section 302 PPC"), or the Act's year added
    ("Section 181 Customs Act 1969" vs "Section 181 Customs Act")."""
    pa, pb = _PARTS_RE.match(a), _PARTS_RE.match(b)
    if not pa or not pb or (pa.group(1).lower(), _num(pa.group(2))) != (pb.group(1).lower(), _num(pb.group(2))):
        return False
    subs_a, subs_b = pa.group(3).lower(), pb.group(3).lower()
    rest_a, rest_b = pa.group(4).lower(), pb.group(4).lower()
    more_subs = rest_a == rest_b and subs_a.startswith(subs_b) and len(subs_a) > len(subs_b)
    more_year = subs_a == subs_b and rest_a != rest_b and re.fullmatch(re.escape(rest_b) + r"\s+(18|19|20)\d{2}", rest_a)
    return bool(more_subs or more_year)


def parse_terms(typed: str) -> list[dict]:
    """The filter's terms: "302, 34 PPC" -> two terms. Words that are not a
    provision ("murder") are ignored rather than matching nothing."""
    terms = []
    for raw in re.split(r"[,;]|\band\b|&", str(typed or ""), flags=re.I):
        m = _TERM_RE.match(raw.replace("–", "-"))
        if not m:
            continue
        kind_word = (m.group(1) or "").lower()
        kind = "article" if kind_word.startswith("art") else "order" if kind_word.startswith("order") else "section"
        number = m.group(2) + (f"-{m.group(3).upper()}" if m.group(3) else "")
        subs = re.sub(r"\s+", "", m.group(4) or "").lower()
        rest = re.sub(r"^(?:of\s+(?:the\s+)?)", "", (m.group(5) or "").strip(), flags=re.I)
        terms.append({"kind": kind, "number": number, "subs": subs, "code": _code_key(rest)})
    return terms


def _provision_matches(provision: str, term: dict) -> bool:
    p = _PARTS_RE.match(provision)
    if not p or p.group(1).lower() != term["kind"]:
        return False
    number, subs = _num(p.group(2)), p.group(3).lower()
    if number != term["number"]:
        # A letter is written both ways: "302 b" for 302(b), "9-C" for 9(c).
        base, _, letter = term["number"].partition("-")
        p_base, _, p_letter = number.partition("-")
        typed_letter = letter and not term["subs"] and number == base and subs.startswith(f"({letter.lower()})")
        judgment_letter = (p_letter and not subs and p_base == term["number"]
                           and term["subs"].startswith(f"({p_letter.lower()})"))
        if not (typed_letter or judgment_letter):
            return False
        return _code_ok(p, term)
    if term["subs"] and not subs.startswith(term["subs"]):
        return False
    return _code_ok(p, term)


def _code_ok(p, term: dict) -> bool:
    if term["code"]:
        code = _code_key(p.group(4))
        if term["code"] not in code and code not in term["code"]:
            return False
    return True


def provisions(card: dict) -> list[str]:
    """Every provision a case involves: what the judgment cites, plus what its
    summary names (which also catches sections the citation list missed)."""
    cited = [s for s in _canonical_list(card.get("statutes") or []) if _PROVISION_RE.match(s)]
    seen = set(cited)
    return cited + [s for s in (card.get("key_sections") or key_sections(card)) if s not in seen]


def matches_sections(card: dict, typed: str) -> bool:
    """Does the case involve every section typed? Empty or unreadable input
    never excludes."""
    terms = parse_terms(typed)
    if not terms:
        return True
    card = card or {}
    # A card from the results (orchestrator._cards_for) carries its provisions
    # already; a raw case_cards document is worked out here.
    have = card.get("provisions") or provisions(card)
    return all(any(_provision_matches(p, t) for p in have) for t in terms)


# ── Sections named in a search query ─────────────────────────────────────────
#
# "pre arrest bail in 377", "bail u/s 302/34", "377 PPC", "section 9(c) CNSA".
# The search ranked by similarity of wording, and its models treat 337, 377
# and 379 as near-identical tokens: asked about 377, it showed a 337-H case as
# its "Strong match". A query that names a section therefore gets the
# judgments that involve that section first (pipeline_v2, "Section-aware
# search"). Reading a section from a bare number is deliberately cautious.

_CODE_WORD = (r"(?:p\.?\s*p\.?\s*c\.?|cr\.?\s*p\.?\s*c\.?|c\.?\s*p\.?\s*c\.?|q\.?\s*s\.?\s*o\.?|c\.?\s*n\.?\s*s\.?\s*a\.?"
              r"|ata\b|pakistan\s+penal\s+code|code\s+of\s+criminal\s+procedure|code\s+of\s+civil\s+procedure)")
_NUMBER = r"(\d{1,3}(?:\s*-\s*[a-z](?![a-z])|[a-z](?![a-z]))?(?:\s*\(\s*[0-9a-z]{1,4}\s*\))*)(?![\d/])"
# Not a section: "under 18 years", "in 3 months", "377-P/2020" (a case number).
_NOT_AFTER = (r"(?!\s*(?:years?|yrs?|months?|days?|hours?|acres?|kanals?|marlas?|rupees|rs\b|%|percent|persons?|people"
              r"|of\s+\d{4}|/\s*\d|-\s*[a-z]{0,2}\s*/))")
_STRONG_RE = re.compile(rf"\b(?:sections?|secs?\.?|ss?\.|u/s\.?)\s*{_NUMBER}{_NOT_AFTER}"
                        rf"(?:\s*(?:/\s*\d{{1,3}}[a-z]?(?:\s*\([0-9a-z]{{1,4}}\))*\s*)*,?\s*(?:of\s+(?:the\s+)?)?({_CODE_WORD}))?", re.I)
_CODED_RE = re.compile(rf"\b{_NUMBER}\s*,?\s*(?:of\s+(?:the\s+)?)?({_CODE_WORD})", re.I)
_WEAK_RE = re.compile(rf"\b(?:in|under|of)\s+(\d{{2,3}}(?:\s*-\s*[a-z](?![a-z])|[a-z](?![a-z]))?)(?![\d/]){_NOT_AFTER}", re.I)
# A bare "in 377" is a section only in a criminal-law query.
_CRIMINAL_CONTEXT = re.compile(r"\b(bail|fir|offen[cs]e|accused|convict\w*|charge\w*|sentenc\w*|acquit\w*|arrest\w*|"
                               r"murder|qatl|trial|prosecution|complainant|police|ppc|crpc|penal)\b", re.I)
# "Article 120 of the Limitation Act", "Article 17 of the Qanun-e-Shahadat
# Order": articles of another law. The stored provisions say only "Article
# 120", which would match the Constitution's Article 120, so such a reference
# is not used to rank (a constitutional or a bare "Article N" is).
_OTHER_LAW_ARTICLE_RE = re.compile(
    r"\b(?:articles?|arts?\.)\s*(\d{1,3}[A-Z]?)(?:\s*\(\s*[0-9a-z]{1,4}\s*\))*\s*,?\s*of\s+(?!(?:the\s+)?constitution)(?:the\s+)?[a-z]",
    re.I)
# "u/s 302/34": the numbers after the first share its code.
_SLASHED_RE = re.compile(r"/\s*(\d{1,3}(?:\s*-\s*[a-z](?![a-z])|[a-z](?![a-z]))?(?:\s*\([0-9a-z]{1,4}\))*)", re.I)


def query_sections(text: str) -> list[dict]:
    """The sections a search query names, as filter terms (parse_terms shape)
    plus a "label" for messages ("Section 377 PPC", "Section 377").
    Case numbers, years and quantities are not sections."""
    text = str(text or "")
    found: list[dict] = []

    def add(number: str, code: str = "", kind: str = "section") -> None:
        for term in parse_terms(f"{'article ' if kind == 'article' else ''}{number} {code}".strip()):
            term["kind"] = kind if kind != "section" else term["kind"]
            label_code = {"ppc": "PPC", "crpc": "CrPC", "cpc": "CPC", "qso": "QSO", "cnsa": "CNSA",
                          "ata": "ATA"}.get(term["code"]) or code.strip()
            number_text = term["number"] + term["subs"]
            term["label"] = " ".join(x for x in ((kind.capitalize() if kind != "order" else "Order"), number_text, label_code) if x)
            if not any((t["kind"], t["number"], t["subs"]) == (term["kind"], term["number"], term["subs"])
                       and (t["code"] == term["code"] or not term["code"]) for t in found):
                # a coded reading replaces a bare one of the same section
                found[:] = [t for t in found if not ((t["kind"], t["number"], t["subs"]) ==
                                                     (term["kind"], term["number"], term["subs"]) and not t["code"])]
                found.append(term)

    # Whatever the full section reader recognises (Article 199, Order 39 Rule 1,
    # Section 122 Income Tax Ordinance 2001, Sections 448/380 PPC ...).
    other_law = {m.group(1).upper() for m in _OTHER_LAW_ARTICLE_RE.finditer(text)}
    for s in parse_statutes(text):
        p = _PARTS_RE.match(s)
        if p and not (p.group(1).lower() == "article" and p.group(2).upper() in other_law):
            add(p.group(2) + p.group(3), p.group(4), p.group(1).lower())

    for m in _STRONG_RE.finditer(text):
        add(m.group(1), m.group(2) or "")
        tail = text[m.start(1) + len(m.group(1)): m.end()]
        for s in _SLASHED_RE.finditer(tail):
            add(s.group(1), m.group(2) or "")
    for m in _CODED_RE.finditer(text):
        add(m.group(1), m.group(2))
    if _CRIMINAL_CONTEXT.search(text):
        for m in _WEAK_RE.finditer(text):
            add(m.group(1))
    return found


# Which judgments involve which provisions: every case card, read once and
# kept for INDEX_TTL_S (a re-ingested or new card is seen within that time).
INDEX_TTL_S = 600
_index: dict = {"at": 0.0, "cards": {}}


def _load_index(cards: list[dict]) -> dict[str, dict]:
    return {c["judgment_id"]: {"all": provisions(c), "key": set(key_sections(c))}
            for c in cards if c.get("judgment_id")}


async def judgments_with_sections(terms: list[dict]) -> dict[str, int]:
    """{judgment_id: strength} of the judgments that involve EVERY term:
    2 when the case's summary names the section (the case is about it), 1 when
    the judgment only cites it."""
    import asyncio
    import time
    from app.database import db

    if not terms or db.database is None:
        return {}
    if time.monotonic() - _index["at"] > INDEX_TTL_S or not _index["cards"]:
        cards = [c async for c in db.database.case_cards.find(
            {}, {"_id": 0, "judgment_id": 1, "statutes": 1, "issues": 1, "headnote": 1, "holding": 1})]
        _index["cards"] = await asyncio.to_thread(_load_index, cards)
        _index["at"] = time.monotonic()
    out: dict[str, int] = {}
    for jid, entry in _index["cards"].items():
        strengths = []
        for term in terms:
            matching = [p for p in entry["all"] if _provision_matches(p, term)]
            if not matching:
                break
            strengths.append(2 if any(p in entry["key"] for p in matching) else 1)
        else:
            out[jid] = min(strengths)
    return out


def query_without_sections(text: str) -> str:
    """The query with its section references taken out: what else it asks.
    "pre-arrest bail section 377 PPC" -> "pre-arrest bail"."""
    from app.retrieval import statutes as st
    text = str(text or "")
    patterns = [_STRONG_RE, _CODED_RE, st._SECTION_LIST_RE, st._SECTION_OF_ACT_RE, st._SECTION_RE,
                st._ARTICLE_RE, st._ORDER_RULE_RE]
    if _CRIMINAL_CONTEXT.search(text):
        patterns.append(_WEAK_RE)
    spans = sorted((m.start(), m.end()) for p in patterns for m in p.finditer(text))
    out, at = [], 0
    for start, end in spans:
        if start >= at:
            # "writ under Article 199 against" -> "writ against": a connector
            # left before the section goes with it.
            out.append(re.sub(r"\b(?:in|under|of|u/s)\s*$", "", text[at:start], flags=re.I))
            at = end
        else:
            at = max(at, end)
    out.append(text[at:])
    rest = re.sub(r"\s+", " ", " ".join(out)).strip(" ,;:-")
    # Connectors left hanging where a section was: "bail in" -> "bail".
    return re.sub(r"\s+\b(?:in|under|of|u/s|and|the)$", "", rest, flags=re.I).strip()


def sections_label(terms: list[dict]) -> str:
    """"Section 377 PPC", "Sections 302 PPC and 34 PPC" for a message."""
    labels = [t.get("label") or t["number"] for t in terms]
    if len(labels) == 1:
        return labels[0]
    return ", ".join(labels[:-1]) + " and " + labels[-1]


if __name__ == "__main__":
    card = {
        "statutes": ["Article 185(3)", "Section 302(b) PPC", "Section 34 PPC", "Section 342 CrPC"],
        "issues": ["Whether the conviction under section 302(b) PPC was proved beyond doubt"],
        "holding": "Bail under section 497(2) Cr.P.C. was refused; section 489-F PPC was not attracted.",
    }
    ks = key_sections(card)
    assert ks == ["Section 302(b) PPC", "Section 497(2) CrPC", "Section 489-F PPC"], ks
    yes = ["302", "section 302", "s. 302 PPC", "302(b)", "302 (b) Pakistan Penal Code", "34",
           "302, 34", "302 and 34 PPC", "489-F", "489F", "489 F", "497(2) Cr.P.C.", "Article 185(3)",
           "art. 185", "murder", "", "u/s 302 PPC", "302 b", "302-B PPC"]
    no = ["302(c)", "302 CrPC", "377", "302, 377", "Article 199", "489-G", "section 185"]
    for t in yes:
        assert matches_sections(card, t), f"should match: {t!r}"
    for t in no:
        assert not matches_sections(card, t), f"should NOT match: {t!r}"
    other = {"issues": ["Whether section 144(4) of the Elections Act, 2017 requires personal verification"]}
    assert key_sections(other) == ["Section 144(4) Elections Act 2017"], key_sections(other)
    assert matches_sections(other, "144 Elections Act") and not matches_sections(other, "144 CrPC")
    dup = {"holding": "Section 181 of the Customs Act, 1969 applies, and section 181 of the Customs Act was misread."}
    assert key_sections(dup) == ["Section 181 Customs Act 1969"], key_sections(dup)
    listed = {"headnote": "a case registered under Sections 448/380 PPC"}
    assert key_sections(listed) == ["Section 448 PPC", "Section 380 PPC"], key_sections(listed)
    # No section in the summary: the judgment's own citations, labelled "cited",
    # sections first, leave-to-appeal left out.
    quiet = {"statutes": ["Article 185(3)", "Article 226", "Section 497 CrPC", "Section 438 CrPC"],
             "headnote": "The bail was granted without exceptional circumstances."}
    assert case_sections(quiet) == {"sections": ["Section 497 CrPC", "Section 438 CrPC", "Article 226"],
                                    "source": "cited"}, case_sections(quiet)
    assert case_sections({"headnote": "nothing"}) == {"sections": [], "source": ""}
    cnsa = {"statutes": ["Section 9-C CNSA"]}
    assert matches_sections(cnsa, "9(c) CNSA") and matches_sections(cnsa, "9-C") and matches_sections(cnsa, "9c")
    # A lettered section is its own section: 489-F (cheque) is not 489 (currency notes).
    assert not matches_sections({"statutes": ["Section 489-F PPC"]}, "489")
    assert not matches_sections(cnsa, "9(b)")

    # Old spellings: 377B is section 377-B (sexual abuse), not section 377.
    old = {"statutes": ["Section 377B PPC", "Section 337A(ii) PPC"]}
    assert provisions(old) == ["Section 377-B PPC", "Section 337-A(ii) PPC"], provisions(old)
    assert matches_sections(old, "377-B") and matches_sections(old, "377b") and matches_sections(old, "337-A")
    assert not matches_sections(old, "377") and not matches_sections(old, "377 PPC") and not matches_sections(old, "337")
    assert canonical("Article 10-A") == "Article 10A" and canonical("Article 184(3)") == "Article 184(3)"
    assert matches_sections({"statutes": ["Article 10A"]}, "Article 10A") and matches_sections({"statutes": ["Article 10A"]}, "art 10-A")

    # Sections named in a search query.
    def labels(q):
        return [t["label"] for t in query_sections(q)]
    expect = {
        "pre arrest bail in 377": ["Section 377"],
        "pre-arrest bail section 377 PPC": ["Section 377 PPC"],
        "bail u/s 302/34 PPC": ["Section 302 PPC", "Section 34 PPC"],
        "pre arrest bail 337 PPC": ["Section 337 PPC"],
        "dishonour of cheque under section 489-F PPC": ["Section 489-F PPC"],
        "Section 9(c) CNSA narcotics bail": ["Section 9(c) CNSA"],
        "writ under Article 199": ["Article 199"],
        "Article 199 of the Constitution": ["Article 199"],
        "suit barred under Article 120 of the Limitation Act": [],
        "evidence under Article 17 of the Qanun-e-Shahadat Order": [],
        "reopening under section 122 of the Income Tax Ordinance, 2001": ["Section 122 Income Tax Ordinance 2001"],
        # Not sections:
        "Criminal Petition No. 1117 of 2024": [],
        "C.P. 377-P/2020 conveyance allowance": [],
        "minor girl under 18 years rape bail": [],
        "general elections 2013 National Assembly seat NA-266": [],
        "NAB case on bail nab ordinance": [],
        "teachers conveyance allowance in 377 cases": [],   # no criminal context: not a section
    }
    for q, want in expect.items():
        got = labels(q)
        assert got == want, (q, got, want)
    rests = {
        "pre arrest bail in 377": "pre arrest bail",
        "pre-arrest bail section 377 PPC": "pre-arrest bail",
        "bail u/s 302/34 PPC": "bail",
        "section 302 PPC": "",
        "writ under Article 199 against a private school": "writ against a private school",
        "reopening under section 122 of the Income Tax Ordinance, 2001": "reopening",
    }
    for q, want in rests.items():
        got = query_without_sections(q)
        assert got == want, (q, got, want)
    assert case_sections(card)["source"] == "summary"
    print(f"OK: key sections, and {len(yes)} matching / {len(no)} non-matching filter inputs.")
