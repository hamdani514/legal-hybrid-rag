"""
Query understanding: turn the words a lawyer typed into a QueryAnalysis.

Why this exists
---------------
Precision differs wildly by kind of question. A citation ("C.A. 5-Q/2014") is
answered by exact match; a statute ("Article 199") by lexical match on a rare
token; a paraphrase ("who owns a brand after a company is restructured") shares
no vocabulary with the judgment at all and scores ~40% p@1 today. Treating all
of them as one bare string is most of the loss. Every retriever therefore gets
a QueryAnalysis (app.retrieval.contracts) instead: the type of question, the
entities in it, and a restatement in the vocabulary a Supreme Court judgment
would actually use.

Two paths
---------
1. Regex fast path — always runs, no network. Case numbers come from
   case_keys.parse_case_numbers and statutes from statutes.parse_statutes (the
   only parsers of each, so query and judgment normalise identically), plus
   years, the registry implied by a city name, and an outcome when the query
   asks about one. A heuristic picks the query type. If a case number is found
   the query is a citation and the LLM is skipped: exact match will answer it.
2. One LLM call (JSON) — the query type, party names, subject area, outcome,
   a legal-language rewrite and 0-2 expansions. The rewrite is the main lever
   for paraphrase queries.

Never trust, never block
------------------------
An LLM asked to "restate in legal language" will happily add a party, a case
number or "Section 9 CPC" that the user never wrote, and retrieval would then
chase facts nobody asked about. So the prompt forbids it AND the output is
validated: types and subjects must be in the fixed vocabularies, any party not
present in the raw query is dropped, and a rewrite/expansion that introduces a
case number, statute or number absent from the query is discarded (the raw
query stands in for a rejected rewrite).

The LLM is wrapped in asyncio.wait_for (QUERY_ANALYZER_TIMEOUT, default 3s).
On timeout or any failure the regex-only analysis is returned with
source="regex", so search never waits on Gemini. Successful analyses are
cached in an in-memory LRU keyed by the normalised query; failures are not
cached, so a transient outage does not pin a degraded answer.

Case descriptions (narratives)
------------------------------
Users increasingly describe their whole case in 40-150 words: what happened,
what each side says, what the courts held, how it ended. A query of
NARRATIVE_MIN_WORDS+ words is marked ``is_narrative`` and split into
``facets`` (contracts.Facets) so retrieval can match each part of the story
against the part of a judgment that discusses it (facts -> FACTS, each side's
case -> ARGUMENTS, the court's view -> ANALYSIS_RATIO, outcome -> FINAL_ORDER).

The free-tier splitter (split_facets) is cue-based and works on the RAW text,
clause by clause, keeping the user's own words:

    court_view  a clause naming a court/forum next to a decision verb ("the
                High Court held", "the tribunal dismissed", "the courts held
                my suit was time-barred"), or any clause stating an outcome
    respondent  an other-side cue ("the other side argues", "the opposite
                party", "the respondent says", "they claim"); in a first-person
                story, a third person's claim ("his wife claims") is also the
                other side's
    claimant    a first-person or appellant cue with a claim verb ("my client
                says", "we argued", "I claimed", "the appellant contends"), or
                a third person's claim when the story is not first-person
    facts       everything else, in order

outcome_sc — the outcome the SUPREME COURT reached — is deliberately narrow,
because a lower court's result usually points the other way (the SC reverses
or upholds it). It is set only when either
    (a) a clause attributes the outcome to the Supreme Court ("the Supreme
        Court allowed his appeal", "this Court set aside", "the apex court
        dismissed") — the last such clause wins; or
    (b) the LAST outcome stated in the story is about an appeal/petition, names
        no lower forum (High Court, tribunal, trial/appellate court,
        department, registrar ...), is not a departmental appeal, and comes
        after the story has mentioned the Supreme Court ("we appealed to the
        Supreme Court. The appeal was dismissed.").
Anything else leaves outcome_sc absent. For narratives, the analysis'
``outcome`` is outcome_sc (the regex outcome, which takes the first label by
priority regardless of which court, is not used for them).

When the LLM path runs on a narrative, the same call also returns facets; they
are validated to be (near-)verbatim substrings of the query and replace the
regex facets key by key. The free tier never depends on the LLM.
"""

import asyncio
import copy
import json
import re
import sys
import time
from collections import OrderedDict
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from loguru import logger

from app.config import settings
from app.retrieval import llm_responder  # light: config + LLM SDKs, no Chroma/Mongo
from app.retrieval.case_keys import parse_case_numbers
from app.retrieval.contracts import NARRATIVE_MIN_WORDS, QUERY_TYPES, SUBJECT_AREAS, Facets, QueryAnalysis
from app.retrieval.statutes import parse_statutes

# ── Settings (read lazily so tests and the integrator can change them) ───────
DEFAULT_TIMEOUT = 3.0
DEFAULT_CACHE_SIZE = 1024
MAX_TOKENS = 450


def _timeout() -> float:
    return float(getattr(settings, "QUERY_ANALYZER_TIMEOUT", DEFAULT_TIMEOUT))


def _cache_size() -> int:
    return int(getattr(settings, "QUERY_ANALYZER_CACHE_SIZE", DEFAULT_CACHE_SIZE))


def _llm_enabled() -> bool:
    return bool(getattr(settings, "QUERY_ANALYZER_USE_LLM", True))


def _facets_enabled() -> bool:
    return bool(getattr(settings, "NARRATIVE_FACETS", True))


def _narrative_timeout() -> float:
    # A narrative call returns the user's facets too: more output tokens, so a
    # longer budget than a short query's rewrite. Still bounded; regex on expiry.
    return float(getattr(settings, "QUERY_ANALYZER_NARRATIVE_TIMEOUT", max(_timeout(), 6.0)))


# ── Regex vocabulary ─────────────────────────────────────────────────────────
_YEAR_RE = re.compile(r"\b(19[4-9]\d|20[0-3]\d)\b")
_MIN_YEAR, _MAX_YEAR = 1947, 2030

# Supreme Court registries. Islamabad is the principal seat and carries no
# registry suffix in case numbers, so it maps to None deliberately.
_REGISTRY_WORDS = {"karachi": "K", "lahore": "L", "peshawar": "P", "quetta": "Q", "islamabad": None}
_CITY_RE = re.compile(r"\b(karachi|lahore|peshawar|quetta|islamabad)\b", re.IGNORECASE)

