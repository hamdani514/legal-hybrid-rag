"""
Exact-match retrieval (R1 exact): case numbers and party names -> judgments.

Why a retriever that is not a search
------------------------------------
A lawyer who types "C.A. 5-Q/2014" or "Mir Saleem Ahmed Khosa v. Zafarullah
Khan Jamali" knows which case they want. Neither dense nor BM25 retrieval is
built to answer that reliably: a bge vector barely distinguishes "5-Q/2014"
from "43-Q/2018", and BM25 can be outvoted by a long passage that repeats
"2014". So this retriever does a lookup, not a ranking — and when it hits, the
hit is the answer (score 1.0), which fusion can trust above everything else.

Two lookups
-----------
1. Case keys. analysis["case_refs"] (from the query analyzer) or, failing
   that, case_keys(cleaned) — the ONE shared normaliser, so "C.A. 5-Q/2014" and
   the header's "CIVIL APPEAL NO. 5-Q OF 2014" both become "CA-5-Q-2014".
   Matched against case_cards.case_keys. Score 1.0.
2. Party names. Normalised token overlap, not substring: honorifics and
   filler ("Mst.", "and others", "through its Secretary") are dropped and
   tokens are weighted by rarity across all party names in the corpus, so a
   query naming "Khan" alone hits nothing while "Zafarullah Khan Jamali" hits
   the one case. A party name P matches when the query covers >= 60% of P's
   rarity-weighted tokens and at least two of them. Score 0.5 + 0.4*coverage
   (0.74..0.9), always below a case-key hit.

Institutions never identify a case
----------------------------------
"The Inspector General of Police said the dismissal was proper" names no
party, yet its tokens covered the party "The Inspector General of Police,
Punjab" and pinned that judgment at 0.9 above everything ("Federation of
Pakistan through the Ministry ..." did the same). At 3,000 judgments hundreds
of cases name the Federation, a Province, a Ministry or the police, so these
words say nothing about WHICH case. INSTITUTIONAL words are removed from both
sides before matching (match_tokens): "Province of Sindh & others" can no
longer be matched at all, "Waris Ali through LRs" still can.

Where party names come from
---------------------------
Tokenising a whole case description finds "party names" in ordinary prose. So:
  * a short query (< NARRATIVE_MIN_WORDS words) is still matched as a whole —
    "Mir Saleem Ahmed Khosa versus Zafarullah Khan Jamali" must resolve;
  * a narrative is matched only on extracted parties: analysis["parties"]
    (the analyzer's) and explicit "X v. Y" / "X versus Y" forms in its text.

Pinned or voting
----------------
Every candidate carries ``pinned``. Case-number hits are always pinned (the
user named the case). Party hits on a short query stay pinned, as before. Party
hits on a narrative are NOT pinned: fusion counts them as one ranked vote
among the retrievers, so a shared name can support a match but never force
one past the gate and the confidence policy.

Without case cards
------------------
Agent B's `case_cards` collection may be empty or partial. For every judgment
without a card, the same two lookups run against what ingestion already has:
case keys parsed from the first 2,500 characters of uploads/{pdf_id}.txt (the
header, where the case number always is), and party names from the root node's
templated summary ("Appeal by X against Y regarding ...") plus the
appellant/respondent block of that header. Cards win wherever they exist.

The per-judgment lookup table is cached in-process and rebuilt when the
number of documents or cards changes (checked at most every 30 s), so a query
costs a dict lookup, not a MongoDB scan. Never raises: any failure returns [].
"""

import asyncio
import math
import re
import sys
import time
from collections import Counter
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from loguru import logger

from app.retrieval.case_keys import case_keys as parse_keys
from app.retrieval.contracts import NARRATIVE_MIN_WORDS, Candidate, QueryAnalysis, with_ranks

UPLOADS_DIR = Path(__file__).resolve().parents[2] / "uploads"
HEAD_CHARS = 2500
CACHE_CHECK_SECONDS = 30

MIN_COVERAGE = 0.6
MIN_MATCHED_TOKENS = 2

