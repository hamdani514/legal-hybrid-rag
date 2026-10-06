"""
Keep every derived store in step with a single judgment's lifecycle, and
record which stores are written.

A judgment is searchable only when its stores are written, in this order
(app.retrieval.contracts.INDEX_STORES):

    tree         MongoDB nodes + document_trees        (tree_builder.ensure_tree)
    dense        live Chroma collection + embedding_mappings + connection JSON
                                                        (embedding_pipeline)
    fts          backend/lexical.db FTS5 rows           (fts_index.upsert_judgment)
    card         MongoDB case_cards, card_status complete (case_card; 1 LLM call)
    card_vector  settings.CARDS_COLLECTION, one vector per card

Why per-store status
--------------------
Before this, documents.status said "complete" as soon as the tree existed, so a
bulk-ingested judgment with no vectors and no keyword rows looked finished; a
failed embedding was labelled a parse failure; and index_judgment's report was
logged and thrown away. Now every store write is recorded on
documents.index_status (contracts.IndexStatus, mirrored onto jobs.index_status
for the admin page) and documents.status is DERIVED from it:

    uploaded -> extracted -> parsed      pipeline stages (unchanged)
    indexing     tree written; dense/fts not yet
    searchable   every INDEX_REQUIRED_FOR_SEARCH store written (tree, dense,
                 fts); search finds it. The card may arrive later (card wave).
    complete     searchable AND a complete card AND its card vector
    failed       a stage failed; index_status.last_error says which and why

The card is required for "complete" but not for search: on the Gemini free tier
cards come in a separate, resumable wave (python -m app.ingestion.case_card
--all), so bulk ingest never waits on the quota to make a judgment findable.

Best effort, but honest
-----------------------
index_judgment still never raises (a 429 on the card call must not fail an
upload whose vectors are saved), but its report is now persisted into
index_status.report and the flags it implies are recorded. complete_judgment,
used by the admin path, bulk ingest, retry and check --repair, DOES raise
StoreError when a store required for search fails, so callers can mark the job
failed at the right stage.

The contextual collection (chunks embedded with case headers) is built only
when settings.CONTEXTUAL_INDEXING is on: live search never reads it and it
doubled embedding CPU on every upload.
"""

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from loguru import logger

from app.config import settings
from app.database import db
from app.retrieval.contracts import INDEX_REQUIRED_FOR_SEARCH, INDEX_STORES

# The experiment collection reindex.py --contextual builds.
DEFAULT_CONTEXTUAL_COLLECTION = "legal_embeddings_v3_ctx"

# Local working copies of one judgment, under backend/uploads/.
UPLOADS_DIR = Path(__file__).resolve().parents[2] / "uploads"
LOCAL_COPY_SUFFIXES = (".pdf", ".txt", "_sections.json", "_summary.md")

# documents.status values owned by the indexing stages (see module docstring).
STATUS_INDEXING = "indexing"
STATUS_SEARCHABLE = "searchable"
STATUS_COMPLETE = "complete"
STATUS_FAILED = "failed"
IN_FLIGHT_STATUSES = ("uploaded", "extracting", "extracted", "parsing", "parsed", STATUS_INDEXING)


class StoreError(RuntimeError):
    """A store required for search could not be written."""

    def __init__(self, store: str, message: str):
        super().__init__(f"{store}: {message}")
        self.store = store


def _contextual_name() -> str:
    return getattr(settings, "CONTEXTUAL_COLLECTION", DEFAULT_CONTEXTUAL_COLLECTION)


def contextual_enabled() -> bool:
    return bool(getattr(settings, "CONTEXTUAL_INDEXING", False))


def _collection(name: str):
    from app.vectorstore.chroma_store import chroma_store

    return chroma_store.client.get_or_create_collection(name=name, metadata={"hnsw:space": "cosine"})


def _existing_collection(name: str):
    """The collection if it exists, else None (never creates one)."""
    from app.vectorstore.chroma_store import chroma_store

    try:
        return chroma_store.client.get_collection(name=name)
    except Exception:
        return None


# ── status ───────────────────────────────────────────────────────────────────

def derive_doc_status(index_status: dict) -> str | None:
    """complete / searchable from the store flags, or None if not searchable yet."""
    if all(index_status.get(s) for s in INDEX_REQUIRED_FOR_SEARCH):
        return STATUS_COMPLETE if all(index_status.get(s) for s in INDEX_STORES) else STATUS_SEARCHABLE
    return None


