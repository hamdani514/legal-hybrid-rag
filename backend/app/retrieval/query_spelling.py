"""
Correcting typing mistakes in a search query, against the judgments' own words.

Why
---
Searches failed on ordinary typos: "NAB casey on bael nab ordinence" found
nothing, "naib bail ordinance" 5 cases instead of 28. The meaning-based
retrievers tolerate a typo, but the cross-encoder that decides what is shown,
and the key-word rules, read the words literally: "bael" is in no judgment.

How (careful by design)
-----------------------
app.retrieval.spelling handles known transliterations ("nikkah" -> "nikah").
This module handles typos, and only these three kinds:

1. A word in no judgment at all ("bael", "murdr", "arest") becomes the closest
   common word of the index (one edit for short words, two for long ones,
   same first letter): "bail", "murder", "arrest".
2. A word in very few passages, typed in lower case ("casey": 3 judgments)
   becomes a far commoner close word ("case").
3. A real but rarer word ("naib", as in naib tehsildar) is changed only when
   the query's other words say so: "naib bail ordinance" -> the judgments with
   bail and ordinance mention "nab" far more often than "naib", so "nab";
   "naib tehsildar seniority" keeps "naib".

Never corrected: an English word (the embedding model's own 30,000-word
vocabulary): "bounced", "stole", "cake" are not typos of "bound", "sole",
"case", though no judgment uses them; nor a capitalised word inside the query
(a party's name) unless no judgment has it. Measured on the 207 evaluation
queries (correctly spelled, many with everyday words): without the English
check 19 were wrongly changed ("bounced cheque" -> "bound"), with it none.
If the vocabulary cannot be read, nothing is corrected. The corrected query is used for the whole search, and the results say
"Showing results for ..." so the user sees what was searched.
"""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from app.indexing.fts_index import connect, db_path

COMMON_MIN = 20          # passages: a correction must be a common word of the index
RARE_MAX = 10            # passages: at or under this, a lower-case word may be a typo (rule 2)
RARE_RATIO = 50          # rule 2: the correction is at least this many times commoner
REAL_RATIO = 3           # rule 3: the correction is at least this many times commoner ...
CONTEXT_RATIO = 5        # ... and co-occurs with the query's other words this many times more
CONTEXT_MIN = 3          # ... in at least this many judgments
MAX_CONTEXT_WORDS = 3

_WORD_RE = re.compile(r"[A-Za-z]+")
_vocab: dict = {"key": None, "terms": []}
_english: dict = {"words": None}


def english_words() -> set[str]:
    """Whole words of the embedding model's vocabulary (offline, from the
    Hugging Face cache); empty if it cannot be read."""
    if _english["words"] is None:
        words: set[str] = set()
        try:
            from huggingface_hub import try_to_load_from_cache
            from app.config import settings
            path = try_to_load_from_cache(settings.EMBEDDING_MODEL, "vocab.txt")
            if isinstance(path, str):
                with open(path, encoding="utf-8") as fh:
                    words = {w for w in (line.strip() for line in fh) if w.isalpha() and w.islower()}
        except Exception:  # noqa: BLE001 - no vocabulary: correct nothing
            words = set()
        _english["words"] = words
    return _english["words"]


def _stop() -> set[str]:
    from app.retrieval.lexical import STOPWORDS, TERM_EQUIVALENTS
    return set(STOPWORDS) | set(TERM_EQUIVALENTS)


def _common_words(conn: sqlite3.Connection, path: Path) -> list[tuple[str, int]]:
    """(stem, passages) of every common alphabetic word of the index, cached
    until the index file changes."""
    key = (str(path), path.stat().st_mtime)
    if _vocab["key"] != key:
        conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS temp.chunks_vocab USING fts5vocab(main, 'chunks_fts', 'row')")
        _vocab["terms"] = [(t, d) for t, d in conn.execute(
            "SELECT term, doc FROM temp.chunks_vocab WHERE doc >= ?", (COMMON_MIN,)) if t.isalpha()]
        _vocab["key"] = key
    return _vocab["terms"]