# Tokens that say nothing about WHICH party: honorifics, legal roles, filler.
_PARTY_STOP = frozenset("""
and or the of in at for to by its his her their through thru others other another etc
mr mrs ms mst miss dr syed sayed haji hafiz sardar mian chaudhry ch rana malik
appellant appellants respondent respondents petitioner petitioners applicant applicants
deceased lrs lr legal heirs heir represented son daughter wife widow d s w o
private pvt limited ltd co company m messrs no nos versus vs v
in ca cp cpla crl case cases appeal appeals petition petitions all both
""".split())

# Words that name an institution, an office or a place rather than a party.
# Never count toward a party match (see "Institutions never identify a case").
INSTITUTIONAL = frozenset("""
federation federal pakistan islamic republic province provinces provincial punjab sindh kpk kp khyber
pakhtunkhwa nwfp balochistan baluchistan gilgit baltistan azad jammu kashmir ajk islamabad capital
territory ict karachi lahore peshawar quetta government govt ministry minister secretary additional
deputy joint police inspector general ig igp superintendent ssp dpo cpo officer officers incharge
board revenue tribunal tribunals department departments authority authorities corporation director
directorate chief commissioner collector district divisional division member chairman president
registrar regional state establishment administration administrator municipal metropolitan council
committee cantonment commission agency bureau office national assembly senate election returning
accountability court courts high supreme
foreign affairs interior finance defence defense law justice parliamentary health education home
communications railways petroleum information commerce industries planning labour religious overseas
housing works irrigation excise taxation customs inland wapda fbr cbr nadra
""".split())

_TOKEN = re.compile(r"[a-z0-9]+")
_NAMED_VERSUS = re.compile(
    r"([A-Z][\w.'&-]*(?:\s+(?:[A-Z][\w.'&-]*|of|and|&|ul|ud|un|bin|binte)){0,7})"
    r"\s+(?:v\.|vs\.?|versus)\s+"
    r"([A-Z][\w.'&-]*(?:\s+(?:[A-Z][\w.'&-]*|of|and|&|ul|ud|un|bin|binte)){0,7})")
_VERSUS = re.compile(r"\b(?:versus|vs\.?|v\.)\s", re.IGNORECASE)
_ROOT_PARTIES = re.compile(r"\bby\s+(.+?)\s+against\s+(.+?)\s+regarding\b", re.IGNORECASE | re.DOTALL)
_ROLE_MARKER = re.compile(
    r"[.…\s]*\b(?:appellants?|respondents?|petitioners?|applicants?)\s*(?:\(s\))?",
    re.IGNORECASE)
_COUNSEL_START = re.compile(r"\bFor\s+(?:the\s+)?(?:Appellant|Petitioner|Respondent|Applicant)",
                            re.IGNORECASE)


def party_tokens(name: str) -> list[str]:
    """Lowercased informative tokens of a party name, in order, deduplicated."""
    out: list[str] = []
    for tok in _TOKEN.findall((name or "").lower()):
        if len(tok) > 1 and not tok.isdigit() and tok not in _PARTY_STOP and tok not in out:
            out.append(tok)
    return out


def match_tokens(name: str) -> list[str]:
    """party_tokens without institutional words: the tokens that can identify a party."""
    return [t for t in party_tokens(name) if t not in INSTITUTIONAL]


def is_narrative(analysis: QueryAnalysis) -> bool:
    """The analyzer's flag, else the word count (contracts.NARRATIVE_MIN_WORDS)."""
    if "is_narrative" in analysis:
        return bool(analysis.get("is_narrative"))
    return len((analysis.get("raw") or analysis.get("cleaned") or "").split()) >= NARRATIVE_MIN_WORDS


def named_parties(raw: str) -> list[str]:
    """Explicit "X v. Y" / "X versus Y" names inside running text (capitalised)."""
    out: list[str] = []
    for m in _NAMED_VERSUS.finditer(raw or ""):
        out += [m.group(1).strip(" .,"), m.group(2).strip(" .,")]
    return [p for p in out if match_tokens(p)]


def _name_variants(name: str) -> list[str]:
    """A name, plus its part before "through ..." (who acts for it is not who it is)."""
    name = re.sub(r"\s+", " ", name or "").strip(" .,;:-…")
    if not name:
        return []
    variants = [name]
    head = re.split(r"\bthrough\b", name, maxsplit=1, flags=re.IGNORECASE)[0].strip(" .,;:-")
    if head and head != name:
        variants.append(head)
    return variants