async def record_index_status(pdf_id: str, *, error: str | None = None, clear_error: bool = False,
                              report: dict | None = None, failed: bool = False, **flags) -> dict:
    """Merge store flags into documents.index_status and re-derive documents.status.

    Args:
        flags: any of INDEX_STORES -> bool. Unnamed stores keep their value.
        error: recorded as index_status.last_error (prefix it with the store).
        clear_error: drop last_error (every attempted step succeeded).
        report: index_judgment's per-step report, persisted as index_status.report.
        failed: also set documents.status = "failed" (a required stage failed).

    Returns the new index_status ({} if the document does not exist).
    """
    if db.database is None:
        return {}
    doc = await db.documents.find_one({"pdf_id": pdf_id}, {"index_status": 1, "status": 1})
    if not doc:
        return {}
    ix = dict(doc.get("index_status") or {})
    for store, value in flags.items():
        if store not in INDEX_STORES:
            raise ValueError(f"unknown store {store!r}")
        ix[store] = bool(value)
    if error:
        ix["last_error"] = str(error)[:1000]
    elif clear_error:
        ix.pop("last_error", None)
    if report is not None:
        ix["report"] = report
    ix["updated_at"] = datetime.now(timezone.utc).isoformat()

    sets: dict = {"index_status": ix}
    derived = derive_doc_status(ix)
    status = doc.get("status")
    if failed:
        sets["status"] = STATUS_FAILED
    elif derived:
        if derived != status:
            sets["status"] = derived
            sets[f"{derived}_at"] = datetime.now(timezone.utc)
    elif status in (STATUS_SEARCHABLE, STATUS_COMPLETE):
        sets["status"] = STATUS_INDEXING  # a required store went missing
    await db.documents.update_one({"pdf_id": pdf_id}, {"$set": sets})
    job_sets = {"index_status": ix, "doc_status": sets.get("status", status),
                "updated_at": datetime.now(timezone.utc)}
    if sets.get("status") in (STATUS_SEARCHABLE, STATUS_COMPLETE):
        job_sets["status"] = sets["status"]
        job_sets["embedding_status"] = "done"
    await db.jobs.update_one({"job_id": pdf_id}, {"$set": job_sets})
    return ix


# ── individual stores ────────────────────────────────────────────────────────

async def _upsert_card_vector(card: dict) -> None:
    """Write ONE card's vector (embedding + Chroma write in a worker thread).

    Deliberately not dense_cards.build_from_cards: that function treats the list
    it is given as the complete set and deletes every other card's vector, so
    calling it with a single card would empty the collection.

    card_status is stored on the vector so check.py can tell a vector built from
    a metadata-only card (after a 429) from one built from the complete card.
    """
    from app.embeddings.embedding_generator import EmbeddingGenerator
    from app.retrieval.dense_cards import card_text, collection_name

    text = card_text(card)
    if not text:
        return
    judgment_id = card["judgment_id"]
    name = collection_name()

    def _write() -> None:
        vector = EmbeddingGenerator().generate_embeddings([text])
        _collection(name).upsert(
            ids=[judgment_id],
            embeddings=vector,
            documents=[text],
            metadatas=[{
                "file_id": judgment_id,
                "judgment_id": judgment_id,
                "case_display": str(card.get("case_display") or ""),
                "subject": str(card.get("subject") or ""),
                "card_status": str(card.get("card_status") or ""),
            }],
        )

    await asyncio.to_thread(_write)


async def _upsert_contextual(judgment_id: str, card: dict | None) -> int:
    """Re-embed one judgment's chunks, with headers, into the contextual collection."""
    from app.embeddings.embedding_generator import EmbeddingGenerator
    from app.indexing.fts_index import judgment_chunks

    name = _contextual_name()
    if name == getattr(settings, "CHROMA_COLLECTION", ""):
        # The live collection is maintained by the embedding pipeline itself.
        return 0

    chunks = await judgment_chunks(judgment_id, card, include_root=True)

    def _write() -> int:
        collection = _collection(name)
        collection.delete(where={"file_id": judgment_id})
        if not chunks:
            return 0
        texts = [c["text"] for c in chunks]
        collection.add(
            ids=[c["vector_id"] for c in chunks],
            embeddings=EmbeddingGenerator().generate_embeddings(texts),
            documents=texts,
            metadatas=[{
                "node_id": c["node_id"], "file_id": c["judgment_id"],
                "parent_node_id": str(c["parent_node_id"] or ""), "level": c["level"],
                "heading": str(c["heading"] or "")[:500], "section_type": c["section_type"],
                "chunk_index": c["chunk_index"], "chunk_count": c["chunk_count"],
            } for c in chunks],
        )
        return len(chunks)

    return await asyncio.to_thread(_write)


