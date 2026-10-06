"""
BM25 retrievers over the SQLite FTS5 lexical index (R2 bm25_chunks, R3 bm25_cards).

Why BM25 next to dense retrieval
--------------------------------
Dense vectors capture meaning but blur rare tokens: party names, places,
constituency codes ("NA-266"), section numbers. BM25 scores exactly those
highest, because a rare matching token is its strongest evidence. The two fail
on different queries, so each retriever runs alone here and fusion (Agent E)
combines them.

How a query becomes an FTS5 MATCH expression
--------------------------------------------
1. Text sources: ``cleaned``, plus ``rewrite`` and ``expansions`` when the
   query analyzer (Agent D) produced them. All their terms are OR'd into one
   query, so a term the user typed and a term from the legal rewrite compete
   on equal BM25 footing rather than in separate lists.
2. Each whitespace token is split the way the index tokenizer (unicode61)
   splits it. A plain word becomes a term. A compound token with a number in
   it — "23-p/2017", "s.302", "185(3)" — becomes an FTS5 NEAR group of its
   parts within 2 tokens, NEAR("23" "p" "2017", 2), so "23-P/2017" in a query
   meets "23-P OF 2017" in a header (a plain phrase would not: "of" sits
   between), plus its multi-digit numbers as separate terms for recall. A
   hyphenated name ("noor-ul-basar") becomes an exact phrase. All-initial
   abbreviations ("c.a.") are dropped: as BM25 terms they match every cited
   case in every judgment.
3. Stopwords and one-character terms are dropped — they carry no evidence and
   cost time on a 36,500-row index.
4. Every term is double-quoted (embedded quotes doubled), so no user input can
   be read as FTS5 syntax (AND, NEAR, column filters, "*"). Any remaining
   SQLite error returns [] — a retriever must never take a search down.

score = -bm25(), so higher is better like every other retriever's score.

Case descriptions: noise words and salience
-------------------------------------------
A 40-150 word description yields 60-100 candidate terms, and the old rule
kept the FIRST 64 — so the tail of the story (what the courts held, how it
ended), which is the most case-specific part, was the part dropped, while
narrative filler ("says", "client", "side", "other", "later") took slots.
Two changes:
  1. NARRATIVE_STOPWORDS (narrative queries only, NARRATIVE_MIN_WORDS+ words):
     the storytelling vocabulary of case descriptions, which no judgment uses
     to distinguish itself. A short query keeps them.
  2. Salience selection (any query over the budget): the plain words are
     ranked by document frequency in the chunk index (an FTS5 MATCH count,
     cached per index file version) and the rarest are kept up to MAX_TERMS.
     Citation NEAR groups and hyphenated-name phrases are always kept. A word
     that occurs in no chunk at all is dropped: it cannot match. Query order is
     restored afterwards, so the MATCH string stays readable.
Short queries under the budget are built exactly as before.
"""

import asyncio
import re
import sqlite3
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from loguru import logger

from app.indexing.fts_index import CARD_COLUMNS, CARD_WEIGHTS, connect, db_path
from app.retrieval.contracts import Candidate, QueryAnalysis, with_ranks

# Function words, question words and the query-boilerplate lawyers type ("case
# where", "judgment about"). Legal vocabulary is deliberately NOT here: BM25's
# IDF already discounts "court" and "appeal" where they are common, and they are
# real evidence in a query like "appeal allowed".
STOPWORDS = frozenset("""
a about above after again against all am an and any are as at be because been
before being below between both but by can could did do does doing down during
each few for from further had has have having he her here hers him his how i if
in into is it its itself just me more most my no nor not now of off on once only
or other our out over own same she should so some such than that the their them
then there these they this those through to too under until up very was we were
what when where which while who whom why will with would you your yours
case cases judgment judgments find show tell give list any regarding related
whether did does please
""".split())

# Storytelling words of case descriptions ("my client says the other side
# argued ..."). Only applied to narratives; a short query keeps them.
NARRATIVE_STOPWORDS = frozenset("""
says said say saying claim claims claimed claiming argue argues argued arguing contend contends
contended client clients side sides opposite opposing someone somebody people person
also later ever since got get gets getting went go goes going came come comes coming told tell
want wants wanted think thinks thought know knows knew like many much one ones thing
things time times day days back still even yet already never always just really
able made make makes making put took take takes taken gave give given lot whole etc
""".split())

