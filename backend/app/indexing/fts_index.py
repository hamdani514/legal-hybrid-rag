"""
SQLite FTS5 lexical index over judgment chunks and case cards.

Why a lexical index at all
--------------------------
Dense retrieval is good at meaning and bad at names. A bge vector for
"Mir Saleem Ahmed Khosa versus Zafarullah Khan Jamali" does not land next to the
chunk holding those names: rare proper nouns, constituency codes ("NA-266") and
section numbers are exactly the tokens an embedding model smooths away. BM25
rewards them, because a rare token that matches is the strongest evidence it
has. The two retrievers fail on different queries, which is why fusing them
works.

Why SQLite FTS5
---------------
It ships inside Python's sqlite3 (verified: SQLite 3.45 with FTS5 and bm25()),
so there is no new service to run, no new dependency, and the index is one file
next to chroma_db. At the real corpus size (3,000+ judgments, ~36,500 chunks)
an FTS5 query over OR'd terms answers in a few milliseconds.

Tables (in backend/lexical.db, or settings.LEXICAL_DB_PATH)
----------------------------------------------------------
    chunks_fts  one row per section chunk; `text` is the chunk WITH its
                contextual header, so a passage from the middle of a judgment
                still carries the case it belongs to. Chunk boundaries come
                from app.embeddings.chunker.chunk_node on the same MongoDB
                section nodes the dense index is built from, so chunk N here is
                chunk N in Chroma ("{node_id}::{chunk_index}").
    cards_fts   one row per case card (MongoDB `case_cards`, Agent B). Empty
                until cards exist; nothing else depends on it being full.
    index_meta  build provenance: tokenizer, schema version, counts, time.

Tokenizer choice: ``porter unicode61 remove_diacritics 2``
-----------------------------------------------------------
unicode61 splits on every non-alphanumeric character, so "23-P/2017" indexes as
``23 p 2017``, "s.302" as ``s 302`` and "Article 185(3)" as ``article 185 3``.
We considered keeping "-" "/" "." as token characters (tokenchars) so those
stay whole, and rejected it: "." as a token character glues every
sentence-final word to its full stop ("court." != "court"), and "-"/"/" make
"23-P/2017" in a query fail to match "23-P OF 2017" in a header anyway. Instead
the QUERY side (app.retrieval.lexical) turns a compound token into an FTS5
phrase — "23-P/2017" becomes the phrase "23 p 2017", which only matches those
tokens adjacent and in order — so precision is kept without a custom tokenizer.
Case-number lookup proper is the exact-match retriever's job (case_keys), not
BM25's. Porter stemming lets "allotted" match "allotment"-style variants in
paraphrase queries; remove_diacritics folds the occasional accented name.

Rebuild and upsert
------------------
``rebuild()`` writes a complete fresh index to a temporary file and swaps it in,
so a reader never sees a half-built index and a re-run is idempotent.
``upsert_judgment()`` replaces one judgment's rows in place, for ingestion of a
new judgment without a full rebuild.
"""

import asyncio
import os
import sqlite3
import sys
import time
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from loguru import logger

from app.config import settings

BACKEND_DIR = Path(__file__).resolve().parents[2]

TOKENIZER = "porter unicode61 remove_diacritics 2"
SCHEMA_VERSION = 1

# Card columns, in table order. The weights are BM25 column weights used by the
# cards retriever: a match on a party name or the case number is much stronger
# evidence than a match somewhere in the headnote.
CARD_COLUMNS: tuple[str, ...] = (
    "case_display", "case_keys", "appellant", "respondent", "bench", "statutes",
    "subject", "headnote", "issues", "holding", "keywords",
)
CARD_WEIGHTS: tuple[float, ...] = (3.0, 3.0, 4.0, 4.0, 1.5, 2.0, 1.5, 1.0, 1.0, 1.0, 2.0)

SECTION_LEVEL = 2
ROOT_LEVEL = 1


