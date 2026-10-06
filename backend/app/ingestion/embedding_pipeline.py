"""
Embedding generation — MongoDB nodes to ChromaDB vectors.

Chunking: vectors, not nodes
----------------------------
A judgment is seven MongoDB nodes: one root plus six sections. That structure
is the product's central claim and the whole retrieval pipeline is built on it
(context_assembler keys text by section_type; context_expander expands by
fetching siblings). Splitting a long section into extra Mongo nodes would break
both — sibling expansion would explode, and the assembler's section map would
silently collapse five ANALYSIS_RATIO nodes into one.

So the MongoDB tree is left exactly as it is, and chunking happens only here,
at the vector layer:

    one node  ->  N vectors, id "{node_id}::{chunk_index}"

Every chunk carries the true `node_id` in its metadata, so retrieval keeps
resolving real nodes and nothing downstream needed to change to accommodate it.
Root nodes are short template summaries and are never chunked.

Idempotency
-----------
Re-running is safe. Existence is checked in one bulk query per document rather
than one round-trip per node, and `force_regenerate` clears that document's
vectors and mappings before rebuilding.

Off the event loop
------------------
The FastAPI server runs this inside its event loop (admin upload, retry).
Encoding a judgment is seconds of CPU and a Chroma write is a synchronous
SQLite transaction; run inline they froze every concurrent search for the
whole time. Both now run in worker threads (asyncio.to_thread); only the Mongo
calls stay on the loop.

Where the connection JSON goes
------------------------------
connection_dir() is settings.CONNECTION_DIR (or the CONNECTION_DIR environment
variable), else backend/app/connection. Scratch and test runs point it
elsewhere so they never drop files into the live index that
app.retrieval.index_loader reads.
"""

import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger

from app.config import settings
from app.database import db
from app.embeddings.chunker import chunk_node
from app.embeddings.embedding_generator import EmbeddingGenerator
from app.vectorstore.chroma_store import chroma_store

# Ingestion writes level 1 for the root node and level 2 for sections. The
# retrieval side filters on this, so the two must agree.
ROOT_LEVEL = 1
SECTION_LEVEL = 2

# How many chunks to embed per forward pass.
EMBED_BATCH_SIZE = 32

# Where the node -> vector index is written by default. Derived from this file
# rather than hardcoded, so the pipeline runs anywhere the repo is checked out.
CONNECTION_DIR = Path(__file__).resolve().parents[1] / "connection"


def connection_dir() -> Path:
    """The live connection-JSON directory, overridable for scratch runs.

    Settings has extra="ignore", so CONNECTION_DIR only reaches `settings` if
    the integrator adds the field; the environment variable works either way.
    """
    configured = (getattr(settings, "CONNECTION_DIR", "") or os.environ.get("CONNECTION_DIR", "")).strip()
    return Path(configured) if configured else CONNECTION_DIR


def mapping_file(pdf_id: str) -> Path:
    return connection_dir() / f"{pdf_id}_mappings.json"


def _dump_json(path: Path, entries: list) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2, ensure_ascii=False)


def _vector_id(node_id: str, chunk_index: int) -> str:
    """The ChromaDB id for one chunk of one node."""
    return f"{node_id}::{chunk_index}"


def _chunks_for(node: dict) -> list[dict]:
    """Split one node into its embedding-ready chunks.

    Root nodes hold a short generated summary and are never split; sections
    are chunked to fit the embedding model's window.
    """
    title = node.get("title") or ""
    text = node.get("text") or ""

    if node.get("type") == "parent":
        combined = f"{title}\n\n{text}" if text else title
        return [{"text": combined, "chunk_index": 0, "token_count": 0}] if combined else []

    return chunk_node(title, text)