MAX_TERMS = 64
NEAR_DISTANCE = 2

_WORD_PARTS = re.compile(r"[^\W_]+", re.UNICODE)


def _quote(term: str) -> str:
    return '"' + term.replace('"', '""') + '"'


def _is_narrative(analysis: QueryAnalysis) -> bool:
    if "is_narrative" in analysis:
        return bool(analysis.get("is_narrative"))
    from app.retrieval.contracts import NARRATIVE_MIN_WORDS
    return len((analysis.get("raw") or analysis.get("cleaned") or "").split()) >= NARRATIVE_MIN_WORDS


def query_terms(analysis: QueryAnalysis, path: Path | None = None) -> list[str]:
    """The quoted FTS5 terms and phrases for one query, deduplicated, in order.

    At most MAX_TERMS; when more are available the rarest plain words are kept
    (see "Case descriptions: noise words and salience").
    """
    texts = [analysis.get("cleaned") or analysis.get("raw") or ""]
    if analysis.get("rewrite"):
        texts.append(analysis["rewrite"])
    texts.extend(e for e in (analysis.get("expansions") or []) if e)
    stop = STOPWORDS | NARRATIVE_STOPWORDS if _is_narrative(analysis) else STOPWORDS

    terms: list[str] = []
    words: set[str] = set()     # plain single-word terms: the only ones salience may drop
    seen: set[str] = set()

    def add(term: str, plain: bool = False) -> None:
        if term and term not in seen:
            seen.add(term)
            terms.append(term)
            if plain:
                words.add(term)

    for text in texts:
        for token in str(text).lower().split():
            parts = _WORD_PARTS.findall(token)
            if not parts:
                continue
            if len(parts) == 1:
                word = parts[0]
                if len(word) > 1 and word not in stop:
                    add(_quote(word), plain=True)
                continue
            if all(len(p) == 1 and not p.isdigit() for p in parts):
                continue  # "c.a.", "s.m.c.": abbreviations, noise as BM25 terms
            if any(p.isdigit() for p in parts):
                # Citation-like: parts close together, a filler word allowed
                # ("5-Q/2014" must meet "5-Q OF 2014").
                add(f"NEAR({' '.join(_quote(p) for p in parts)}, {NEAR_DISTANCE})")
            else:
                add(_quote(" ".join(parts)))  # hyphenated name: exact phrase
            for part in parts:
                if part.isdigit() and len(part) >= 2:
                    add(_quote(part))
    if len(terms) <= MAX_TERMS:
        return terms
    return _salient(terms, words, path)


def _salient(terms: list[str], words: set[str], path: Path | None) -> list[str]:
    """Every structured term, then the rarest plain words, up to MAX_TERMS, in query order."""
    fixed = [t for t in terms if t not in words]
    plain = [t for t in terms if t in words]
    budget = max(0, MAX_TERMS - len(fixed))
    df = document_frequencies(plain, path)
    if df is None:   # no index to measure against: the old rule, first come first kept
        chosen = plain[:budget]
    else:
        order = {t: i for i, t in enumerate(plain)}
        chosen = sorted((t for t in plain if df.get(t, 0) > 0), key=lambda t: (df[t], order[t]))[:budget]
    keep = set(fixed) | set(chosen)
    return [t for t in terms if t in keep][:MAX_TERMS]


# (index path, mtime) -> {quoted term: chunk document frequency}
_df_cache: dict[tuple[str, float], dict[str, int]] = {}


