"""
Rebuild the vector index from the MongoDB nodes that are already parsed.

Why this exists
---------------
Ingestion is two very different costs. Extraction and classification are slow
and expensive — OCR, then an LLM call per judgment with a ten-minute timeout —
and they produce the six-section tree in MongoDB. Embedding is fast, local, and
derives entirely from that tree.

Changing the embedding model or the chunking strategy invalidates every vector
but touches none of the parsing. So a re-index reads `nodes` straight out of
MongoDB and rebuilds the vectors: no PDFs re-read, no OCR, no LLM calls, no
re-upload. On the current corpus it is a matter of seconds; at a thousand
judgments it is minutes rather than the hours a full re-ingest would take.

Usage
-----
    python reindex.py --dry-run          # report what would happen
    python reindex.py                    # rebuild every judgment
    python reindex.py --pdf-id <id>      # rebuild one
    python reindex.py --resume           # skip judgments already in the index

The target collection comes from settings.CHROMA_COLLECTION. Pointing that at a
new name leaves the old vectors untouched on disk, which is what makes an
embedding-model change reversible.

Derived indexes (precision-v2, Agent C)
---------------------------------------
These read the same MongoDB nodes (and, when present, the `case_cards`
collection) and never touch the live collection, embedding_mappings or the
connection/*.json index:

    python reindex.py --fts                      # build backend/lexical.db (FTS5)
    python reindex.py --fts --pdf-id <id>        # upsert one judgment into it
    python reindex.py --cards                    # build card vectors (CARDS_COLLECTION)
    python reindex.py --contextual --collection legal_embeddings_v3_ctx
                                                 # chunks WITH contextual headers,
                                                 # Chroma only. Resumes by default
                                                 # (judgments already in the
                                                 # collection are skipped); --reset
                                                 # rebuilds it from scratch
    python reindex.py --fts --cards --dry-run    # report only

The contextual collection is an experiment live search never reads, and it
doubles embedding CPU, so --contextual refuses to run unless
settings.CONTEXTUAL_INDEXING is on (or --force-contextual is given). Uploads and
bulk ingest maintain it only under the same flag (app/indexing/sync.py).

New judgments no longer need this script: bulk ingest and the admin upload
write the live vectors and the keyword index themselves, and
`python -m app.indexing.check --repair` fills any gap. The live rebuild below
records index_status.dense for every judgment it re-embeds.

The three flags combine. --contextual refuses the live collection
(settings.CHROMA_COLLECTION, legal_embeddings_v2): switching live retrieval to
contextual vectors is an integration decision, made by pointing
CHROMA_COLLECTION at the new name, not by overwriting the old one.
"""

import argparse
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from loguru import logger

from app.config import settings
from app.database import connect_db, db
from app.ingestion.embedding_pipeline import run_embedding_pipeline
from app.vectorstore.chroma_store import chroma_store


async def _judgment_ids() -> list[str]:
    """Every pdf_id that has nodes in MongoDB, in a stable order."""
    return sorted({d for d in await db.database.nodes.distinct("pdf_id") if d})


async def _already_indexed() -> set[str]:
    """Judgment ids that already have vectors in the target collection."""
    try:
        got = chroma_store.collection.get(include=["metadatas"])
    except Exception as e:
        logger.warning(f"Could not read the collection: {e}")
        return set()

    return {
        meta.get("file_id", "")
        for meta in (got.get("metadatas") or [])
        if meta.get("file_id")
    }


# Never overwritten by --contextual in this wave, whatever settings say.
PROTECTED_COLLECTIONS = {"legal_embeddings_v2"}
CONTEXTUAL_BATCH = 32


