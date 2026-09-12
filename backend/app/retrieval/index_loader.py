"""
In-memory loader for the node -> vector index.

STEP 5 of retrieval: reads the index the ingestion pipeline writes and exposes
fast dictionary lookups over it. No ChromaDB, no MongoDB.

Index layout in this project
----------------------------
Ingestion writes one file per judgment into backend/app/connection, named
<judgment_id>_mappings.json, each holding a list of node entries. The path is
configurable through the JSON_INDEX_PATH setting (a directory of
*_mappings.json files, or a single JSON file); it defaults to that folder.

Each raw entry carries `node_id`, `file_id`, `level`, `heading`, `tree_id`,
`vector_id` and `embedding_text`. On load, every entry is enriched with the
names the retrieval pipeline uses, so callers do not have to know the
ingestion-side spelling:

    mongo_doc_id  <- node_id
    judgment_id   <- file_id
    node_type     <- "root" if level == 1 else "section"

`section_type` is not present in this index: the ingestion classifier stores it
in MongoDB (nodes.section_type) only.
"""

import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from loguru import logger

from app.config import settings

# Ingestion writes level 1 for root nodes and level 2 for sections.
ROOT_LEVEL = 1

DEFAULT_INDEX_DIR = Path(__file__).resolve().parents[1] / "connection"
INDEX_GLOB = "*_mappings.json"


def _resolve_index_path() -> Path:
    """Return the configured index location, falling back to app/connection."""
    configured = (settings.JSON_INDEX_PATH or "").strip()
    return Path(configured) if configured else DEFAULT_INDEX_DIR


def _index_files(path: Path) -> list[Path]:
    """List the JSON files making up the index at `path`."""
    if path.is_dir():
        return sorted(path.glob(INDEX_GLOB))
    return [path] if path.is_file() else []


def _normalise(entry: dict) -> dict:
    """Add the retrieval-side field names to a raw ingestion index entry."""
    enriched = dict(entry)
    enriched["mongo_doc_id"] = entry.get("node_id") or entry.get("nodeid") or ""
    enriched["judgment_id"] = entry.get("file_id") or entry.get("pdf_id") or ""
    enriched["node_type"] = "root" if entry.get("level") == ROOT_LEVEL else "section"
    return enriched


def _load_index() -> tuple[dict[str, dict], dict[str, list[dict]]]:
    """Read the index files and build the two lookup tables."""
    path = _resolve_index_path()
    files = _index_files(path)

    if not files:
        logger.warning(f"No index files found at {path}; lookups will return nothing.")
        return {}, {}

    by_mongo_id: dict[str, dict] = {}
    by_judgment: dict[str, list[dict]] = {}

    for file_path in files:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                raw_entries = json.load(f)
        except Exception as e:
            # One malformed file must not take down the whole index.
            logger.error(f"Skipping unreadable index file {file_path}: {e}")
            continue

        for raw in raw_entries:
            entry = _normalise(raw)
            mongo_doc_id = entry["mongo_doc_id"]
            if not mongo_doc_id:
                continue
            by_mongo_id[mongo_doc_id] = entry
            by_judgment.setdefault(entry["judgment_id"], []).append(entry)

    return by_mongo_id, by_judgment


_by_mongo_id, _by_judgment = _load_index()

logger.info(f"JSON index loaded: {len(_by_mongo_id)} entries")


def get_by_mongo_id(mongo_doc_id: str) -> dict | None:
    """Look up one index entry by its MongoDB node id.

    Args:
        mongo_doc_id: The node id, as returned by the stage 1 / stage 2 search.

    Returns:
        The index entry, or None if the id is not in the index.
    """
    entry = _by_mongo_id.get(mongo_doc_id)
    if entry is None:
        logger.warning(f"mongo_doc_id not found in index: {mongo_doc_id}")
    return entry


def get_nodes_for_judgment(judgment_id: str) -> list[dict]:
    """Return every index entry belonging to one judgment, or [] if unknown."""
    return _by_judgment.get(judgment_id, [])


def get_all_judgment_ids() -> list[str]:
    """Return every judgment id in the index, sorted."""
    return sorted(_by_judgment)


def reload_index() -> int:
    """Re-read the index from disk after a re-ingest. Returns the entry count."""
    global _by_mongo_id, _by_judgment
    _by_mongo_id, _by_judgment = _load_index()
    logger.info(f"JSON index reloaded: {len(_by_mongo_id)} entries")
    return len(_by_mongo_id)


if __name__ == "__main__":
    ids = get_all_judgment_ids()
    print(f"Index path: {_resolve_index_path()}")
    print(f"Total judgments in index: {len(ids)}")
    print(f"Total entries: {len(_by_mongo_id)}")

    nodes = get_nodes_for_judgment(ids[0])
    print(f"\nJudgment {ids[0]} has {len(nodes)} nodes:")
    for n in nodes:
        print(f"  {n['node_type']:<8} {n['heading'][:50]!r}")

    sample_id = nodes[0]["mongo_doc_id"]
    entry = get_by_mongo_id(sample_id)
    print(f"\nLookup by mongo_doc_id {sample_id}:")
    print(f"  judgment_id = {entry['judgment_id']}")
    print(f"  node_type   = {entry['node_type']}")
    print(f"  heading     = {entry['heading'][:50]!r}")

    assert entry is not None and entry["mongo_doc_id"] == sample_id
    assert get_by_mongo_id("no-such-id") is None
    assert get_nodes_for_judgment("no-such-judgment") == []
    print("\nOK: index lookups verified.")