def document_frequencies(terms: list[str], path: Path | None = None) -> dict[str, int] | None:
    """Chunk document frequency of each quoted term, via an FTS5 MATCH count.

    The query side of MATCH is stemmed exactly as the index was (porter), so the
    count is the term's real df without re-implementing the tokenizer. Cached
    per index file version; None when there is no index.
    """
    path = Path(path or db_path())
    try:
        key = (str(path), path.stat().st_mtime)
    except OSError:
        return None
    if key not in _df_cache:
        _df_cache.clear()   # the index was rebuilt: old counts are stale
        _df_cache[key] = {}
    cache = _df_cache[key]
    missing = [t for t in terms if t not in cache]
    if missing:
        conn = connect(path)
        try:
            for term in missing:
                try:
                    row = conn.execute("SELECT count(*) FROM chunks_fts WHERE chunks_fts MATCH ?",
                                       (term,)).fetchone()
                    cache[term] = int(row[0])
                except sqlite3.Error:
                    cache[term] = 0
        finally:
            conn.close()
    return {t: cache.get(t, 0) for t in terms}


def build_match(analysis: QueryAnalysis, path: Path | None = None) -> str:
    """The full MATCH expression: quoted terms OR'd together ("" if none)."""
    return " OR ".join(query_terms(analysis, path))


def _run(sql: str, params: tuple, path: Path | None) -> list[sqlite3.Row]:
    path = path or db_path()
    if not Path(path).exists():
        logger.warning(f"Lexical index {path} does not exist; run reindex.py --fts")
        return []
    conn = connect(path)
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


class BM25ChunksRetriever:
    """R2: BM25 over contextual-header chunks. One candidate per chunk."""

    name = "bm25_chunks"

    def __init__(self, path: Path | str | None = None):
        self.path = Path(path) if path else None

    def search(self, analysis: QueryAnalysis, k: int) -> list[Candidate]:
        match = build_match(analysis, self.path)
        if not match or k <= 0:
            return []
        rows = _run(
            "SELECT rowid, judgment_id, node_id, section_type, chunk_index, heading, text, "
            "bm25(chunks_fts) AS b FROM chunks_fts WHERE chunks_fts MATCH ? "
            "ORDER BY b LIMIT ?",
            (match, k), self.path,
        )
        return with_ranks([
            {
                "judgment_id": r["judgment_id"],
                "mongo_doc_id": r["node_id"],
                "vector_id": f"{r['node_id']}::{r['chunk_index']}",
                "section_type": r["section_type"],
                "heading": r["heading"] or "",
                "chunk_index": int(r["chunk_index"] or 0),
                "text": r["text"],
                "score": float(-r["b"]),
            }
            for r in rows
        ], self.name)

    async def retrieve(self, analysis: QueryAnalysis, k: int) -> list[Candidate]:
        try:
            return await asyncio.to_thread(self.search, analysis, k)
        except Exception as e:
            logger.warning(f"bm25_chunks failed, returning []: {e}")
            return []


class BM25CardsRetriever:
    """R3: BM25 over case cards, party and case-number columns weighted up.

    One candidate per judgment; mongo_doc_id is "" and section_type "CARD", as
    the contract specifies for card-level hits. Empty until case_cards exist.
    """

    name = "bm25_cards"

    def __init__(self, path: Path | str | None = None):
        self.path = Path(path) if path else None

    def search(self, analysis: QueryAnalysis, k: int) -> list[Candidate]:
        match = build_match(analysis, self.path)
        if not match or k <= 0:
            return []
        weights = ", ".join(str(w) for w in CARD_WEIGHTS)
        rows = _run(
            f"SELECT rowid, judgment_id, {', '.join(CARD_COLUMNS)}, "
            f"bm25(cards_fts, {weights}) AS b FROM cards_fts WHERE cards_fts MATCH ? "
            "ORDER BY b LIMIT ?",
            (match, k), self.path,
        )
        out: list[Candidate] = []
        for r in rows:
            text = "\n".join(f"{col}: {r[col]}" for col in CARD_COLUMNS if r[col])
            out.append({
                "judgment_id": r["judgment_id"],
                "mongo_doc_id": "",
                "vector_id": f"card:{r['judgment_id']}",
                "section_type": "CARD",
                "heading": r["case_display"] or "",
                "chunk_index": 0,
                "text": text,
                "score": float(-r["b"]),
            })
        return with_ranks(out, self.name)

    async def retrieve(self, analysis: QueryAnalysis, k: int) -> list[Candidate]:
        try:
            return await asyncio.to_thread(self.search, analysis, k)
        except Exception as e:
            logger.warning(f"bm25_cards failed, returning []: {e}")
            return []