def _passages(conn: sqlite3.Connection, word: str) -> int:
    try:
        return int(conn.execute("SELECT count(*) FROM chunks_fts WHERE chunks_fts MATCH ?", (f'"{word}"',)).fetchone()[0])
    except sqlite3.Error:
        return 0


def _judgments(conn: sqlite3.Connection, words: list[str]) -> int:
    try:
        return int(conn.execute("SELECT count(DISTINCT judgment_id) FROM chunks_fts WHERE chunks_fts MATCH ?",
                                (" AND ".join(f'"{w}"' for w in words),)).fetchone()[0])
    except sqlite3.Error:
        return 0


def distance(a: str, b: str, limit: int) -> int:
    """Edit distance with transpositions (optimal string alignment); any value
    above `limit` is returned as limit + 1."""
    if abs(len(a) - len(b)) > limit:
        return limit + 1
    prev2, prev = None, list(range(len(b) + 1))
    for i in range(1, len(a) + 1):
        cur = [i] + [0] * len(b)
        for j in range(1, len(b) + 1):
            cost = a[i - 1] != b[j - 1]
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                cur[j] = min(cur[j], prev2[j - 2] + 1)
        if min(cur) > limit:
            return limit + 1
        prev2, prev = prev, cur
    return prev[-1]


def _closest(word: str, vocab: list[tuple[str, int]], limit: int, min_passages: int,
             conn: sqlite3.Connection | None = None, others: list[str] | None = None) -> tuple[str, int] | None:
    """The closest common word; among equally close ones, the one found most
    often with the query's other words ("dowr" in a family-court query is
    "dower", not the commoner "down"), else the commonest."""
    near: list[tuple[int, str, int]] = []
    for term, n in vocab:
        if term[0] != word[0] or n < min_passages or term == word:
            continue
        d = distance(word, term, limit)
        if d <= limit:
            near.append((d, term, n))
    if not near:
        return None
    best_d = min(d for d, _, _ in near)
    tied = sorted(((t, n) for d, t, n in near if d == best_d), key=lambda x: -x[1])[:12]
    if len(tied) > 1 and conn is not None and others:
        # The SHARE of each candidate's judgments that also contain the other
        # words, not the raw count: a word as common as "down" ("laid down")
        # co-occurs with anything; "dower" with "family" and "recovery".
        # A context word may itself be rare or mistyped ("cort"): if no
        # candidate occurs with all of them, try with fewer.
        for k in range(len(others), 0, -1):
            context = others[-k:]          # the commoner ones first to stay
            scored = []
            for t, n in tied:
                joint = _judgments(conn, [t] + context)
                scored.append((joint / max(_judgments(conn, [t]), 1), joint, n, t))
            top = max(scored)
            if top[1] > 0:
                return top[3], top[2]
    return tied[0]


def _surface(stem: str, typed: str = "") -> str:
    """The index stores stems ("dowri" for dowry, "parti" for party); write
    the English word when the stem is one of its forms."""
    english = english_words()
    if stem in english:
        return stem
    # The user typed a final "y" ("anticipatry"): the stem's final "i" is it.
    if stem.endswith("i") and typed.lower().endswith("y"):
        return stem[:-1] + "y"
    # Porter writes a final "y" as "i" and drops a final "e".
    forms = ([stem[:-1] + "y"] if stem.endswith("i") else []) + [stem + "e"]
    return next((w for w in forms if w in english), stem)


