"""
Broad category queries — "family dispute", "service matter", "legal dispute".

Why these need their own path
-----------------------------
The retrieval pipeline is built to answer a question: find the judgment that
decides THIS point. A category query is not a question. It has either many
right answers or none in particular, and treating it like a question produced
two failures on the same afternoon:

  * "legal dispute" matched boilerplate every judgment shares ("The following
    legal issue arises for determination…"), the cross-encoder scored one case
    0.393, and it was shown as a Strong match — for a phrase that describes
    all eleven judgments equally.
  * "family dispute" scored the dower case 0.005 — the cross-encoder does not
    connect "family" with dower, nikah or a husband's heirs — so the query was
    refused although the archive holds family matters.

Same intent, opposite outcomes: a short generic query gives the cross-encoder
nothing stable to score.

What happens instead
--------------------
`classify(query)` sorts a SHORT query (≤ 5 words) into one of three:

    too_broad   nothing left once generic legal words are removed
                ("legal dispute", "any case") -> refuse, asking for specifics
    category    every remaining word names one category below
                ("family dispute", "election cases") -> browse that category
    None        anything else -> the normal question-answering path

A category is browsed by searching with its terms and keeping only judgments
whose own text contains at least one of them. The evidence test is lexical and
deliberately so: a judgment that never mentions dower, nikah, divorce, legal
heirs or a family settlement is not a family matter, however the scores fall.

The term lists are precise phrases, not loose kinship words: "custody of
minor", not "custody" (an accused is in custody too); "maintenance allowance",
not "maintenance". They are a free-tier stand-in for the LLM analyzer's
rewrite, and the place to add vocabulary as the corpus grows.
"""

import re

# Words that carry no subject on their own. A query made only of these is too
# broad to answer; removing them from a category query leaves the category.
GENERIC = frozenset("""
    a an the of on in for with about regarding related to and or any all some
    show me find give list get search see want need
    legal law laws dispute disputes case cases matter matters issue issues
    judgment judgments judgement judgements decision decisions court courts
    appeal appeals petition petitions suit suits litigation proceedings
    supreme high pakistan type kind kinds sort example examples
""".split())

# key -> words that name the category in a query, and the phrases that show a
# judgment is about it. Phrases are matched case-insensitively on word
# boundaries against the judgment's full text.
CATEGORIES: dict[str, dict] = {
    "family": {
        "label": "family",
        "triggers": {"family", "families", "matrimonial", "marital", "domestic", "marriage"},
        "phrases": [
            "dower", "haq mehr", "nikah", "nikahnama", "nikah nama", "khula", "talaq",
            "divorce", "dissolution of marriage", "maintenance allowance", "custody of minor",
            "guardianship", "family court", "family settlement", "widow", "legal heirs",
            "inheritance", "husband", "wife",
        ],
    },
    "property": {
        "label": "property and land",
        "triggers": {"property", "properties", "land", "lands", "ownership", "title",
                     "possession", "tenancy", "rent", "revenue"},
        "phrases": [
            # Not bare "title" or "possession": every judgment has a case title,
            # and narcotics judgments turn on "possession". Phrases only.
            "mutation", "khasra", "revenue record", "declaration of ownership",
            "recovery of possession", "possession of the land", "sale deed", "tenancy",
            "ejectment", "pre-emption", "evacuee", "proprietary rights",
        ],
    },
    "service": {
        "label": "service",
        "triggers": {"service", "employment", "employee", "employees", "servant", "servants",
                     "civil", "job", "jobs"},
        "phrases": [
            "civil servant", "service tribunal", "promotion", "seniority", "dismissal from service",
            "removal from service", "reinstatement", "departmental inquiry", "regularisation",
            "regularization",
        ],
    },
    "election": {
        "label": "election",
        "triggers": {"election", "elections", "electoral", "poll", "polls", "vote", "votes"},
        "phrases": [
            "election petition", "election tribunal", "returned candidate", "polling", "re-poll",
            "constituency", "representation of the people act",
        ],
    },
    "criminal": {
        "label": "criminal",
        "triggers": {"criminal", "crime", "crimes", "murder", "offence", "offences"},
        "phrases": ["murder", "qatl", "conviction", "acquittal", "sentence", "f.i.r", "fir",
                    "pakistan penal code", "ppc"],
    },
    "bail": {
        "label": "bail",
        "triggers": {"bail"},
        "phrases": ["bail", "pre-arrest", "post-arrest"],
    },
    "tax": {
        "label": "tax",
        "triggers": {"tax", "taxes", "taxation", "customs", "duty"},
        "phrases": ["income tax", "sales tax", "customs duty", "tax assessment", "federal board of revenue"],
    },
    "intellectual_property": {
        "label": "trade mark and intellectual property",
        "triggers": {"trademark", "trademarks", "trade", "mark", "marks", "copyright",
                     "patent", "patents", "brand", "brands", "intellectual"},
        # Not bare "patent": in judgments it usually means obvious ("patent
        # illegality"), and matched an election case.
        "phrases": ["trade mark", "trademark", "copyright", "patent infringement",
                    "patents ordinance", "passing off", "registrar of trade marks"],
    },
    "contract": {
        "label": "contract",
        "triggers": {"contract", "contracts", "agreement", "agreements"},
        "phrases": ["breach of contract", "specific performance", "agreement to sell"],
    },
    "constitutional": {
        "label": "constitutional",
        "triggers": {"constitutional", "constitution", "fundamental", "rights", "writ"},
        "phrases": ["article 199", "article 184", "article 185", "fundamental rights",
                    "writ petition", "constitution petition"],
    },
}