def db_path() -> Path:
    """Where the lexical index lives: settings.LEXICAL_DB_PATH, else backend/lexical.db."""
    configured = getattr(settings, "LEXICAL_DB_PATH", "") or ""
    return Path(configured) if configured else BACKEND_DIR / "lexical.db"


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    """Open the index. Callers open one connection per call and close it."""
    conn = sqlite3.connect(str(path or db_path()), timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Create the tables if they do not exist. Safe to call repeatedly."""
    conn.execute(
        "CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5("
        "text, judgment_id UNINDEXED, node_id UNINDEXED, section_type UNINDEXED, "
        f"chunk_index UNINDEXED, heading UNINDEXED, tokenize='{TOKENIZER}')"
    )
    conn.execute(
        "CREATE VIRTUAL TABLE IF NOT EXISTS cards_fts USING fts5("
        + ", ".join(CARD_COLUMNS)
        + f", judgment_id UNINDEXED, tokenize='{TOKENIZER}')"
    )
    conn.execute("CREATE TABLE IF NOT EXISTS index_meta (key TEXT PRIMARY KEY, value TEXT)")


def _join(value) -> str:
    """Card fields are strings or lists of strings; FTS wants one string."""
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return "; ".join(str(v) for v in value if v)
    return str(value)


def card_row(card: dict) -> list[str]:
    """One cards_fts row (indexed columns then judgment_id) from a CaseCard."""
    return [_join(card.get(col)) for col in CARD_COLUMNS] + [card.get("judgment_id", "")]


# ── Reading the source data out of MongoDB ──────────────────────────────────

async def _database():
    from app.database import connect_db, db
    if db.database is None:
        await connect_db()
    return db.database


async def load_cards(judgment_ids: list[str] | None = None) -> dict[str, dict]:
    """Case cards by judgment_id. Empty when Agent B's collection is absent or empty."""
    database = await _database()
    if database is None:
        return {}
    query = {"judgment_id": {"$in": judgment_ids}} if judgment_ids else {}
    cards: dict[str, dict] = {}
    try:
        async for card in database.case_cards.find(query, {"_id": 0}):
            if card.get("judgment_id"):
                cards[card["judgment_id"]] = card
    except Exception as e:
        logger.warning(f"Could not read case_cards: {e}")
    return cards


async def judgment_ids() -> list[str]:
    """Every pdf_id that has nodes in MongoDB, in a stable order."""
    database = await _database()
    return sorted({d for d in await database.nodes.distinct("pdf_id") if d})


async def judgment_chunks(
    judgment_id: str,
    card: dict | None = None,
    include_root: bool = False,
) -> list[dict]:
    """Every chunk of one judgment, each with its contextual header prepended.

    Args:
        judgment_id: The pdf_id.
        card: Its CaseCard, if Agent B has built one. Without it the header
            falls back to the root node's title, which ingestion sets to the
            case display ("Civil Appeal No. 5-Q OF 2014").
        include_root: Also return the root node as a single level-1 chunk, as
            the live dense index does. The FTS index leaves roots out.

    Returns:
        Dicts with vector_id, judgment_id, node_id, parent_node_id, level,
        section_type, heading, chunk_index, chunk_count, header, body (the
        chunk_node text) and text (header + body — what gets indexed).
    """
    from app.embeddings.chunker import chunk_node
    from app.retrieval.contracts import contextual_header

    database = await _database()
    nodes = await database.nodes.find({"pdf_id": judgment_id}, {"_id": 0}).to_list(length=None)
    root = next((n for n in nodes if n.get("type") == "parent"), None)
    case_title = ((root or {}).get("title") or "").strip()

    out: list[dict] = []
    for node in nodes:
        is_root = node.get("type") == "parent"
        if is_root and not include_root:
            continue
        section_type = node.get("section_type") or ("ROOT" if is_root else "")
        title = node.get("title") or ""
        text = node.get("text") or ""
        if is_root:
            combined = f"{title}\n\n{text}" if text else title
            pieces = [{"text": combined, "chunk_index": 0}] if combined else []
        else:
            pieces = chunk_node(title, text)
        header = contextual_header(card, section_type, case_title)
        for piece in pieces:
            body = piece["text"]
            out.append({
                "vector_id": f"{node['node_id']}::{piece['chunk_index']}",
                "judgment_id": judgment_id,
                "node_id": node["node_id"],
                "parent_node_id": node.get("parent_node_id") or "",
                "level": ROOT_LEVEL if is_root else SECTION_LEVEL,
                "section_type": section_type,
                "heading": title,
                "chunk_index": piece["chunk_index"],
                "chunk_count": len(pieces),
                "header": header,
                "body": body,
                "text": f"{header}\n{body}" if header else body,
            })
    return out


# ── Writing ──────────────────────────────────────────────────────────────────

def _write_judgment(conn: sqlite3.Connection, judgment_id: str,
                    chunks: list[dict], card: dict | None) -> None:
    conn.execute("DELETE FROM chunks_fts WHERE judgment_id = ?", (judgment_id,))
    conn.execute("DELETE FROM cards_fts WHERE judgment_id = ?", (judgment_id,))
    conn.executemany(
        "INSERT INTO chunks_fts (text, judgment_id, node_id, section_type, chunk_index, heading) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [(c["text"], judgment_id, c["node_id"], c["section_type"], c["chunk_index"],
          (c["heading"] or "")[:200]) for c in chunks if c["level"] == SECTION_LEVEL],
    )
    if card:
        placeholders = ", ".join("?" * (len(CARD_COLUMNS) + 1))
        conn.execute(
            f"INSERT INTO cards_fts ({', '.join(CARD_COLUMNS)}, judgment_id) VALUES ({placeholders})",
            card_row({**card, "judgment_id": judgment_id}),
        )