def _chunks_from_nodes(judgment_id: str, nodes: list[dict], card: dict | None) -> list[dict]:
    """fts_index.judgment_chunks without its Mongo read (include_root=False).

    Same rules, same output (asserted against judgment_chunks in the scratch
    acceptance run); split out so the tokenizer-heavy chunking can run in a
    worker thread. judgment_chunks does it inline on the event loop, which
    measured 1.3-2.5 s of loop stall per judgment during bulk ingest.
    """
    from app.embeddings.chunker import chunk_node
    from app.indexing.fts_index import ROOT_LEVEL, SECTION_LEVEL  # noqa: F401
    from app.retrieval.contracts import contextual_header

    root = next((n for n in nodes if n.get("type") == "parent"), None)
    case_title = ((root or {}).get("title") or "").strip()
    out: list[dict] = []
    for node in nodes:
        if node.get("type") == "parent":
            continue
        section_type = node.get("section_type") or ""
        title = node.get("title") or ""
        pieces = chunk_node(title, node.get("text") or "")
        header = contextual_header(card, section_type, case_title)
        for piece in pieces:
            body = piece["text"]
            out.append({
                "vector_id": f"{node['node_id']}::{piece['chunk_index']}",
                "judgment_id": judgment_id, "node_id": node["node_id"],
                "parent_node_id": node.get("parent_node_id") or "", "level": SECTION_LEVEL,
                "section_type": section_type, "heading": title,
                "chunk_index": piece["chunk_index"], "chunk_count": len(pieces),
                "header": header, "body": body, "text": f"{header}\n{body}" if header else body,
            })
    return out


async def fts_upsert(judgment_id: str) -> int:
    """fts_index.upsert_judgment with the CPU and SQLite work in a worker thread."""
    import time

    from app.indexing import fts_index

    cards = await fts_index.load_cards([judgment_id])
    card = cards.get(judgment_id)
    nodes = await db.database.nodes.find({"pdf_id": judgment_id}, {"_id": 0}).to_list(length=None)

    def _work() -> int:
        chunks = _chunks_from_nodes(judgment_id, nodes, card)
        conn = fts_index.connect()
        try:
            fts_index.ensure_schema(conn)
            with conn:
                fts_index._write_judgment(conn, judgment_id, chunks, card)
                fts_index._set_meta(conn, last_upsert=time.strftime("%Y-%m-%dT%H:%M:%S"))
        finally:
            conn.close()
        return len(chunks)

    written = await asyncio.to_thread(_work)
    logger.info(f"FTS upsert {judgment_id[:8]}: {written} chunks, card={'yes' if card else 'no'}")
    return written


async def warm_imports() -> None:
    """Import the heavy modules (torch, sentence-transformers, chromadb) in a
    thread, so the first judgment does not stall the event loop for seconds."""
    def _imp() -> None:
        import app.embeddings.embedding_generator  # noqa: F401
        import app.indexing.check  # noqa: F401
        import app.indexing.fts_index  # noqa: F401
        import app.ingestion.embedding_pipeline  # noqa: F401
        import app.retrieval.dense_cards  # noqa: F401
        import app.vectorstore.chroma_store  # noqa: F401

    await asyncio.to_thread(_imp)