# Only short queries are treated as categories, so a real question that merely
# mentions a category ("family dispute over evacuee land in Tando Adam") still
# goes down the question-answering path.
MAX_CATEGORY_WORDS = 5

_WORD = re.compile(r"[a-z][a-z\-]*")


def _words(query: str) -> list[str]:
    return _WORD.findall((query or "").lower())


def classify(query: str) -> tuple[str | None, str | None]:
    """Return ``("too_broad", None)``, ``("category", key)`` or ``(None, None)``."""
    words = _words(query)
    if not words or len(words) > MAX_CATEGORY_WORDS:
        return None, None

    content = [w for w in words if w not in GENERIC]
    if not content:
        return "too_broad", None

    for key, spec in CATEGORIES.items():
        if all(w in spec["triggers"] for w in content):
            return "category", key
    return None, None


def phrase_pattern(key: str) -> re.Pattern:
    """One compiled alternation of a category's phrases, word-bounded."""
    phrases = sorted(CATEGORIES[key]["phrases"], key=len, reverse=True)
    alternation = "|".join(re.escape(p) for p in phrases)
    return re.compile(rf"(?<![a-z])(?:{alternation})(?![a-z])", re.IGNORECASE)


def matched_phrases(key: str, text: str) -> list[str]:
    """The distinct category phrases found in `text`, for grounding and display."""
    return sorted({m.group(0).lower() for m in phrase_pattern(key).finditer(text or "")})


def search_text(key: str) -> str:
    """The category's phrases as one query string, for BM25 and dense search."""
    return " ".join(CATEGORIES[key]["phrases"])


if __name__ == "__main__":
    cases = [
        ("legal dispute", ("too_broad", None)),
        ("any case", ("too_broad", None)),
        ("family dispute", ("category", "family")),
        ("family disputes", ("category", "family")),
        ("matrimonial matters", ("category", "family")),
        ("election cases", ("category", "election")),
        ("service matter", ("category", "service")),
        ("trade mark cases", ("category", "intellectual_property")),
        # A real question that mentions a category stays on the normal path.
        ("family dispute over evacuee land in Tando Adam", (None, None)),
        ("who owns a brand name after a company is restructured", (None, None)),
        ("imran khan bail case", (None, None)),   # names a person: not a category
        ("case of car selling", (None, None)),
        ("C.A. 57-K/2018", (None, None)),
    ]
    failures = 0
    for query, expected in cases:
        got = classify(query)
        ok = got == expected
        failures += not ok
        print(f"  {'OK  ' if ok else 'FAIL'} {query:<50} -> {got}")

    # Grounding: precise phrases, not loose words.
    assert matched_phrases("family", "the dower deed in the Nikah Nama") == ["dower", "nikah nama"]
    assert matched_phrases("criminal", "the accused remained in custody") == []
    assert matched_phrases("family", "maintenance of the building") == []
    assert matched_phrases("intellectual_property", "a patent illegality in the order") == []
    assert matched_phrases("property", "the case title and possession of narcotics") == []
    print("\n  grounding uses precise phrases  OK")

    assert failures == 0, f"{failures} classification cases failed"
    print(f"\nOK: {len(cases)} queries classified.")