# Outcome phrases, most specific first. An outcome word only counts when a
# proceeding noun precedes it within a few words ("civil revision dismissed",
# "bail was granted"): "rejected ballot papers" or "land granted" describe
# facts, not an outcome. "decline"/"refuse" are left out: in queries they
# almost always pose a question ("when will the Court decline leave").
_PROCEEDING = (
    r"\b(?:appeals?|petitions?|applications?|revisions?|suits?|bail|leave|case|conviction|"
    r"sentence|order|judgments?|judgements?|decrees?|claims?|plea|reference|accused|convict|"
    r"writ|complaint|objection)\b(?:\W+\w+){0,4}?\W+"
)
_OUTCOME_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(_PROCEEDING + r"(?:partly|partially)\W*(?:allowed|accepted|granted)\b", re.I), "partly_allowed"),
    (re.compile(_PROCEEDING + r"(?:remand(?:ed)?|sent back|remitted)\b", re.I), "remanded"),
    (re.compile(_PROCEEDING + r"disposed of\b", re.I), "disposed"),
    (re.compile(_PROCEEDING + r"(?:dismissed|rejected|upheld|maintained)\b", re.I), "dismissed"),
    (re.compile(_PROCEEDING + r"(?:allowed|accepted|granted|set aside|reversed|acquitted)\b", re.I), "allowed"),
]

# Words that make up a disposition-style query ("appeal dismissed with no order
# as to costs"). When nearly every content word is one of these, the user is
# asking about an outcome rather than a subject.
_DISPOSITION_VOCAB = {
    "appeal", "appeals", "petition", "petitions", "allowed", "dismissed", "accepted", "rejected",
    "costs", "cost", "order", "impugned", "judgment", "judgement", "set", "aside", "remanded",
    "remand", "parties", "bearing", "own", "merit", "merits", "want", "disposed", "partly",
    "partially", "leave", "granted", "refused", "upheld", "maintained", "reversed", "converted",
    "fresh", "decision", "decided", "orders", "sentence", "acquitted", "acquittal", "no",
}

_STOPWORDS = {
    "a", "an", "the", "of", "in", "on", "for", "to", "by", "with", "and", "or", "as", "at",
    "is", "was", "be", "under", "about", "from", "into", "that", "this", "its", "it", "any",
    "where", "which", "who", "what", "case", "cases",
}

# Generic words that, on their own, describe a category rather than a question.
_GENERIC_WORDS = {
    "legal", "dispute", "disputes", "issue", "issues", "matter", "matters", "case", "cases",
    "family", "families", "between", "the", "a", "an", "any", "of", "on", "some", "court",
    "law", "car", "selling", "property", "land", "service", "tribunal", "appeal", "criminal",
    "civil", "about", "related", "regarding", "for", "judgment", "judgments",
}

_CHITCHAT_RE = re.compile(
    r"^\s*(h+i+|hello+|hey+|ok+y*|okay+|thanks?|thank you|got it|yes|no|test)\W*\s*$", re.I
)

_QUESTION_START = {
    "whether", "was", "is", "are", "were", "can", "could", "what", "why", "when", "who",
    "whom", "how", "did", "does", "do", "should", "may", "must", "will", "would", "which",
    "has", "have", "had", "shall",
}

_VS_RE = re.compile(r"^\s*(.+?)\s+(?:vs\.?|versus|v\.|v)\s+(.+?)\s*$", re.I)

_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'\-]*")


def _words(text: str) -> list[str]:
    return [w.lower() for w in _WORD_RE.findall(text)]


def _normalise(text: str) -> str:
    """Lowercase, alphanumerics only, single spaces — for cache keys and grounding checks."""
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", (text or "").lower())).strip()


def _clean(raw: str) -> str:
    # Agent C owns clean_query and is changing it; import at call time so this
    # module always uses the current version, and never fails if it is broken.
    try:
        from app.retrieval.query_preprocessor import clean_query
        return clean_query(raw)
    except Exception as e:  # pragma: no cover - defensive
        logger.warning(f"clean_query failed, using a whitespace-normalised query: {e}")
        return re.sub(r"\s+", " ", raw).strip().lower()


# ── Regex path ───────────────────────────────────────────────────────────────
def _outcome(text: str) -> str | None:
    for pattern, outcome in _OUTCOME_PATTERNS:
        if pattern.search(text):
            return outcome
    return None


def _registry(text: str, case_refs: list[dict]) -> str | None:
    for ref in case_refs:
        if ref.get("registry"):
            return ref["registry"]
    found = {_REGISTRY_WORDS[m.group(1).lower()] for m in _CITY_RE.finditer(text)}
    found.discard(None)
    return found.pop() if len(found) == 1 else None


def _years(text: str, statutes: list[str]) -> list[int]:
    # A year inside a statute ("Family Courts Act 1964") is the Act's year, not
    # a decision year; counting it would filter on the wrong thing.
    statute_years = {int(y) for s in statutes for y in _YEAR_RE.findall(s)}
    years: list[int] = []
    for y in (int(m) for m in _YEAR_RE.findall(text)):
        if _MIN_YEAR <= y <= _MAX_YEAR and y not in statute_years and y not in years:
            years.append(y)
    return years


def _regex_parties(raw: str) -> list[str]:
    """Only the unambiguous "X vs Y" form; anything subtler is left to the LLM."""
    m = _VS_RE.match(raw)
    if not m:
        return []
    return [p.strip(" .,") for p in (m.group(1), m.group(2)) if p.strip(" .,")]


def heuristic_type(raw: str, case_refs: list, statutes: list, outcome: str | None) -> str:
    """Cheap query-type guess, used when the LLM is skipped, disabled or fails."""
    if case_refs:
        return "citation"
    if _CHITCHAT_RE.match(raw):
        return "unknown"
    words = _words(raw)
    if not words:
        return "unknown"
    is_question = words[0] in _QUESTION_START or raw.strip().endswith("?")
    if statutes and not is_question and len(words) <= 10:
        return "statute"
    if _VS_RE.match(raw):
        return "entity"
    content = [w for w in words if w not in _STOPWORDS]
    if outcome and content:
        share = sum(w in _DISPOSITION_VOCAB for w in content) / len(content)
        if share >= 0.6:
            return "disposition"
    if not statutes and len(words) <= 5 and all(w in _GENERIC_WORDS for w in words):
        return "vague"
    if is_question:
        return "issue"
    return "paraphrase"