async def prune_local_copies(judgment_id: str) -> dict:
    """Delete a finished judgment's local working files (backend/uploads/).

    At 2,677 judgments the PDFs alone are ~431 MB and their cached text another
    ~137 MB, all of it dead weight on a deployed server once the judgment is
    indexed and its original is safe in Google Drive. This removes that copy,
    but ONLY when both are true:

        * documents.status == "complete" (every store written, card included),
          so nothing is left to resume; and
        * the judgment has a Drive file id, so the PDF still exists somewhere.

    A judgment that is only "searchable", failed, or was ingested without
    --drive keeps its files: those are exactly the cases Retry/Resume needs.

    Nothing live reads these files for a complete judgment: downloads prefer
    Drive (the local path is only a fallback), exact_match reads uploads/*.txt
    only for judgments that have NO case card, and metadata_extractor returns
    None when the text is gone and rebuilds a card from MongoDB instead.

    Never raises; returns {"pruned": [names], "skipped": "reason"}.
    """
    try:
        doc = await db.documents.find_one(
            {"pdf_id": judgment_id}, {"status": 1, "drive": 1, "drive_file_id": 1})
        if not doc:
            return {"pruned": [], "skipped": "no document record"}
        if doc.get("status") != STATUS_COMPLETE:
            return {"pruned": [], "skipped": f"status is {doc.get('status')!r}, not complete"}
        drive_id = (doc.get("drive") or {}).get("file_id") or doc.get("drive_file_id")
        if not drive_id:
            return {"pruned": [], "skipped": "no Google Drive copy; keeping the only original"}

        def _unlink() -> list[str]:
            removed = []
            for suffix in LOCAL_COPY_SUFFIXES:
                path = UPLOADS_DIR / f"{judgment_id}{suffix}"
                try:
                    if path.exists():
                        path.unlink()
                        removed.append(path.name)
                except OSError as e:  # locked by another process: leave it
                    logger.warning(f"[{judgment_id}] could not remove {path.name}: {e}")
            return removed

        pruned = await asyncio.to_thread(_unlink)
        if pruned:
            logger.info(f"[{judgment_id}] local copies pruned ({len(pruned)} files); PDF remains on Drive")
        return {"pruned": pruned, "skipped": ""}
    except Exception as e:  # noqa: BLE001 - housekeeping must never fail a job
        logger.warning(f"[{judgment_id}] prune_local_copies failed: {e}")
        return {"pruned": [], "skipped": str(e)}


def _refresh_loader() -> None:
    """Make the server's in-memory node index see a write/delete immediately.

    index_loader is read-through anyway (see its docstring); this only closes
    the few-second rescan window, and only in a process that already loaded it.
    """
    mod = sys.modules.get("app.retrieval.index_loader")
    if mod is not None:
        try:
            mod.reload_index()
        except Exception as e:  # noqa: BLE001
            logger.warning(f"index_loader reload failed: {e}")


# ── the v2 stores for one judgment ───────────────────────────────────────────

async def index_judgment(judgment_id: str, build_card: bool = True) -> dict:
    """Bring the derived stores (card, FTS, card vector[, contextual]) up to date.

    Args:
        judgment_id: The pdf_id; its nodes must already be in MongoDB.
        build_card: Make the one LLM call for the card. When False, an existing
            card is reused and only the indexes are refreshed.

    Returns:
        ``{step: "ok" | "skipped" | "error: …"}`` for each store. The report is
        also persisted to documents.index_status.report together with the
        store flags it implies; this function never raises.
    """
    report: dict[str, str] = {}
    card: dict | None = None
    errors: list[str] = []

    # 1. Case card — the only step that costs an LLM call.
    try:
        if build_card:
            from app.ingestion.case_card import build_card as make_card, save_card

            card = await make_card(judgment_id)
            existing = await db.database.case_cards.find_one({"judgment_id": judgment_id})
            if card.get("card_status") == "complete" or not existing \
                    or existing.get("card_status") != "complete":
                await save_card(card)
            else:
                card = existing  # never replace a complete card with a degraded one
            report["case_card"] = card.get("card_status", "ok")
            if card.get("card_status") != "complete":
                errors.append(f"card: {card.get('card_error') or card.get('card_status')}")
        else:
            card = await db.database.case_cards.find_one({"judgment_id": judgment_id})
            report["case_card"] = f"reused ({card.get('card_status')})" if card else "skipped"
            if card and card.get("card_status") != "complete":
                errors.append(f"card: {card.get('card_error') or card.get('card_status')}")
    except Exception as e:
        logger.exception(f"[{judgment_id}] case card failed")
        report["case_card"] = f"error: {e}"
        errors.append(f"card: {e}")
        card = await db.database.case_cards.find_one({"judgment_id": judgment_id})

    # 2. BM25 index — reads the card itself from MongoDB.
    fts_ok = False
    try:
        written = await fts_upsert(judgment_id)
        fts_ok = written > 0
        report["lexical"] = f"ok ({written} chunks)" if fts_ok else "error: 0 chunks written"
        if not fts_ok:
            errors.append("fts: 0 chunks written")
    except Exception as e:
        logger.exception(f"[{judgment_id}] lexical index failed")
        report["lexical"] = f"error: {e}"
        errors.append(f"fts: {e}")

    # 3. Card vector.
    vec_ok = False
    try:
        if card:
            await _upsert_card_vector(card)
            report["card_vector"] = "ok"
            vec_ok = True
        else:
            report["card_vector"] = "skipped (no card)"
    except Exception as e:
        logger.exception(f"[{judgment_id}] card vector failed")
        report["card_vector"] = f"error: {e}"
        errors.append(f"card_vector: {e}")

    # 4. Contextual chunks — off unless CONTEXTUAL_INDEXING.
    if contextual_enabled():
        try:
            written = await _upsert_contextual(judgment_id, card)
            report["contextual"] = f"ok ({written} chunks)"
        except Exception as e:
            logger.exception(f"[{judgment_id}] contextual chunks failed")
            report["contextual"] = f"error: {e}"
    else:
        report["contextual"] = "skipped (CONTEXTUAL_INDEXING off)"

    card_complete = bool(card) and card.get("card_status") == "complete"
    try:
        await record_index_status(
            judgment_id, fts=fts_ok, card=card_complete, card_vector=vec_ok and bool(card),
            report=report, error="; ".join(errors) if errors else None, clear_error=not errors)
    except Exception as e:  # noqa: BLE001
        logger.error(f"[{judgment_id}] could not record index status: {e}")
    logger.info(f"[{judgment_id}] v2 indexes: {report}")
    return report