async def _contextual_embed(name: str, targets: list[str], reset: bool, resume: bool,
                            dry_run: bool) -> int:
    """Embed every chunk WITH its contextual header into collection `name`.

    Chroma only: same ids ("{node_id}::{chunk_index}") and metadata layout as
    the live collection, so DenseChunksRetriever(collection_name=name) and,
    later, CHROMA_COLLECTION=name read it unchanged. Root nodes are included at
    level 1 as in the live index. Chunk boundaries are chunk_node's, identical
    to the live index; the header (~15-30 tokens) rides on top, so a chunk at
    the full 480-token budget may lose its last few tokens to the model's
    512-token window — counted and reported below.
    """
    from app.embeddings.chunker import count_tokens
    from app.embeddings.embedding_generator import EmbeddingGenerator
    from app.indexing.fts_index import judgment_chunks, load_cards

    client = chroma_store.client
    if reset and not dry_run:
        try:
            client.delete_collection(name)
            print(f"dropped collection {name!r}")
        except Exception:
            pass
    collection = None if dry_run else client.get_or_create_collection(
        name=name, metadata={"hnsw:space": "cosine"})

    if resume and collection is not None and not reset:
        got = collection.get(include=["metadatas"])
        done = {m.get("file_id") for m in got.get("metadatas") or []}
        skipped = [t for t in targets if t in done]
        targets = [t for t in targets if t not in done]
        if skipped:
            print(f"resuming, skipping {len(skipped)} judgments already in {name!r}")

    cards = await load_cards()
    print(f"\ncontextual -> {name!r}: {len(targets)} judgments, "
          f"{sum(1 for t in targets if t in cards)} with case cards")
    if dry_run:
        for judgment_id in targets[:3]:
            chunks = await judgment_chunks(judgment_id, cards.get(judgment_id), include_root=True)
            example = chunks[min(1, len(chunks) - 1)]["header"] if chunks else "(none)"
            print(f"  {judgment_id[:8]}  {len(chunks)} chunks, e.g. {example!r}")
        print("  --dry-run: nothing written")
        return 0

    generator = EmbeddingGenerator()
    started = time.perf_counter()
    total = over_window = 0
    for index, judgment_id in enumerate(targets, start=1):
        chunks = await judgment_chunks(judgment_id, cards.get(judgment_id), include_root=True)
        collection.delete(where={"file_id": judgment_id})
        for start in range(0, len(chunks), CONTEXTUAL_BATCH):
            batch = chunks[start:start + CONTEXTUAL_BATCH]
            texts = [c["text"] for c in batch]
            over_window += sum(1 for t in texts if count_tokens(t) > 510)
            collection.add(
                ids=[c["vector_id"] for c in batch],
                embeddings=generator.generate_embeddings(texts),
                documents=texts,
                metadatas=[{
                    "node_id": c["node_id"], "file_id": c["judgment_id"],
                    "parent_node_id": str(c["parent_node_id"] or ""), "level": c["level"],
                    "heading": str(c["heading"] or "")[:500], "section_type": c["section_type"],
                    "chunk_index": c["chunk_index"], "chunk_count": c["chunk_count"],
                } for c in batch],
            )
        total += len(chunks)
        print(f"  [{index}/{len(targets)}] {judgment_id[:8]}  {len(chunks)} chunks")

    elapsed = time.perf_counter() - started
    print(f"contextual: {total} chunks in {elapsed:.1f}s; {collection.count()} vectors in "
          f"{name!r}; {over_window} chunks exceed 510 tokens with header (tail truncated)")
    return 0