# ── Narrative facets (free tier, cue-based) ──────────────────────────────────

def is_narrative(raw: str) -> bool:
    """A case description rather than a short question: NARRATIVE_MIN_WORDS+ words."""
    return len((raw or "").split()) >= NARRATIVE_MIN_WORDS


# Abbreviations whose full stop does not end a sentence.
_ABBREV = re.compile(r"\b(?:mr|mrs|ms|mst|dr|no|nos|s|art|sec|ss|vs|v|st|jr|sr|ltd|pvt|co|govt|u)\.\s*$", re.I)
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[\"'(\[]?[A-Z0-9])")

_FORUM = (r"(?:supreme\s+court|apex\s+court|this\s+court|high\s+court|trial\s+court|appellate\s+court|"
          r"sessions?\s+court|district\s+court|family\s+court|civil\s+court|lower\s+courts?|courts?\s+below|"
          r"(?:\w+\s+){0,3}tribunal|tribunals|courts?|registrar|bench|board|commissioner|ombudsman|"
          r"magistrate|judge|inquiry\s+officer|inspector\s+general(?:\s+of\s+police)?|competent\s+authority|"
          r"departmental\s+authority|appellate\s+authority|authority|rent\s+controller|controller|collector)")
_DECISION_VERB = (r"(?:held|holds|hold|decided|decides|ruled|rules|found|finds|decreed|decrees|dismissed|"
                  r"dismisses|allowed|allows|upheld|upholds|reversed|reverses|accepted|accepts|rejected|"
                  r"rejects|ordered|orders|agreed|agrees|restored|restores|refused|refuses|reinstated|"
                  r"set\s+aside|sets\s+aside|maintained|maintains|granted|grants|convicted|acquitted|"
                  r"remanded|remitted|declined|declines|concluded|observed|disagreed|said|says|"
                  r"directed|declared|struck\s+down|quashed|endorsed|confirmed|affirmed|modified|reduced)")
# "the High Court held", "the Federal Service Tribunal dismissed my appeal",
# "the courts held", "the Registrar and the High Court allowed".
_COURT_ACTS = re.compile(
    rf"\b{_FORUM}\b(?:\W+\w+){{0,5}}?\W+(?:also\s+|then\s+|later\s+|however\s+|both\s+)?{_DECISION_VERB}\b"
    rf"|\b{_DECISION_VERB}\s+by\s+the\s+{_FORUM}\b"
    rf"|\bruled\s+in\s+(?:his|her|their|our|my|its)\s+favou?r\b"
    rf"|\b(?:lost|won)\s+(?:\w+\s+){{0,2}}(?:in|before|at)\s+the\s+{_FORUM}\b",
    re.I)
_SUPREME = re.compile(r"\b(?:supreme\s+court|apex\s+court|this\s+court|honou?rable\s+supreme|s\.?c\.?(?=\s))\b", re.I)
_LOWER_FORUM = re.compile(
    r"\b(?:high\s+court|trial\s+court|appellate\s+court|sessions?\s+court|district\s+court|family\s+court|"
    r"civil\s+court|lower\s+courts?|courts?\s+below|tribunal|registrar|department|departmental|inspector|"
    r"commissioner|board|authority|magistrate|ombudsman|inquiry|competent\s+authority|ministry)\b", re.I)

_CLAIM_VERB = (r"(?:says?|said|saying|claiming|argue[sd]?|arguing|claim(?:s|ed)?|contend(?:s|ed)?|maintain(?:s|ed)?|"
               r"allege[sd]?|insist(?:s|ed)?|plead(?:s|ed)?|pleaded|believe[sd]?|assert(?:s|ed)?|"
               r"submit(?:s|ted)?|den(?:y|ies|ied)|object(?:s|ed)?|stance|position|case\s+is|"
               r"appealed(?:\s+\w+){0,3}\s+saying|appealed|challenged|sought|seek(?:s)?|prayed|asked)")
_OTHER_SIDE = re.compile(
    rf"\b(?:the\s+other\s+side|other\s+party|opposite\s+(?:party|side)|opposing\s+(?:party|side|counsel)|"
    rf"the\s+respondents?|respondent\s+side|the\s+defendants?|the\s+complainant|the\s+prosecution|"
    rf"the\s+government|the\s+department|the\s+province|the\s+state|the\s+federation|the\s+ministry|"
    rf"they|the\s+other\s+company|the\s+opposition)\b(?:\W+\w+){{0,4}}?\W+{_CLAIM_VERB}\b",
    re.I)
_FIRST_PERSON_CLAIM = re.compile(
    rf"\b(?:i|we|my\s+clients?|our\s+clients?|our\s+side|my\s+side|the\s+appellants?|the\s+petitioners?|"
    rf"the\s+plaintiffs?)\b(?:\W+\w+){{0,3}}?\W+{_CLAIM_VERB}\b",
    re.I)
# "He says ..." in a story about "my client" is the client's own case; "his
# wife claims ..." in a story told by the heirs is the other side's.
_PRONOUN_CLAIM = re.compile(rf"\b(?:he|she)\b(?:\W+\w+){{0,3}}?\W+{_CLAIM_VERB}\b", re.I)
_THIRD_PERSON_CLAIM = re.compile(
    rf"\b(?:his\s+\w+|her\s+\w+|their\s+\w+|the\s+accused|the\s+candidate|the\s+employee|"
    rf"the\s+tenants?|the\s+landlord|the\s+seller|the\s+buyer|the\s+purchaser|the\s+husband|"
    rf"the\s+wife|the\s+heirs|the\s+allottees?|the\s+co-?owners?|the\s+company|the\s+bank|"
    rf"the\s+employer|the\s+losing\s+candidate|the\s+returned\s+candidate)\b"
    rf"(?:\W+\w+){{0,3}}?\W+{_CLAIM_VERB}\b",
    re.I)