async def complete_judgment(judgment_id: str, build_card: bool = False,
                            force_dense: bool = False) -> dict:
    """Fill every missing store after the tree, recording each one.

    The single "finish this judgment" call shared by the admin upload, bulk
    ingest, retry and check --repair. Inspects what is actually present first,
    so a resumed judgment re-embeds only when its vectors are missing or
    incomplete. Raises StoreError("tree"|"dense"|"fts", …) when a store needed
    for search cannot be written; the error is recorded before raising.

    Returns {"stores": {...flags after}, "dense": "ok"|"present"|..., "report": {...}}.
    """
    from app.indexing.check import inspect_one

    state = await inspect_one(judgment_id)
    if not state["tree"]:
        await record_index_status(judgment_id, tree=False, error="tree: no tree in MongoDB")
        raise StoreError("tree", "no tree in MongoDB; the judgment must be parsed first")
    await record_index_status(judgment_id, tree=True)

    out: dict = {"dense": "present"}
    if force_dense or not state["dense"]:
        from app.ingestion.embedding_pipeline import run_embedding_pipeline

        try:
            res = await run_embedding_pipeline(pdf_id=judgment_id, force_regenerate=True)
        except Exception as e:
            logger.exception(f"[{judgment_id}] dense embedding failed")
            await record_index_status(judgment_id, dense=False, error=f"dense: {e}")
            raise StoreError("dense", str(e)) from e
        out["dense"] = f"ok ({res.get('chunks_embedded', 0)} chunks)"
        await asyncio.to_thread(_refresh_loader)
        state = await inspect_one(judgment_id)
        if not state["dense"]:
            await record_index_status(judgment_id, dense=False,
                                      error=f"dense: incomplete after embedding ({state['notes']})")
            raise StoreError("dense", f"incomplete after embedding: {state['notes']}")
    await record_index_status(judgment_id, dense=True)

    if build_card:
        # Never spend an LLM call on a judgment whose card is already current.
        from app.ingestion.case_card import _is_current

        existing = await db.database.case_cards.find_one(
            {"judgment_id": judgment_id}, {"card_version": 1, "metadata_version": 1, "card_status": 1})
        build_card = not _is_current(existing)
    out["report"] = await index_judgment(judgment_id, build_card=build_card)
    if not out["report"].get("lexical", "").startswith("ok"):
        await record_index_status(judgment_id, fts=False, error=f"fts: {out['report'].get('lexical')}")
        raise StoreError("fts", out["report"].get("lexical", "failed"))

    doc = await db.documents.find_one({"pdf_id": judgment_id}, {"index_status": 1})
    out["stores"] = {s: bool((doc or {}).get("index_status", {}).get(s)) for s in INDEX_STORES}
    return out