async def _write_index_json(pdf_ids: set[str]) -> None:
    """Write the node -> vector index that app.retrieval.index_loader reads.

    One entry per NODE, not per chunk: the retrieval side resolves nodes, and
    `embedding_mappings` carries a unique index on node_id.

    The embedding vectors themselves are deliberately not written. Chroma is
    the vector store; duplicating 768 floats per chunk into JSON produced files
    that nothing ever read and that would have run to hundreds of megabytes at
    corpus scale.
    """
    out_dir = connection_dir()
    out_dir.mkdir(parents=True, exist_ok=True)

    for pdf_id in pdf_ids:
        entries = []
        async for mapping in db.database.embedding_mappings.find({"file_id": pdf_id}):
            mapping["_id"] = str(mapping["_id"])
            created = mapping.get("created_at")
            if isinstance(created, datetime):
                mapping["created_at"] = created.isoformat()

            # Field aliases kept for the existing readers of this file.
            mapping["nodeid"] = mapping.get("node_id", "")
            mapping["pdfid"] = mapping.get("file_id", "")
            mapping["treeid"] = mapping.get("tree_id", "")
            mapping["pdf_id"] = mapping["pdfid"]
            mapping["tree_id"] = mapping["treeid"]
            mapping["embedding_id"] = mapping.get("vector_id", "")
            mapping["embedding id"] = mapping["embedding_id"]

            entries.append(mapping)

        path = out_dir / f"{pdf_id}_mappings.json"
        try:
            await asyncio.to_thread(_dump_json, path, entries)
            logger.info(f"[{pdf_id}] Wrote index: {path.name} ({len(entries)} nodes)")
        except Exception as e:
            logger.error(f"[{pdf_id}] Failed to write index {path}: {e}")

        # Remove the vector dump left by earlier runs of this pipeline.
        stale = out_dir / f"{pdf_id}_vectors.json"
        if stale.exists():
            try:
                stale.unlink()
                logger.info(f"[{pdf_id}] Removed obsolete {stale.name}")
            except OSError as e:
                logger.warning(f"[{pdf_id}] Could not remove {stale.name}: {e}")