_CLIENT_STORY = re.compile(r"\b(?:my|our)\s+clients?\b", re.I)
_PASSIVE_OUTCOME = re.compile(r"\b(?:appeals?|petitions?|suits?|revisions?|applications?|claims?|case)\s+"
                              r"(?:\w+\s+)?(?:was|were|got|has\s+been|have\s+been|is)\s+(?:\w+\s+)?"
                              r"(?:dismissed|rejected|allowed|accepted|upheld|set\s+aside|remanded|"
                              r"refused|granted|reversed|restored|disposed)\b", re.I)
_FIRST_PERSON = re.compile(r"\b(?:i|we|my|our|me|us)\b", re.I)

# Clause boundaries inside a sentence: ";", "but", "whereas", "however", and a
# comma/"and" before a new forum ("..., the appellate court reversed it, and
# the High Court restored the decree").
_CLAUSE_SPLIT = re.compile(
    r"\s*;\s*|\s*,?\s+\bbut\b\s+|\s*,?\s+\bwhereas\b\s+|\s*,?\s+\bhowever\b,?\s+|\s*,?\s+\bwhile\b\s+"
    r"|\s*,\s*(?:and\s+)?(?=(?:the|a|his|her|their|our|my)\s+(?:[\w-]+\s+){0,3}"
    r"(?:court|courts|tribunal|registrar|bench|board|commissioner|authority)\b)"
    r"|\s+and\s+(?=the\s+(?:[\w-]+\s+){0,3}(?:court|courts|tribunal|registrar)\b)"
    r"|\s+and\s+(?=(?:we|i|they)\s+(?:\w+\s+)?(?:appealed|filed|challenged|went|moved)\b)",
    re.I)
# A forum named in a clause, to decide WHICH court an outcome belongs to.
_ANY_FORUM = re.compile(rf"\b{_FORUM}\b", re.I)

# Outcome verbs, for outcome_sc. Order matters: the more specific first.
_SC_OUTCOME: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\b(?:partly|partially)\W*(?:allowed|accepted|granted|set\s+aside)\b", re.I), "partly_allowed"),
    (re.compile(r"\b(?:remand(?:ed|s)?|sent\s+(?:it\s+|the\s+case\s+|the\s+matter\s+)?back|remitted)\b", re.I), "remanded"),
    (re.compile(r"\bdisposed\s+of\b", re.I), "disposed"),
    (re.compile(r"\b(?:dismiss(?:ed|es)?|reject(?:ed|s)?|upheld|uphold(?:s)?|maintain(?:ed|s)?|refused|"
                r"declined|affirmed|confirmed)\b", re.I), "dismissed"),
    (re.compile(r"\b(?:allow(?:ed|s)?|accept(?:ed|s)?|set(?:s)?\s+aside|revers(?:ed|es)|restored|acquitted|"
                r"quashed|struck\s+down|reinstated|in\s+(?:his|her|their|our|my)\s+favou?r)\b", re.I), "allowed"),
]
_APPEAL_NOUN = re.compile(r"\b(?:appeals?|petitions?|leave|revision|case|matter)\b", re.I)
_DEPARTMENTAL = re.compile(r"\bdepartmental\s+appeal|\bservice\s+appeal|\brepresentation\b", re.I)


def _sentences(raw: str) -> list[str]:
    pieces = _SENTENCE_END.split(re.sub(r"\s+", " ", raw or "").strip())
    out: list[str] = []
    for piece in pieces:
        if out and _ABBREV.search(out[-1]):
            out[-1] = f"{out[-1]} {piece}"
        elif piece.strip():
            out.append(piece.strip())
    return out


def _clauses(sentence: str) -> list[str]:
    """Split a sentence at clause boundaries; a piece under 4 words is glued back
    ("The Registrar and the High Court allowed ..." stays one clause)."""
    out: list[str] = []
    for piece in _CLAUSE_SPLIT.split(sentence):
        piece = (piece or "").strip(" ,")
        if not piece:
            continue
        if out and len(out[-1].split()) < 4:
            out[-1] = f"{out[-1]} and {piece}"
        else:
            out.append(piece)
    return [c for c in out if len(c.split()) >= 2]


def _sc_attributed(clause: str) -> bool:
    """Whether the outcome in a clause is the Supreme Court's: the nearest forum
    named before the outcome verb is the SC, or "... by the Supreme Court".
    "The High Court ruled in her favour and we appealed to the Supreme Court"
    is the High Court's outcome, not the SC's."""
    first = min((m.start() for p, _ in _SC_OUTCOME for m in [p.search(clause)] if m), default=None)
    if first is None:
        return False
    if re.search(r"by\s+(?:the\s+)?(?:supreme\s+court|apex\s+court|this\s+court)", clause[first:], re.I):
        return True
    before = [m.group(0) for m in _ANY_FORUM.finditer(clause[:first])]
    return bool(before) and bool(_SUPREME.search(before[-1] + " "))


def _outcome_label(clause: str) -> str | None:
    for pattern, label in _SC_OUTCOME:
        if pattern.search(clause):
            return label
    return None


def _outcome_sc(clauses: list[str]) -> str | None:
    """The Supreme Court's outcome per the documented rule (module docstring)."""
    attributed: str | None = None
    last_outcome: tuple[int, str, str] | None = None   # (index, clause, label)
    supreme_seen_at: int | None = None
    for index, clause in enumerate(clauses):
        label = _outcome_label(clause)
        if _SUPREME.search(clause):
            if supreme_seen_at is None:
                supreme_seen_at = index
            if label and _sc_attributed(clause) and not re.search(r"\bleave\s+(?:to\s+appeal\s+)?(?:was\s+)?granted\b|\bgranted\s+leave\b",
                                       clause, re.I):
                attributed = label
                continue
        if label and (_COURT_ACTS.search(clause) or _APPEAL_NOUN.search(clause)):
            last_outcome = (index, clause, label)
    if attributed:
        return attributed
    if last_outcome and supreme_seen_at is not None:
        index, clause, label = last_outcome
        if (index > supreme_seen_at and re.search(r"\b(?:appeals?|petitions?)\b", clause, re.I)
                and not _LOWER_FORUM.search(clause) and not _DEPARTMENTAL.search(clause)):
            return label
    return None