def parties_from_head(head: str) -> list[str]:
    """Party names from the appellant/respondent block of a judgment header.

    The block runs from the case number to the first "For the Appellant"; it is
    split on VERSUS, parentheticals ("(In CA 42-K/2016)") and role markers are
    removed, and numbered lists ("1. X 2. Y") become separate names.
    """
    end = _COUNSEL_START.search(head)
    block = head[: end.start()] if end else head
    parts = _VERSUS.split(block)
    if len(parts) < 2:
        return []
    # Appellant side: what follows the last bracketed lower-court reference.
    left = re.split(r"[)\]]", parts[0])[-1]
    names: list[str] = []
    for side in (left, " ".join(parts[1:])):
        side = re.sub(r"\([^)]*\)|\[[^\]]*\]", " ", side)
        side = _ROLE_MARKER.sub(" ; ", side)
        for piece in re.split(r";|\s\d{1,2}\.\s|\n\s*\n", side):
            piece = re.sub(r"\s+", " ", piece).strip(" .,;:-…")
            if party_tokens(piece):
                names.append(piece)
    return names


class _Entry(dict):
    """keys: set[str]; parties: list[str]; display: str; source: 'card'|'fallback'."""


class ExactMatchRetriever:
    """R1: case-key and party-name lookup against case cards (or the fallback)."""

    name = "exact"

    def __init__(self, uploads_dir: Path | str | None = None, use_cards: bool = True):
        """use_cards=False forces the no-card fallback everywhere (for ablation)."""
        self.uploads_dir = Path(uploads_dir) if uploads_dir else UPLOADS_DIR
        self.use_cards = use_cards
        self._table: dict[str, _Entry] = {}
        self._key_index: dict[str, set[str]] = {}
        self._idf: dict[str, float] = {}
        self._signature: tuple | None = None
        self._checked_at = 0.0
        self._lock = asyncio.Lock()

    # ── lookup table ────────────────────────────────────────────────────────
    async def _database(self):
        from app.database import connect_db, db
        if db.database is None:
            await connect_db()
        return db.database

    async def _refresh(self) -> None:
        now = time.monotonic()
        if self._signature is not None and now - self._checked_at < CACHE_CHECK_SECONDS:
            return
        async with self._lock:
            if self._signature is not None and time.monotonic() - self._checked_at < CACHE_CHECK_SECONDS:
                return
            database = await self._database()
            signature = (
                await database.documents.estimated_document_count(),
                await database.case_cards.estimated_document_count(),
                await database.nodes.estimated_document_count(),
            )
            self._checked_at = time.monotonic()
            if signature == self._signature:
                return
            await self._build(database)
            self._signature = signature

    async def _build(self, database) -> None:
        started = time.perf_counter()
        judgment_ids = sorted({d for d in await database.nodes.distinct("pdf_id") if d})
        table: dict[str, _Entry] = {}

        async for card in database.case_cards.find(
                {"judgment_id": {"$in": judgment_ids if self.use_cards else []}},
                {"_id": 0, "judgment_id": 1, "case_keys": 1, "case_display": 1,
                 "appellant": 1, "respondent": 1}):
            parties = [v for n in (card.get("appellant"), card.get("respondent"))
                       for v in _name_variants(n or "")]
            table[card["judgment_id"]] = _Entry(
                keys=set(card.get("case_keys") or []), parties=parties,
                display=card.get("case_display") or "", source="card")

        missing = [j for j in judgment_ids if j not in table]
        if missing:
            roots = {
                r["pdf_id"]: r
                async for r in database.nodes.find(
                    {"pdf_id": {"$in": missing}, "type": "parent"},
                    {"_id": 0, "pdf_id": 1, "title": 1, "text": 1})
            }
            for judgment_id in missing:
                head = self._head(judgment_id)
                root = roots.get(judgment_id, {})
                names: list[str] = []
                found = _ROOT_PARTIES.search(root.get("text") or "")
                if found:
                    names += [found.group(1), found.group(2)]
                names += parties_from_head(head)
                parties = [v for n in names for v in _name_variants(n)]
                keys = set(parse_keys(head)) | set(parse_keys(root.get("title") or ""))
                table[judgment_id] = _Entry(keys=keys, parties=parties,
                                            display=root.get("title") or "", source="fallback")

        key_index: dict[str, set[str]] = {}
        df: Counter = Counter()
        names_total = 0
        for judgment_id, entry in table.items():
            for key in entry["keys"]:
                key_index.setdefault(key, set()).add(judgment_id)
            for name in entry["parties"]:
                names_total += 1
                df.update(set(match_tokens(name)))
        self._idf = {t: math.log(1 + names_total / n) for t, n in df.items()}
        self._table, self._key_index = table, key_index
        logger.info(
            f"Exact-match table: {len(table)} judgments "
            f"({sum(e['source'] == 'card' for e in table.values())} from cards), "
            f"{len(key_index)} case keys, built in {time.perf_counter() - started:.2f}s")

    def _head(self, judgment_id: str) -> str:
        path = self.uploads_dir / f"{judgment_id}.txt"
        try:
            with open(path, encoding="utf-8", errors="ignore") as f:
                return f.read(HEAD_CHARS)
        except OSError:
            return ""

    # ── matching ────────────────────────────────────────────────────────────
    def _party_score(self, query_tokens: set[str], entry: _Entry) -> float:
        best = 0.0
        for name in entry["parties"]:
            tokens = match_tokens(name)
            if not tokens:
                continue
            matched = [t for t in tokens if t in query_tokens]
            if len(matched) < MIN_MATCHED_TOKENS:
                continue
            mass = sum(self._idf.get(t, 1.0) for t in tokens)
            coverage = sum(self._idf.get(t, 1.0) for t in matched) / mass if mass else 0.0
            if coverage >= MIN_COVERAGE:
                best = max(best, coverage)
        return 0.5 + 0.4 * best if best else 0.0

    def match(self, analysis: QueryAnalysis, k: int) -> list[Candidate]:
        text = analysis.get("cleaned") or analysis.get("raw") or ""
        refs = analysis.get("case_refs")
        keys = [r["key"] for r in refs if r.get("key")] if refs else parse_keys(text)
        if not keys and analysis.get("raw"):
            keys = parse_keys(analysis["raw"])

        scored: dict[str, tuple[float, str, bool]] = {}
        for key in keys:
            for judgment_id in self._key_index.get(key, ()):
                scored[judgment_id] = (1.0, f"case number {key}", True)

        # Short query: the whole text may be a party name. Narrative: only
        # names that were extracted as names (see "Where party names come from").
        narrative = is_narrative(analysis)
        parties = list(analysis.get("parties") or [])
        if narrative:
            parties += named_parties(analysis.get("raw") or "")
            party_text = " ".join(parties)
        else:
            party_text = " ".join([text] + parties)
        query_tokens = set(match_tokens(party_text))
        if len(query_tokens) >= MIN_MATCHED_TOKENS:
            for judgment_id, entry in self._table.items():
                if judgment_id in scored:
                    continue
                score = self._party_score(query_tokens, entry)
                if score:
                    scored[judgment_id] = (score, "party name", not narrative)

        ranked = sorted(scored.items(), key=lambda kv: (-kv[1][0], kv[0]))[:k]
        out: list[Candidate] = []
        for judgment_id, (score, why, pinned) in ranked:
            entry = self._table.get(judgment_id, _Entry(parties=[], display=""))
            out.append({
                "judgment_id": judgment_id,
                "mongo_doc_id": "",
                "vector_id": f"exact:{judgment_id}",
                "section_type": "CARD",
                "heading": entry.get("display", ""),
                "chunk_index": 0,
                "text": f"{entry.get('display', '')}\n" + " v. ".join(entry.get("parties", [])[:2]),
                "score": score,
                "reason": why,
                "pinned": pinned,   # False: a narrative party hit, fused as a vote
            })
        return with_ranks(out, self.name)

    async def retrieve(self, analysis: QueryAnalysis, k: int) -> list[Candidate]:
        try:
            await self._refresh()
            return self.match(analysis, k)
        except Exception as e:
            logger.warning(f"exact match failed, returning []: {e}")
            return []