def _set_meta(conn: sqlite3.Connection, **values) -> None:
    conn.executemany(
        "INSERT OR REPLACE INTO index_meta (key, value) VALUES (?, ?)",
        [(k, str(v)) for k, v in values.items()],
    )


def counts(path: Path | str | None = None) -> dict[str, int]:
    """Row counts of both tables; zeros if the index does not exist yet."""
    path = Path(path or db_path())
    if not path.exists():
        return {"chunks": 0, "cards": 0, "judgments": 0}
    conn = connect(path)
    try:
        ensure_schema(conn)
        return {
            "chunks": conn.execute("SELECT count(*) FROM chunks_fts").fetchone()[0],
            "cards": conn.execute("SELECT count(*) FROM cards_fts").fetchone()[0],
            "judgments": conn.execute(
                "SELECT count(DISTINCT judgment_id) FROM chunks_fts").fetchone()[0],
        }
    finally:
        conn.close()


async def upsert_judgment(judgment_id: str, path: Path | str | None = None) -> int:
    """Replace one judgment's rows (chunks and card). Returns chunks written.

    For ingestion: call after the judgment's nodes (and, later, its card) are
    in MongoDB. A judgment with no nodes is simply removed from the index.
    """
    cards = await load_cards([judgment_id])
    chunks = await judgment_chunks(judgment_id, cards.get(judgment_id))
    conn = connect(path)
    try:
        ensure_schema(conn)
        with conn:
            _write_judgment(conn, judgment_id, chunks, cards.get(judgment_id))
            _set_meta(conn, last_upsert=time.strftime("%Y-%m-%dT%H:%M:%S"))
    finally:
        conn.close()
    logger.info(f"FTS upsert {judgment_id[:8]}: {len(chunks)} chunks, "
                f"card={'yes' if judgment_id in cards else 'no'}")
    return len(chunks)


def remove_judgment(judgment_id: str, path: Path | str | None = None) -> None:
    """Delete one judgment's rows from both tables."""
    conn = connect(path)
    try:
        ensure_schema(conn)
        with conn:
            conn.execute("DELETE FROM chunks_fts WHERE judgment_id = ?", (judgment_id,))
            conn.execute("DELETE FROM cards_fts WHERE judgment_id = ?", (judgment_id,))
    finally:
        conn.close()