def split_facets(raw: str) -> Facets:
    """The parts of a case description, in the user's own words (see module docstring).

    Clause-level: each clause goes to exactly one facet, so no word is counted
    twice. A facet the user did not describe is absent.
    """
    clauses = [c for s in _sentences(raw) for c in _clauses(s)]
    first_person = bool(_FIRST_PERSON.search(raw or ""))
    client_story = bool(_CLIENT_STORY.search(raw or ""))
    buckets: dict[str, list[str]] = {"facts": [], "claimant": [], "respondent": [], "court_view": []}
    for clause in clauses:
        court = _COURT_ACTS.search(clause) and not _OTHER_SIDE.match(clause)
        if court or _PASSIVE_OUTCOME.search(clause):
            buckets["court_view"].append(clause)
        elif _OTHER_SIDE.search(clause):
            buckets["respondent"].append(clause)
        elif _FIRST_PERSON_CLAIM.search(clause):
            buckets["claimant"].append(clause)
        elif _PRONOUN_CLAIM.search(clause):
            # "he says" is the client's case in a story about a client, and the
            # protagonist's in a third-person story; in an "I/we" story it is
            # someone else's.
            buckets["respondent" if first_person and not client_story else "claimant"].append(clause)
        elif _THIRD_PERSON_CLAIM.search(clause):
            # In "We are the heirs ... His wife claims ...", a third person's
            # claim is the other side's; in a third-person story it is the
            # protagonist's own case.
            buckets["respondent" if first_person else "claimant"].append(clause)
        else:
            buckets["facts"].append(clause)
    facets: Facets = {}
    for key, parts in buckets.items():
        text = " ".join((p[:1].upper() + p[1:]).rstrip(".?!") + ("?" if p.endswith("?") else ".")
                        for p in parts).strip()
        if text:
            facets[key] = text  # type: ignore[literal-required]
    outcome = _outcome_sc(clauses)
    if outcome:
        facets["outcome_sc"] = outcome  # type: ignore[typeddict-item]
    return facets


def analyze_regex(raw: str) -> QueryAnalysis:
    """The no-LLM analysis. Always safe to call; never touches the network."""
    raw = raw or ""
    case_refs = parse_case_numbers(raw)
    statutes = parse_statutes(raw)
    narrative = is_narrative(raw)
    facets = split_facets(raw) if narrative and _facets_enabled() else {}
    # A narrative's outcome is the Supreme Court's, never the first label found
    # anywhere in the story (which is usually a lower court's, reversed later).
    outcome = facets.get("outcome_sc") if narrative else _outcome(raw)
    return QueryAnalysis(
        raw=raw,
        cleaned=_clean(raw),
        query_type=heuristic_type(raw, case_refs, statutes, outcome),  # type: ignore[typeddict-item]
        case_refs=case_refs,  # type: ignore[typeddict-item]
        parties=_regex_parties(raw),
        statutes=statutes,
        years=_years(raw, statutes),
        registry=_registry(raw, case_refs),
        subject=None,
        outcome=outcome,  # type: ignore[typeddict-item]
        rewrite=raw.strip(),
        expansions=[],
        source="regex",
        is_narrative=narrative,  # type: ignore[typeddict-unknown-key]
        facets=facets,  # type: ignore[typeddict-unknown-key]
    )


# ── LLM path ─────────────────────────────────────────────────────────────────
SYSTEM_PROMPT = f"""You analyse search queries typed by lawyers who are looking
for judgments of the Supreme Court of Pakistan. Return ONE JSON object and
nothing else, with exactly these keys:

"query_type": one of {list(QUERY_TYPES)}
   citation    = names a case number ("C.A. 5-Q/2014")
   entity      = mainly names a party, person, organisation, place or judge
   statute     = mainly names a statutory provision ("Article 199", "s.302 PPC")
   issue       = states a legal question ("Was the penalty proportionate?")
   paraphrase  = describes facts or a situation in plain words
   disposition = asks about an outcome ("appeal dismissed with no order as to costs")
   vague       = a broad category, not a question ("any family dispute case")
   unknown     = not a legal query at all (greetings, chit-chat)
"parties": names of litigants, persons, organisations or places EXACTLY as
   written in the query. Proper names only, never generic roles such as
   "wife", "accused", "civil servant", "police officers". [] if none.
"subject": the single best area from {list(SUBJECT_AREAS)}, or null if unsure.
"outcome": one of ["allowed", "dismissed", "partly_allowed", "remanded",
   "disposed"] ONLY if the query asks about or specifies an outcome, else null.
"rewrite": the query restated in ONE sentence (max 40 words) in the formal
   vocabulary a Pakistani Supreme Court judgment would use. Replace lay words
   with legal terms of art (e.g. "fired from job" -> "dismissal from service";
   "thrown out of a rented shop" -> "ejectment of a tenant"; "got bail" ->
   "bail was granted"). Keep every fact, name and number the query states.
"expansions": 0-2 alternative legal phrasings of the same question, ONLY when
   query_type is paraphrase or vague; otherwise [].

STRICT RULES — the rewrite and expansions RESTATE, they never ADD:
- Do not invent facts, party names, places, dates, years, case numbers,
  citations, Acts, Articles, sections or courts that are not in the query.
- Do not name any statute or provision unless the query itself names it.
- If the query is not a legal query, return the query unchanged as the rewrite.
"""


NARRATIVE_ADDENDUM = """
THIS QUERY IS A CASE DESCRIPTION. Add one more key:
"facets": an object with any of these keys, each value COPIED VERBATIM from the
   query (whole sentences or clauses, never paraphrased, never invented); omit
   a key the query does not describe:
   "facts"       what happened
   "claimant"    what the user's side / the appellant says
   "respondent"  what the other side says
   "court_view"  what a court or tribunal BELOW the Supreme Court held
   "outcome_sc"  one of ["allowed", "dismissed", "partly_allowed", "remanded",
                 "disposed"] ONLY if the query says what the SUPREME COURT
                 decided (a High Court's or tribunal's result is NOT this);
                 otherwise omit it.
"""

NARRATIVE_MAX_TOKENS = 1100


def _user_prompt(raw: str) -> str:
    return f"QUERY: {raw.strip()}\n\nReturn the JSON object."


async def _call_llm(system_prompt: str, user_prompt: str, max_tokens: int) -> str:
    """The single seam to the LLM, so tests can replace it."""
    return await llm_responder._complete(system_prompt, user_prompt, max_tokens)