async def run_embedding_pipeline(pdf_id: str = None, force_regenerate: bool = False) -> dict:
    """Embed MongoDB nodes into ChromaDB, chunking sections to fit the model.

    Args:
        pdf_id: Restrict to one judgment. None processes every node.
        force_regenerate: Drop existing vectors and mappings first.

    Returns:
        Counts for the run: documents, nodes, chunks embedded.
    """
    if db.database is None:
        raise RuntimeError("Database connection not initialized")

    if force_regenerate:
        logger.info(f"Force regenerate: clearing existing vectors for pdf_id={pdf_id or 'ALL'}")
        if pdf_id:
            await db.database.embedding_mappings.delete_many({"file_id": pdf_id})
            await asyncio.to_thread(chroma_store.delete_by_file_id, pdf_id)
        else:
            await db.database.embedding_mappings.delete_many({})
            try:
                await asyncio.to_thread(chroma_store.reset_collection)
            except Exception as e:
                logger.warning(f"Could not reset the Chroma collection: {e}")

    query = {"pdf_id": pdf_id} if pdf_id else {}
    nodes = await db.database.nodes.find(query).to_list(length=None)
    if not nodes:
        logger.warning(f"No nodes found for pdf_id={pdf_id or 'ALL'}")
        return {
            "documents_processed": 0, "nodes_processed": 0, "chunks_embedded": 0,
            "vector_store": "chroma", "status": "success",
        }

    # One bulk existence check instead of one round-trip per node.
    already = set()
    if not force_regenerate:
        cursor = db.database.embedding_mappings.find(
            {"node_id": {"$in": [n["node_id"] for n in nodes]}}, {"node_id": 1}
        )
        already = {m["node_id"] async for m in cursor}
        if already:
            logger.info(f"Skipping {len(already)} nodes that are already embedded")

    pending = [n for n in nodes if n["node_id"] not in already]
    documents_seen = {n.get("pdf_id") or "" for n in nodes}

    generator = EmbeddingGenerator()
    chunks_embedded = 0

    # Flatten every node into its chunks up front, so batches are full even
    # when one node contributes twenty chunks and the next contributes one.
    def _flatten() -> list[tuple[dict, dict, int]]:
        out: list[tuple[dict, dict, int]] = []
        for node in pending:
            chunks = _chunks_for(node)
            for chunk in chunks:
                out.append((node, chunk, len(chunks)))
        return out

    # Tokenizer-based chunking is CPU too.
    flat = await asyncio.to_thread(_flatten)

    if not flat:
        logger.info("Nothing to embed; every node is already indexed.")
        await _write_index_json({d for d in documents_seen if d})
        return {
            "documents_processed": len(documents_seen), "nodes_processed": len(nodes),
            "chunks_embedded": 0, "vector_store": "chroma", "status": "success",
        }

    logger.info(
        f"Embedding {len(flat)} chunks from {len(pending)} nodes "
        f"({len(flat) / max(len(pending), 1):.1f} chunks/node)"
    )

    for start in range(0, len(flat), EMBED_BATCH_SIZE):
        batch = flat[start:start + EMBED_BATCH_SIZE]
        vectors = await asyncio.to_thread(generator.generate_embeddings,
                                          [c["text"] for _, c, _ in batch])

        ids, metadatas, documents = [], [], []
        for node, chunk, chunk_count in batch:
            node_id = node["node_id"]
            ids.append(_vector_id(node_id, chunk["chunk_index"]))
            metadatas.append({
                # The MongoDB node id, NOT the chunk id — retrieval resolves
                # real nodes and must not learn about chunking.
                "node_id": node_id,
                "file_id": node.get("pdf_id") or "",
                "parent_node_id": node.get("parent_node_id") or "",
                "level": ROOT_LEVEL if node.get("type") == "parent" else SECTION_LEVEL,
                "heading": node.get("title") or "",
                "section_type": node.get("section_type") or "",
                "chunk_index": chunk["chunk_index"],
                "chunk_count": chunk_count,
            })
            documents.append(chunk["text"])

        await asyncio.to_thread(
            chroma_store.add_node_embeddings,
            node_ids=ids, embeddings=vectors, metadatas=metadatas, documents=documents,
        )
        chunks_embedded += len(batch)

    # One mapping row per node, carrying the chunk fan-out.
    now = datetime.now(timezone.utc)
    chunk_counts: dict[str, int] = {}
    for node, chunk, chunk_count in flat:
        chunk_counts[node["node_id"]] = chunk_count

    for node in pending:
        node_id = node["node_id"]
        count = chunk_counts.get(node_id, 0)
        if not count:
            continue

        await db.database.embedding_mappings.update_one(
            {"node_id": node_id},
            {"$set": {
                "node_id": node_id,
                "file_id": node.get("pdf_id") or "",
                "tree_id": node.get("tree_id") or "",
                "parent_node_id": node.get("parent_node_id") or "",
                "level": ROOT_LEVEL if node.get("type") == "parent" else SECTION_LEVEL,
                "heading": node.get("title") or "",
                "section_type": node.get("section_type") or "",
                "vector_store": "chroma",
                "model": settings.EMBEDDING_MODEL,
                "vector_id": _vector_id(node_id, 0),
                "vector_ids": [_vector_id(node_id, i) for i in range(count)],
                "chunk_count": count,
                "created_at": now,
            }},
            upsert=True,
        )

    await _write_index_json({d for d in documents_seen if d})

    logger.info(
        f"Embedding complete: {len(documents_seen)} documents, "
        f"{len(pending)} nodes, {chunks_embedded} chunks"
    )
    return {
        "documents_processed": len(documents_seen),
        "nodes_processed": len(nodes),
        "chunks_embedded": chunks_embedded,
        # Retained for callers written against the previous return shape.
        "embeddings_created": chunks_embedded,
        "vector_store": "chroma",
        "status": "success",
    }