if __name__ == "__main__":
    from app.retrieval.query_preprocessor import clean_query

    logger.remove()

    # Pure helpers.
    assert party_tokens("Mst. Pakistan Bibi and others") == ["pakistan", "bibi"]
    assert _name_variants("Federation of Pakistan through Secretary, Ministry")[1] == \
        "Federation of Pakistan"
    head = ("CIVIL APPEAL NO. 5-Q OF 2014 (On appeal against the judgment dated 18.03.2014) "
            "Mir Saleem Ahmed Khosa … Appellant VERSUS Zafarullah Khan Jamali and others "
            "…Respondents For the Appellant: Mr. Kamran Murtaza")
    names = parties_from_head(head)
    assert names[0] == "Mir Saleem Ahmed Khosa" and "Zafarullah Khan Jamali and others" in names, names
    print(f"OK: header party parse -> {names}")

    async def real() -> None:
        r = ExactMatchRetriever()
        def a(q: str) -> QueryAnalysis:
            return {"raw": q, "cleaned": clean_query(q)}  # type: ignore[return-value]

        target = "5a14105d-8a45-413c-8c93-26d6301cf028"
        for q in ("C.A. 5-Q/2014", "Civil Appeal No. 5-Q of 2014", "what was held in CA 5-Q/2014?"):
            got = await r.retrieve(a(q), 10)
            assert got and got[0]["judgment_id"] == target and got[0]["score"] == 1.0, (q, got)
        got = await r.retrieve(a("Mir Saleem Ahmed Khosa versus Zafarullah Khan Jamali"), 10)
        assert got and got[0]["judgment_id"] == target and 0.5 < got[0]["score"] < 1.0, got
        assert len(got) == 1, f"party match must be specific, got {len(got)}"
        # case_refs from the analyzer take precedence over re-parsing.
        got = await r.retrieve({"raw": "x", "cleaned": "x", "case_refs": [{"key": "CA-5-Q-2014"}]}, 5)
        assert got and got[0]["judgment_id"] == target
        # Non-matches.
        for q in ("Khan", "appeal dismissed with no order as to costs",
                  "C.A. 999-Q/2014", "", "Government of Pakistan", "Inspector General of Police Punjab",
                  "Federation of Pakistan through Secretary Ministry of Foreign Affairs"):
            got = await r.retrieve(a(q), 10)
            assert got == [], (q, got)
        got = await r.retrieve(a("Mir Saleem Ahmed Khosa versus Zafarullah Khan Jamali"), 10)
        assert got[0]["pinned"] is True, "a short party query stays pinned"

        # The two baseline misfires: institutional words in a narrative never match.
        misfires = (
            "My client is a police constable in Punjab who was dismissed after a departmental inquiry into "
            "absence from duty. He says the inquiry officer never recorded his evidence. The Inspector General "
            "of Police said the dismissal was proper and his departmental appeal was rejected.",
            "The Federation of Pakistan through the Ministry refused to pay my client's pension after he "
            "retired from a corporation, saying he was never a civil servant. The tribunal agreed with the "
            "Ministry and dismissed his appeal.")
        for q in misfires:
            got = await r.retrieve(a(q), 10)
            assert got == [], (q[:40], got)
        # A narrative naming the parties as "X v. Y" votes, it is not pinned.
        story = ("This is like Mir Saleem Ahmed Khosa v. Zafarullah Khan Jamali where my client lost an "
                 "election petition because the tribunal said the rejected ballot papers could not be recounted "
                 "after the polls were over.")
        got = await r.retrieve(a(story), 10)
        assert got and got[0]["judgment_id"] == target and got[0]["pinned"] is False, got
        # A narrative's case number stays pinned.
        got = await r.retrieve(a(story + " It was C.A. 5-Q/2014."), 10)
        assert got[0]["pinned"] is True and got[0]["score"] == 1.0, got
        assert match_tokens("The Inspector General of Police, Punjab & Others") == []
        assert match_tokens("Waris Ali (deceased) through LRs & Others") == ["waris", "ali"]
        print(f"OK: case keys, party names, case_refs and non-matches "
              f"({len(r._table)} judgments, {len(r._key_index)} keys)")

    async def fallback_only() -> None:
        r = ExactMatchRetriever(use_cards=False)
        got = await r.retrieve({"raw": "C.A. 23-P/2017", "cleaned": "c.a. 23-p/2017"}, 5)
        assert got and got[0]["judgment_id"].startswith("3eff8217"), got
        assert all(e["source"] == "fallback" for e in r._table.values())
        print("OK: no-card fallback (uploads head + root summary) finds the case")

    async def both() -> None:
        # One event loop: motor's client is bound to the loop it was created on.
        await real()
        await fallback_only()

    asyncio.run(both())