_FENCE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def _parse_json(content: str) -> dict | None:
    """Pull a JSON object out of a model response.

    The same logic as comparator._parse, kept local on purpose: importing
    app.retrieval.comparator pulls in Chroma and MongoDB at import time
    (~10s on first use), which would blow the 3s budget on a cold process.
    """
    if not content or content == llm_responder.ERROR_RESPONSE:
        return None
    candidate = content.strip()
    fenced = _FENCE.search(candidate)
    if fenced:
        candidate = fenced.group(1).strip()
    if not candidate.startswith("{"):
        start, end = candidate.find("{"), candidate.rfind("}")
        if start == -1 or end == -1:
            return None
        candidate = candidate[start:end + 1]
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


_NUMBER_WORDS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
    "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
    "seventy": 70, "eighty": 80, "ninety": 90, "hundred": 100,
}


def _numbers_in(text: str) -> set[str]:
    """Digit strings in text, plus spelled-out numbers ("sixty five" -> "65")."""
    nums = set(re.findall(r"\d+", text))
    tokens = re.findall(r"[a-z]+", text.lower())
    i = 0
    while i < len(tokens):
        if tokens[i] in _NUMBER_WORDS:
            value = _NUMBER_WORDS[tokens[i]]
            if value >= 20 and i + 1 < len(tokens) and 0 < _NUMBER_WORDS.get(tokens[i + 1], 0) < 10:
                value += _NUMBER_WORDS[tokens[i + 1]]
                i += 1
            nums.add(str(value))
        i += 1
    return nums


def _adds_entities(text: str, base: QueryAnalysis, raw_numbers: set[str]) -> list[str]:
    """What a rewrite/expansion introduces that the raw query did not contain."""
    added: list[str] = []
    raw_keys = {r["key"] for r in base.get("case_refs", [])}
    added += [r["key"] for r in parse_case_numbers(text) if r["key"] not in raw_keys]
    added += [s for s in parse_statutes(text) if s not in base.get("statutes", [])]
    added += [n for n in _numbers_in(text) if n not in raw_numbers]
    return added


def _validate(data: dict, base: QueryAnalysis) -> tuple[QueryAnalysis, dict]:
    """Merge the LLM's answer into the regex analysis, keeping only grounded parts.

    Returns the analysis and a dict of what was dropped (for logging/eval).
    """
    raw = base["raw"]
    raw_norm = f" {_normalise(raw)} "
    raw_numbers = _numbers_in(raw)
    dropped: dict[str, list] = {"parties": [], "rewrite": [], "expansions": [], "fields": []}
    result = copy.deepcopy(base)

    qtype = str(data.get("query_type") or "").strip().lower()
    if qtype == "citation" and not base["case_refs"]:
        qtype = "entity"  # no case number in the query: it cannot be exact-matched
    if qtype in QUERY_TYPES:
        result["query_type"] = qtype  # type: ignore[typeddict-item]
    else:
        dropped["fields"].append(f"query_type={qtype!r}")

    parties: list[str] = list(base.get("parties", []))
    for party in data.get("parties") or []:
        if not isinstance(party, str) or not party.strip():
            continue
        norm = _normalise(party)
        if norm and f" {norm} " in raw_norm:
            if norm not in {_normalise(p) for p in parties}:
                parties.append(party.strip())
        else:
            dropped["parties"].append(party)
    result["parties"] = parties

    subject = data.get("subject")
    if subject in SUBJECT_AREAS:
        result["subject"] = subject
    elif subject:
        match = next((s for s in SUBJECT_AREAS if s.lower() == str(subject).strip().lower()), None)
        result["subject"] = match
        if not match:
            dropped["fields"].append(f"subject={subject!r}")

    outcome = data.get("outcome")
    if outcome in ("allowed", "dismissed", "partly_allowed", "remanded", "disposed"):
        result["outcome"] = outcome
    elif outcome in (None, "", "null", "unknown"):
        result["outcome"] = None
    else:
        dropped["fields"].append(f"outcome={outcome!r}")

    rewrite = data.get("rewrite")
    if isinstance(rewrite, str) and rewrite.strip():
        added = _adds_entities(rewrite, base, raw_numbers)
        if added:
            dropped["rewrite"] = added
        else:
            result["rewrite"] = rewrite.strip()

    expansions: list[str] = []
    if result["query_type"] in ("paraphrase", "vague"):
        for exp in (data.get("expansions") or [])[:4]:
            if not isinstance(exp, str) or not exp.strip():
                continue
            added = _adds_entities(exp, base, raw_numbers)
            if added:
                dropped["expansions"].append(added)
            elif exp.strip() not in expansions and len(expansions) < 2:
                expansions.append(exp.strip())
    result["expansions"] = expansions

    # Narrative facets: each must be the user's own words. Accepted per key;
    # a missing or rejected key keeps the regex splitter's value.
    if base.get("is_narrative") and isinstance(data.get("facets"), dict):
        facets = dict(base.get("facets") or {})
        dropped["facets"] = []
        for key, value in data["facets"].items():
            if key == "outcome_sc":
                if value in ("allowed", "dismissed", "partly_allowed", "remanded", "disposed"):
                    facets["outcome_sc"] = value
                elif value not in (None, "", "null", "unknown"):
                    dropped["facets"].append(f"outcome_sc={value!r}")
                continue
            if key not in ("facts", "claimant", "respondent", "court_view"):
                dropped["facets"].append(f"{key}=?")
                continue
            if isinstance(value, list):
                value = " ".join(str(v) for v in value if v)
            if isinstance(value, str) and value.strip() and is_grounded_span(value, raw):
                facets[key] = value.strip()
            elif value:
                dropped["facets"].append(key)
        result["facets"] = facets  # type: ignore[typeddict-unknown-key]
    if base.get("is_narrative"):
        # A narrative's outcome is the Supreme Court's or nothing; the LLM's
        # general "outcome" may be a lower court's result.
        result["outcome"] = (result.get("facets") or {}).get("outcome_sc")  # type: ignore[typeddict-item]
    result["source"] = "llm"
    return result, dropped