async def repair_judgment(judgment_id: str, with_cards: bool = False,
                          allow_delete: bool = True) -> dict:
    """check --repair for one judgment: fill what is missing, never an LLM call
    unless with_cards. Rebuilds a missing tree only from the cached parse
    (uploads/{id}_sections.json), which costs no LLM call either."""
    from app.indexing.check import inspect_one

    before = await inspect_one(judgment_id)
    actions: list[str] = []
    if not before["tree"]:
        parsed = load_cached_parse(judgment_id)
        if parsed is None:
            return {"judgment_id": judgment_id, "actions": ["skip: no tree and no cached parse; "
                                                            "re-ingest (retry / --retry-failed)"],
                    "ok": False}
        from app.ingestion.tree_builder import ensure_tree

        await ensure_tree(judgment_id, parsed, allow_delete=allow_delete)
        actions.append("tree from cached parse")

    needs_card = with_cards and not before["card"]
    stale_vector = before["card_present"] and not before["card_vector"]
    if not (before["dense"] and before["fts"]) or needs_card or stale_vector or not before["tree"]:
        try:
            res = await complete_judgment(judgment_id, build_card=needs_card)
            actions.append(f"dense {res['dense']}; fts/card_vector refreshed"
                           + ("; card built" if needs_card else ""))
        except StoreError as e:
            actions.append(f"failed: {e}")
    after = await inspect_one(judgment_id)
    # Record the truth, including for judgments that needed nothing (legacy
    # documents written before index_status existed).
    flags = {s: after[s] for s in INDEX_STORES}
    await record_index_status(judgment_id, **flags,
                              clear_error=all(after[s] for s in INDEX_REQUIRED_FOR_SEARCH))
    return {"judgment_id": judgment_id, "actions": actions or ["none needed"],
            "ok": all(after[s] for s in INDEX_REQUIRED_FOR_SEARCH), "after": flags}


def load_cached_parse(judgment_id: str) -> dict | None:
    """parse_sections' cached output, if both cache files exist (as the parser requires)."""
    import json

    uploads = Path(__file__).resolve().parents[2] / "uploads"
    sections, summary = uploads / f"{judgment_id}_sections.json", uploads / f"{judgment_id}_summary.md"
    if not (sections.exists() and summary.exists()):
        return None
    try:
        return json.loads(sections.read_text(encoding="utf-8", errors="ignore"))
    except Exception:  # noqa: BLE001
        return None


async def unindex_judgment(judgment_id: str) -> dict:
    """Remove one judgment from every v2 store. Safe to call more than once."""
    report: dict[str, str] = {}

    try:
        result = await db.database.case_cards.delete_many({"judgment_id": judgment_id})
        report["case_card"] = f"ok ({result.deleted_count} removed)"
    except Exception as e:
        report["case_card"] = f"error: {e}"

    try:
        from app.indexing.fts_index import remove_judgment

        await asyncio.to_thread(remove_judgment, judgment_id)
        report["lexical"] = "ok"
    except Exception as e:
        report["lexical"] = f"error: {e}"

    try:
        from app.retrieval.dense_cards import collection_name

        coll = _existing_collection(collection_name())
        if coll is not None:
            await asyncio.to_thread(coll.delete, ids=[judgment_id])
        report["card_vector"] = "ok"
    except Exception as e:
        report["card_vector"] = f"error: {e}"

    try:
        # Cleaned up even with CONTEXTUAL_INDEXING off: vectors written while it
        # was on must not outlive their judgment.
        name = _contextual_name()
        coll = _existing_collection(name) if name != getattr(settings, "CHROMA_COLLECTION", "") else None
        if coll is not None:
            await asyncio.to_thread(coll.delete, where={"file_id": judgment_id})
        report["contextual"] = "ok"
    except Exception as e:
        report["contextual"] = f"error: {e}"

    await asyncio.to_thread(_refresh_loader)
    logger.info(f"[{judgment_id}] removed from v2 indexes: {report}")
    return report


if __name__ == "__main__":
    # Offline self-check of the status derivation (no DB). The store round trip
    # is exercised by `python -m app.indexing.check --self-test` against a
    # scratch database.
    req = {s: True for s in INDEX_REQUIRED_FOR_SEARCH}
    assert derive_doc_status({}) is None
    assert derive_doc_status({"tree": True, "dense": True}) is None
    assert derive_doc_status(req) == STATUS_SEARCHABLE
    assert derive_doc_status({**req, "card": True}) == STATUS_SEARCHABLE
    assert derive_doc_status({**req, "card": True, "card_vector": True}) == STATUS_COMPLETE
    assert derive_doc_status({**req, "card": False, "card_vector": True}) == STATUS_SEARCHABLE
    assert StoreError("dense", "x").store == "dense"
    print("sync self-check OK")