async def rebuild(path: Path | str | None = None, progress: bool = False,
                  use_cards: bool = True) -> dict:
    """Full, idempotent rebuild of both tables from MongoDB.

    Writes a fresh database beside the target and swaps it in, so readers see
    either the old index or the new one, never a half-written one. If the swap
    is blocked (Windows will not replace a file another process holds open),
    the rebuild is redone in place inside one transaction instead.
    """
    target = Path(path or db_path())
    started = time.perf_counter()
    ids = await judgment_ids()
    # use_cards=False builds the no-card variant (headers from root titles,
    # empty cards_fts) — for ablation only.
    cards = await load_cards() if use_cards else {}

    per_judgment: list[tuple[str, list[dict]]] = []
    for index, judgment_id in enumerate(ids, start=1):
        chunks = await judgment_chunks(judgment_id, cards.get(judgment_id))
        per_judgment.append((judgment_id, chunks))
        if progress:
            print(f"  [{index}/{len(ids)}] {judgment_id[:8]}  {len(chunks)} chunks")

    def write(conn: sqlite3.Connection, fresh: bool) -> None:
        ensure_schema(conn)
        with conn:
            if not fresh:
                conn.execute("DELETE FROM chunks_fts")
                conn.execute("DELETE FROM cards_fts")
            for judgment_id, chunks in per_judgment:
                _write_judgment(conn, judgment_id, chunks, cards.get(judgment_id))
            # Cards for judgments with no nodes would be unreachable downstream; skip them.
            _set_meta(
                conn, schema_version=SCHEMA_VERSION, tokenizer=TOKENIZER,
                built_at=time.strftime("%Y-%m-%dT%H:%M:%S"), judgments=len(ids),
                cards=sum(1 for j in ids if j in cards),
            )
            conn.execute("INSERT INTO chunks_fts(chunks_fts) VALUES ('optimize')")
            conn.execute("INSERT INTO cards_fts(cards_fts) VALUES ('optimize')")

    tmp = target.with_name(target.name + ".tmp")
    if tmp.exists():
        tmp.unlink()
    conn = connect(tmp)
    try:
        write(conn, fresh=True)
    finally:
        conn.close()
    try:
        os.replace(tmp, target)
    except OSError as e:
        logger.warning(f"Could not swap in the new index ({e}); rebuilding in place")
        tmp.unlink(missing_ok=True)
        conn = connect(target)
        try:
            write(conn, fresh=False)
        finally:
            conn.close()

    stats = {**counts(target), "elapsed_s": round(time.perf_counter() - started, 2),
             "path": str(target)}
    logger.info(f"FTS rebuild: {stats}")
    return stats


if __name__ == "__main__":
    import tempfile

    logger.remove()
    logger.add(sys.stderr, level="WARNING")

    # 1. Tokenizer behaviour the module docstring promises.
    conn = sqlite3.connect(":memory:")
    ensure_schema(conn)
    conn.execute(
        "INSERT INTO chunks_fts (text, judgment_id, node_id, section_type, chunk_index, heading) "
        "VALUES (?, 'j1', 'n1', 'FACTS', 0, '')",
        ("CIVIL APPEAL NO. 23-P OF 2017 under Article 185(3); s.302 PPC. Land was allotted.",),
    )
    def hits(match: str) -> int:
        return conn.execute("SELECT count(*) FROM chunks_fts WHERE chunks_fts MATCH ?",
                            (match,)).fetchone()[0]
    assert hits('"185 3"') == 1, "Article 185(3) must be findable as a phrase"
    assert hits('"s 302"') == 1, "s.302 must be findable as a phrase"
    assert hits('"23 p"') == 1
    assert hits('"allotment"') == 1, "porter: allotment and allotted share the stem allot"
    assert hits('"court"') == 0 and hits('"23 2017"') == 0, "phrases need adjacency"
    print("OK: tokenizer splits citations into phrase-searchable tokens")

    # 2. card_row flattens lists.
    row = card_row({"judgment_id": "j", "bench": ["A", "B"], "case_display": "C.A. 1"})
    assert row[CARD_COLUMNS.index("bench")] == "A; B" and row[-1] == "j"
    assert len(row) == len(CARD_COLUMNS) + 1
    print("OK: card rows")

    # 3. A real rebuild into a temp file, then an idempotent re-run and an upsert.
    async def real() -> None:
        tmp_path = Path(tempfile.mkdtemp()) / "lexical_selftest.db"
        first = await rebuild(tmp_path)
        assert first["chunks"] > 0 and first["judgments"] > 0, first
        second = await rebuild(tmp_path)
        assert second["chunks"] == first["chunks"], "rebuild must be idempotent"
        one = (await judgment_ids())[0]
        written = await upsert_judgment(one, tmp_path)
        assert counts(tmp_path)["chunks"] == first["chunks"], "upsert must not duplicate rows"
        remove_judgment(one, tmp_path)
        assert counts(tmp_path)["chunks"] == first["chunks"] - written
        conn2 = connect(tmp_path)
        sample = conn2.execute("SELECT text FROM chunks_fts LIMIT 1").fetchone()[0]
        conn2.close()
        assert sample.startswith("["), f"chunks must carry the contextual header: {sample[:80]!r}"
        print(f"OK: rebuild {first['chunks']} chunks / {first['judgments']} judgments / "
              f"{first['cards']} cards in {first['elapsed_s']}s; idempotent; upsert/remove work")
        print(f"    sample header: {sample.splitlines()[0]!r}")

    asyncio.run(real())