def is_grounded_span(span: str, raw: str, min_share: float = 0.85) -> bool:
    """Whether `span` is (nearly) a verbatim piece of `raw`.

    Exact normalised substring, or at least `min_share` of the span's word
    trigrams occur in the raw text — so a model that fixes a typo or drops a
    comma still passes, while a paraphrase ("dismissed from service" for
    "fired") does not.
    """
    s, r = _normalise(span), _normalise(raw)
    if not s:
        return False
    if f" {s} " in f" {r} ":
        return True
    sw, rw = s.split(), r.split()
    if len(sw) < 3:
        return False
    raw_grams = {tuple(rw[i:i + 3]) for i in range(len(rw) - 2)}
    grams = [tuple(sw[i:i + 3]) for i in range(len(sw) - 2)]
    return sum(g in raw_grams for g in grams) / len(grams) >= min_share


# ── Cache ────────────────────────────────────────────────────────────────────
_cache: "OrderedDict[str, QueryAnalysis]" = OrderedDict()

# The last call's validation drops, exposed for the eval script.
last_dropped: dict = {}


def _cache_get(key: str) -> QueryAnalysis | None:
    if key in _cache:
        _cache.move_to_end(key)
        return copy.deepcopy(_cache[key])
    return None


def _cache_put(key: str, value: QueryAnalysis) -> None:
    _cache[key] = copy.deepcopy(value)
    _cache.move_to_end(key)
    while len(_cache) > max(1, _cache_size()):
        _cache.popitem(last=False)


def clear_cache() -> None:
    _cache.clear()


# ── Entry point ──────────────────────────────────────────────────────────────
async def analyze(raw: str) -> QueryAnalysis:
    """Understand a query. Never raises, never waits longer than the timeout.

    Args:
        raw: The query as typed.

    Returns:
        A QueryAnalysis. source="llm" when the LLM answered and was validated;
        "regex" when it was skipped (citation, chit-chat, disabled) or failed.
    """
    global last_dropped
    last_dropped = {}
    key = _normalise(raw)
    cached = _cache_get(key)
    if cached is not None:
        cached["raw"] = raw or ""
        return cached

    base = analyze_regex(raw)

    # Citation: exact match answers it. Chit-chat/empty: nothing to understand.
    if base["case_refs"] or base["query_type"] == "unknown" or not key or not _llm_enabled():
        _cache_put(key, base)
        return base

    started = time.perf_counter()
    narrative = bool(base.get("is_narrative")) and _facets_enabled()
    system = SYSTEM_PROMPT + (NARRATIVE_ADDENDUM if narrative else "")
    budget = _narrative_timeout() if narrative else _timeout()
    try:
        content = await asyncio.wait_for(
            _call_llm(system, _user_prompt(raw), NARRATIVE_MAX_TOKENS if narrative else MAX_TOKENS),
            timeout=budget,
        )
    except asyncio.TimeoutError:
        logger.warning(f"Query analyzer LLM timed out after {budget:.1f}s; regex fallback")
        return base
    except Exception as e:
        logger.warning(f"Query analyzer LLM failed ({e}); regex fallback")
        return base

    data = _parse_json(content)
    if not data:
        logger.warning("Query analyzer got no usable JSON; regex fallback")
        return base

    try:
        result, dropped = _validate(data, base)
    except Exception as e:
        logger.warning(f"Query analyzer could not validate LLM output ({e}); regex fallback")
        return base

    last_dropped = dropped
    if any(dropped.values()):
        logger.info(f"Query analyzer dropped ungrounded output: {dropped}")
    logger.debug(
        f"Query analyzed in {time.perf_counter() - started:.2f}s: "
        f"type={result['query_type']} subject={result.get('subject')}"
    )
    _cache_put(key, result)
    return result