def correct(text: str, path: Path | str | None = None) -> tuple[str, list[tuple[str, str]]]:
    """(the query with its typos corrected, [(typed, corrected), ...])."""
    text = str(text or "")
    path = Path(path or db_path())
    if not text.strip() or not path.exists():
        return text, []
    english = english_words()
    if not english:
        return text, []          # cannot tell a typo from a word: correct nothing
    stop = _stop()
    tokens = [(m, m.group(0)) for m in _WORD_RE.finditer(text)]
    words = [(m, w) for m, w in tokens if len(w) >= 3 and w.lower() not in stop]
    # Every word can serve as context; only a non-English word can be a typo.
    candidates = {i for i, (_, w) in enumerate(words) if w.lower() not in english}
    if not words:
        return text, []
    conn = connect(path)
    try:
        vocab = _common_words(conn, path)
        counts = {w.lower(): _passages(conn, w.lower()) for _, w in words}
        fixes: dict[int, str] = {}
        for i, (m, typed) in enumerate(words):
            if i not in candidates:
                continue
            word = typed.lower()
            n = counts[word]
            name_like = typed[0].isupper() and m.start() > 0 and not typed.isupper()
            limit = 1 if len(word) <= 8 else 2
            # The query's other known words, rarest first: the context.
            others = sorted((w.lower() for j, (_, w) in enumerate(words)
                             if j != i and counts[w.lower()] > 0), key=lambda w: counts[w])[:MAX_CONTEXT_WORDS]
            if n == 0:                                              # rule 1
                found = _closest(word, vocab, limit, COMMON_MIN, conn, others)
            elif n <= RARE_MAX and not name_like:                   # rule 2
                found = _closest(word, vocab, limit, max(COMMON_MIN, n * RARE_RATIO), conn, others)
            elif not name_like:                                     # rule 3: needs context
                found = _closest(word, vocab, 1, n * REAL_RATIO, conn, others)
                if found and others:
                    with_typed = _judgments(conn, [word] + others)
                    with_fix = _judgments(conn, [found[0]] + others)
                    if not (with_fix >= CONTEXT_MIN and with_fix >= CONTEXT_RATIO * max(with_typed, 1)):
                        found = None
                else:
                    found = None
            else:
                found = None
            if found:
                fixes[m.start()] = found[0]
    finally:
        conn.close()
    if not fixes:
        return text, []
    out, at, pairs = [], 0, []
    for m, typed in tokens:
        if m.start() in fixes:
            out.append(text[at:m.start()])
            fixed = _surface(fixes[m.start()], typed)
            out.append(fixed.upper() if typed.isupper() and len(typed) > 1 else fixed)
            pairs.append((typed, fixed))
            at = m.end()
    out.append(text[at:])
    return "".join(out), pairs


if __name__ == "__main__":
    import sys
    cases = {
        # typos -> the word the judgments use
        "NAB casey on bael nab ordinence": "NAB casey on bail nab ordinence",   # casey: an English word
        "naib bail ordinance": "nab bail ordinance",
        "pre arest bail in murdr case": "pre arrest bail in murder case",
        # "dowr" is dower or dowry: either is right, never "down".
        "recovery of dowr in family court": ("recovery of dower in family court", "recovery of dowry in family court"),
        "recovery of dowr in family cort": ("recovery of dower in family court", "recovery of dowry in family court"),
        # left alone: correct words, a real word in its own context, a name, sections
        "NAB bail ordinance": "NAB bail ordinance",
        "naib tehsildar seniority promotion": "naib tehsildar seniority promotion",
        "pre arrest bail in 377": "pre arrest bail in 377",
        "bail u/s 302/34 PPC": "bail u/s 302/34 PPC",
        "Maqbool Ahmed Mahessar NAB": "Maqbool Ahmed Mahessar NAB",
        "cheque bounced bail 489-F": "cheque bounced bail 489-F",
        "anticipatry bail": "anticipatory bail",
        "symptoms of dengue fever in children": "symptoms of dengue fever in children",
    }
    bad = 0
    for q, want in cases.items():
        got, pairs = correct(q)
        ok = got in want if isinstance(want, tuple) else got == want
        bad += not ok
        print(f"  {'OK  ' if ok else 'FAIL'} {q!r:42} -> {got!r}  {pairs}")
    sys.exit(f"{bad} spelling case(s) failed") if bad else print(f"OK: {len(cases)} spelling cases.")