async def _derived(args) -> int:
    """--fts / --cards / --contextual. Never touches the live collection."""
    from app.indexing import fts_index
    from app.retrieval import dense_cards

    targets = [args.pdf_id] if args.pdf_id else await fts_index.judgment_ids()
    status = 0

    if args.fts:
        path = fts_index.db_path()
        print(f"\nFTS index: {path}  (tokenizer {fts_index.TOKENIZER!r})")
        print(f"  now: {fts_index.counts(path)}")
        if args.dry_run:
            action = f"upsert {args.pdf_id}" if args.pdf_id else "rebuild"
            print(f"  --dry-run: would {action} ({len(targets)} judgments)")
        elif args.pdf_id:
            written = await fts_index.upsert_judgment(args.pdf_id, path)
            from app.indexing.sync import record_index_status
            await record_index_status(args.pdf_id, fts=written > 0)
            print(f"  upserted {args.pdf_id}: {written} chunks -> {fts_index.counts(path)}")
        else:
            print(f"  rebuilt: {await fts_index.rebuild(path, progress=True)}")

    if args.cards:
        cards = await fts_index.load_cards()
        print(f"\ncard vectors: {dense_cards.collection_name()!r}, {len(cards)} cards in MongoDB")
        if args.dry_run:
            print("  --dry-run: nothing written")
        else:
            print(f"  built: {await dense_cards.build(reset=args.reset)}")

    if args.contextual:
        if not args.collection:
            print("--contextual needs --collection NAME (e.g. legal_embeddings_v3_ctx)")
            return 2
        if not getattr(settings, "CONTEXTUAL_INDEXING", False) and not args.force_contextual:
            print("--contextual skipped: CONTEXTUAL_INDEXING is off (live search never reads the "
                  "contextual collection). Pass --force-contextual to build it anyway.")
        else:
            # Resume unless a rebuild was asked for: re-embedding every judgment
            # on every run was the main cost of this step.
            status |= await _contextual_embed(args.collection, targets, args.reset,
                                              args.resume or not args.reset, args.dry_run)
    return status


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pdf-id", help="Rebuild only this judgment.")
    parser.add_argument("--resume", action="store_true",
                        help="Skip judgments that already have vectors.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Report what would be done and exit.")
    parser.add_argument("--reset", action="store_true",
                        help="Drop the whole collection first. Implies a full rebuild. "
                             "With --contextual/--cards it drops THAT collection only.")
    parser.add_argument("--fts", action="store_true",
                        help="Build (or with --pdf-id, upsert into) the SQLite FTS5 lexical index.")
    parser.add_argument("--cards", action="store_true",
                        help="Build one vector per case card into settings.CARDS_COLLECTION.")
    parser.add_argument("--contextual", action="store_true",
                        help="Embed chunks with contextual headers into --collection (Chroma only).")
    parser.add_argument("--collection",
                        help="Target collection for --contextual. The live collection is refused.")
    parser.add_argument("--force-contextual", action="store_true",
                        help="Build --contextual even though CONTEXTUAL_INDEXING is off.")
    args = parser.parse_args()

    derived = args.fts or args.cards or args.contextual
    if args.collection and not args.contextual:
        print("--collection only applies to --contextual.")
        return 2
    if args.contextual and args.collection and (
            args.collection in PROTECTED_COLLECTIONS
            or args.collection == settings.CHROMA_COLLECTION):
        print(f"Refusing --collection {args.collection!r}: it is the live collection that "
              f"retrieval reads. Build into a new name (e.g. legal_embeddings_v3_ctx) and "
              f"switch CHROMA_COLLECTION to it once it has been measured.")
        return 2

    await connect_db()
    if db.database is None:
        logger.error("No database connection; is MongoDB running?")
        return 1

    if derived:
        return await _derived(args)

    print(f"model      : {settings.EMBEDDING_MODEL} ({settings.EMBEDDING_DIM}d)")
    print(f"collection : {settings.CHROMA_COLLECTION}")
    print(f"chunking   : {settings.CHUNK_MAX_TOKENS} tokens, "
          f"{settings.CHUNK_OVERLAP_SENTENCES}-sentence overlap")

    targets = [args.pdf_id] if args.pdf_id else await _judgment_ids()
    if not targets:
        print("\nNothing to index: no nodes found in MongoDB.")
        return 0

    existing = chroma_store.collection.count()
    print(f"\njudgments in MongoDB : {len(targets)}")
    print(f"vectors in collection: {existing}")

    if args.resume and not args.reset:
        indexed = await _already_indexed()
        skipped = [t for t in targets if t in indexed]
        targets = [t for t in targets if t not in indexed]
        if skipped:
            print(f"resuming, skipping    : {len(skipped)} already indexed")

    # An empty target list must count nothing, not fall through to every node.
    node_count = (
        await db.database.nodes.count_documents({"pdf_id": {"$in": targets}}) if targets else 0
    )
    print(f"to index             : {len(targets)} judgments, {node_count} nodes")

    if args.dry_run:
        print("\n--dry-run: nothing written.")
        for judgment_id in targets[:10]:
            nodes = await db.database.nodes.count_documents({"pdf_id": judgment_id})
            print(f"  {judgment_id}  {nodes} nodes")
        if len(targets) > 10:
            print(f"  ... and {len(targets) - 10} more")
        return 0

    if not targets:
        print("\nNothing to do.")
        return 0

    if args.reset:
        print(f"\nResetting collection {settings.CHROMA_COLLECTION!r}...")
        chroma_store.reset_collection()
        await db.database.embedding_mappings.delete_many({})

    started = time.perf_counter()
    total_chunks = 0
    failed: list[tuple[str, str]] = []

    for index, judgment_id in enumerate(targets, start=1):
        try:
            result = await run_embedding_pipeline(
                pdf_id=judgment_id,
                # --reset already cleared everything; otherwise replace this
                # judgment's vectors so a re-run cannot leave stale chunks from
                # a previous chunking strategy behind.
                force_regenerate=not args.reset,
            )
            chunks = result.get("chunks_embedded", 0)
            total_chunks += chunks
            from app.indexing.sync import record_index_status
            await record_index_status(judgment_id, dense=True)
            print(f"  [{index}/{len(targets)}] {judgment_id[:8]}  "
                  f"{result.get('nodes_processed', 0)} nodes -> {chunks} chunks")
        except Exception as e:
            logger.exception(f"Failed to index {judgment_id}")
            failed.append((judgment_id, str(e)))
            print(f"  [{index}/{len(targets)}] {judgment_id[:8]}  FAILED: {e}")

    elapsed = time.perf_counter() - started
    print(f"\nindexed  : {len(targets) - len(failed)}/{len(targets)} judgments")
    print(f"chunks   : {total_chunks}")
    print(f"vectors  : {chroma_store.collection.count()} now in {settings.CHROMA_COLLECTION!r}")
    print(f"elapsed  : {elapsed:.1f}s ({elapsed / max(len(targets), 1):.1f}s per judgment)")

    if failed:
        print(f"\n{len(failed)} failed:")
        for judgment_id, error in failed:
            print(f"  {judgment_id}  {error}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