# ── Self-check (no real LLM calls; pass --live for one real call) ────────────
if __name__ == "__main__":

    async def _main() -> None:
        global _call_llm
        real_call = _call_llm

        # 1. Regex path.
        a = analyze_regex("Civil Appeal No. 5-Q of 2014 decided at Quetta")
        assert a["query_type"] == "citation" and a["case_refs"][0]["key"] == "CA-5-Q-2014", a
        assert a["registry"] == "Q" and a["years"] == [2014], a
        a = analyze_regex("suo motu jurisdiction under Article 199")
        assert a["statutes"] == ["Article 199"] and a["query_type"] == "statute", a
        a = analyze_regex("family court jurisdiction under the Family Courts Act 1964")
        assert a["years"] == [], "an Act's year must not be a decision year"
        assert analyze_regex("any family dispute case")["query_type"] == "vague"
        assert analyze_regex("hiiii")["query_type"] == "unknown"
        assert analyze_regex("Can rejected ballot papers be recounted?")["outcome"] is None
        assert analyze_regex("evacuee land granted and later disputed")["outcome"] is None
        assert analyze_regex("civil revision dismissed by the High Court")["outcome"] == "dismissed"
        assert analyze_regex("Service appeal remanded for fresh hearing")["outcome"] == "remanded"
        assert analyze_regex("appeal partly allowed")["outcome"] == "partly_allowed"
        assert analyze_regex("Why was bail granted despite murder charges?")["query_type"] == "issue"
        a = analyze_regex("appeal dismissed with no order as to costs for want of merit")
        assert a["query_type"] == "disposition" and a["outcome"] == "dismissed", a
        assert analyze_regex("goveronment of pakistan vs pso")["parties"] == ["goveronment of pakistan", "pso"]
        assert analyze_regex("petitions decided by the High Court at Islamabad")["registry"] is None
        assert analyze_regex("who owns a brand name after a company is restructured")["query_type"] == "issue"
        assert analyze_regex("dispute over wrong entries in the revenue record")["query_type"] == "paraphrase"
        assert analyze_regex("civil revision dismissed by the High Court")["is_narrative"] is False
        print("  regex path                              OK")

        # 1b. Narrative facets and the Supreme-Court-only outcome rule.
        constable = ("My client was a police constable who was dismissed from service after a departmental "
                     "inquiry. He says the inquiry officer never recorded his evidence. The other side argues "
                     "that his absence was proved. The tribunal upheld the dismissal. The Supreme Court allowed "
                     "his appeal and reinstated him.")
        a = analyze_regex(constable)
        f = a["facets"]
        assert a["is_narrative"] and f["outcome_sc"] == "allowed" and a["outcome"] == "allowed", a
        assert "inquiry officer never recorded" in f["claimant"], f
        assert "absence was proved" in f["respondent"] and "tribunal upheld" in f["court_view"], f
        assert "departmental inquiry" in f["facts"], f
        heirs = ("We are the heirs of the deceased. His wife claims land was given to her in lieu of dower "
                 "through the nikah nama and she sued decades later to correct the revenue entries. We say "
                 "her claim is barred by limitation. The High Court ruled in her favour and we appealed to "
                 "the Supreme Court.")
        f = analyze_regex(heirs)["facets"]
        assert "outcome_sc" not in f, f"a High Court result is not the SC's: {f}"
        assert f["respondent"].startswith("His wife claims") and f["claimant"].startswith("We say"), f
        assert analyze_regex(heirs)["outcome"] is None
        tenants = ("We are tenants of a shop in the city and paid rent for twenty years without default. The "
                   "rent controller ordered our eviction and the High Court upheld it. We appealed to the "
                   "Supreme Court. The appeal was dismissed.")
        assert analyze_regex(tenants)["facets"]["outcome_sc"] == "dismissed"
        misfire = ("The Federation of Pakistan through the Ministry refused to pay my client's pension after "
                   "he retired from a corporation, saying he was never a civil servant. The tribunal agreed "
                   "with the Ministry and dismissed his appeal.")
        f = analyze_regex(misfire)["facets"]
        assert "outcome_sc" not in f and "dismissed his appeal" in f["court_view"], f
        assert set(f) <= {"facts", "claimant", "respondent", "court_view", "outcome_sc"}
        assert all(v for v in f.values()), "absent facets are absent, never empty"
        print("  narrative facets + SC-only outcome      OK")

        # 2. Validation drops ungrounded entities.
        async def fake(system, user, max_tokens):
            return json.dumps({
                "query_type": "paraphrase", "parties": ["Tando Adam", "Mst. Zainab"],
                "subject": "Evacuee property", "outcome": None,
                "rewrite": "Dispute regarding evacuee land allotted and subsequently challenged in Tando Adam.",
                "expansions": ["Evacuee property claim under Section 2 of the Displaced Persons Act 1958",
                               "Cancellation of allotment of evacuee land at Tando Adam"],
            })
        _call_llm = fake
        clear_cache()
        r = await analyze("evacuee land granted and later disputed in Tando Adam")
        assert r["source"] == "llm" and r["parties"] == ["Tando Adam"], r
        assert r["subject"] == "Evacuee property" and len(r["expansions"]) == 1, r
        assert last_dropped["parties"] == ["Mst. Zainab"] and last_dropped["expansions"], last_dropped
        print("  validation drops hallucinated entities  OK")

        # LLM facets: verbatim spans accepted, paraphrases rejected (regex value kept).
        base = analyze_regex(constable)
        v, d = _validate({"query_type": "paraphrase", "outcome": "dismissed", "facets": {
            "facts": "My client was a police constable who was dismissed from service",
            "claimant": "The officer was unfairly treated and denied a hearing",
            "court_view": "The tribunal upheld the dismissal.",
            "outcome_sc": "allowed"}}, base)
        assert v["facets"]["facts"] == "My client was a police constable who was dismissed from service"
        assert v["facets"]["claimant"] == base["facets"]["claimant"] and d["facets"] == ["claimant"], d
        assert v["outcome"] == "allowed", "a narrative's outcome is outcome_sc, not the LLM's 'outcome'"
        assert is_grounded_span("the tribunal upheld the dismisal", base["raw"]) is False
        assert is_grounded_span("The tribunal upheld the dismissal", base["raw"])
        print("  LLM facets validated as verbatim        OK")

        # Case-insensitive duplicates of a regex party are not added twice.
        v, _ = _validate({"query_type": "entity", "parties": ["PSO", "Government of Pakistan"]},
                         analyze_regex("goveronment of pakistan vs pso"))
        assert v["parties"] == ["goveronment of pakistan", "pso"], v["parties"]

        # A citation never reaches the LLM: exact match answers it.
        async def must_not_call(system, user, max_tokens):
            raise AssertionError("LLM called for a citation query")
        _call_llm = must_not_call
        r = await analyze("C.A. 57-K/2018 trade mark")
        assert r["query_type"] == "citation" and r["case_refs"][0]["key"] == "CA-57-K-2018", r
        assert r["registry"] == "K" and r["source"] == "regex"
        print("  citation skips the LLM                  OK")

        # 3. Cache: second call is near-instant and does not call the LLM.
        calls = 0

        async def counting(system, user, max_tokens):
            nonlocal calls
            calls += 1
            return await fake(system, user, max_tokens)
        _call_llm = counting
        t = time.perf_counter()
        r2 = await analyze("Evacuee land granted and later disputed in Tando Adam!")
        assert calls == 0 and r2["source"] == "llm" and time.perf_counter() - t < 0.01
        print(f"  cache hit in {(time.perf_counter() - t) * 1000:.2f} ms              OK")

        # 4. Fallback: an LLM that hangs must not block past the timeout.
        async def hang(system, user, max_tokens):
            await asyncio.sleep(60)
            return "{}"
        _call_llm = hang
        settings_timeout = getattr(settings, "QUERY_ANALYZER_TIMEOUT", None)
        clear_cache()
        t = time.perf_counter()
        r3 = await analyze("who owns a brand name after a company is restructured")
        elapsed = time.perf_counter() - t
        assert r3["source"] == "regex" and elapsed < _timeout() + 0.5, (r3, elapsed)
        assert settings_timeout is None or settings_timeout == _timeout()
        print(f"  hanging LLM -> regex fallback in {elapsed:.2f}s   OK")

        # 5. Garbage output -> fallback, and failures are not cached.
        async def garbage(system, user, max_tokens):
            return "Error: Could not generate answer. Please try again."
        _call_llm = garbage
        r4 = await analyze("trade mark assignment agreement was incorrectly relied upon")
        assert r4["source"] == "regex" and _normalise(r4["raw"]) not in _cache
        print("  LLM error -> regex fallback, not cached OK")

        if "--live" in sys.argv:
            _call_llm = real_call
            clear_cache()
            r5 = await analyze("who owns a brand name after a company is restructured")
            print(json.dumps(r5, indent=2))
        print("\nOK: query analyzer self-check passed.")

    asyncio.run(_main())