if __name__ == "__main__":
    from app.retrieval.query_preprocessor import clean_query

    logger.remove()

    def analysis(q: str, **extra) -> QueryAnalysis:
        return {"raw": q, "cleaned": clean_query(q), **extra}  # type: ignore[return-value]

    # Query construction.
    terms = query_terms(analysis("C.A. 23-P/2017 under Article 185(3) and s.302"))
    assert 'NEAR("23" "p" "2017", 2)' in terms and 'NEAR("185" "3", 2)' in terms, terms
    assert 'NEAR("s" "302", 2)' in terms and '"c a"' not in terms, terms
    assert '"23"' in terms and '"2017"' in terms and '"185"' in terms
    assert '"noor ul basar"' in query_terms(analysis("Pirzada Noor-ul-Basar"))
    assert '"and"' not in terms and '"under"' not in terms
    assert query_terms(analysis("the of and")) == []
    with_rewrite = query_terms(analysis("brand owner", rewrite="trade mark assignment",
                                        expansions=["proprietor of mark"]))
    assert '"trade"' in with_rewrite and '"proprietor"' in with_rewrite
    print(f"OK: query construction, e.g. {terms}")

    # Narratives: storytelling words dropped; short queries keep them.
    story = ("My client says the other side argued that the suit was time-barred and that the "
             "Family Court alone had jurisdiction over the dower land, but the High Court decreed it.")
    n_terms = query_terms(analysis(story))
    assert '"says"' not in n_terms and '"client"' not in n_terms and '"side"' not in n_terms, n_terms
    assert '"dower"' in n_terms and '"decreed"' in n_terms
    assert '"says"' in query_terms(analysis("what the client says"))
    # Over budget: structured terms always kept, then the rarest words; tail words survive.
    if Path(db_path()).exists():
        filler = " ".join(f"court appeal order section zzqx{i}" for i in range(70))
        long_terms = query_terms(analysis(f"C.A. 23-P/2017 {filler} dower nikah mutation"))
        assert len(long_terms) <= MAX_TERMS and 'NEAR("23" "p" "2017", 2)' in long_terms, long_terms
        assert '"dower"' in long_terms and '"nikah"' in long_terms, "rare tail terms must survive"
        assert not any(t.startswith('"zzqx') for t in long_terms), "a term in no chunk is dropped"
        df = document_frequencies(['"dower"', '"court"'])
        assert df['"court"'] > df['"dower"'] > 0, df
        print(f"OK: narrative stopwords; salience keeps rare tail terms (df {df})")

    # Hostile input never escapes as FTS5 syntax or an exception.
    chunks, cards = BM25ChunksRetriever(), BM25CardsRetriever()
    for hostile in ['"', 'NEAR(a b)', 'text:foo', 'a AND OR NOT', '*', "'; DROP TABLE x;--",
                    '"unterminated', '((((', '']:
        got = asyncio.run(chunks.retrieve(analysis(hostile), 10))
        assert isinstance(got, list)
        assert isinstance(asyncio.run(cards.retrieve({"raw": hostile, "cleaned": hostile}, 10)), list)
    assert asyncio.run(BM25ChunksRetriever("does/not/exist.db").retrieve(analysis("x y"), 5)) == []
    print("OK: hostile queries and a missing index return lists, never raise")

    # Real retrieval against the built index.
    if Path(db_path()).exists():
        got = asyncio.run(chunks.retrieve(
            analysis("general elections 2013 National Assembly seat NA-266 Nasirabad Jaffarabad"), 20))
        assert got and got[0]["judgment_id"] == "5a14105d-8a45-413c-8c93-26d6301cf028", got[:1]
        assert [c["rank"] for c in got] == list(range(len(got)))
        assert all(got[i]["score"] >= got[i + 1]["score"] for i in range(len(got) - 1))
        assert got[0]["source"] == "bm25_chunks" and got[0]["mongo_doc_id"]
        print(f"OK: NA-266 query -> {got[0]['judgment_id'][:8]} {got[0]['section_type']} "
              f"score {got[0]['score']:.2f}")
    else:
        print("SKIP: no lexical.db yet (python reindex.py --fts)")
