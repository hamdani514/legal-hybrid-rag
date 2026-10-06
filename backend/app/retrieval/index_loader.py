"""
In-memory loader for the node -> vector index.

STEP 5 of retrieval: resolves a judgment (or a single node id) to the node
entries the answer pipeline needs. Backed by MongoDB.

Where the index lives
---------------------
The authoritative index is the `embedding_mappings` collection, written by
app.ingestion.embedding_pipeline: one row per node, carrying `node_id`,
`file_id`, `level`, `heading`, `tree_id`, `vector_id` and `chunk_count`.

Until this module was changed, the same rows were ALSO mirrored to
backend/app/connection/<judgment_id>_mappings.json and read from there. That
duplicated the collection on disk for no benefit: the files could drift from
the database, every store check had to verify both, and a deployed server
carried ~20 MB of JSON it already had in MongoDB. The files are gone; the
collection is the single source of truth. `settings.JSON_INDEX_PATH` is
ignored and kept only so old .env files do not fail to load.

Each row is enriched on read with the names the retrieval pipeline uses, so
callers do not have to know the ingestion-side spelling:

    mongo_doc_id  <- node_id
    judgment_id   <- file_id
    node_type     <- "root" if level == 1 else "section"

Fresh, but not a query per call
-------------------------------
The public functions are synchronous (they are called from inside the
orchestrator's own coroutines), so they use a small synchronous pymongo client
rather than the app's motor client, and cache what they read for CACHE_TTL_S
seconds. A judgment uploaded or deleted by another process therefore shows up
within that window, and reload_index() — already called by the admin path
after embedding and after delete — drops the cache immediately.

If MongoDB is unreachable, every lookup returns empty and logs instead of
raising: a degraded answer is better than a 500 on the whole search.
"""

import sys
import threading
import time
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from loguru import logger

from app.config import settings

# Ingestion writes level 1 for root nodes and level 2 for sections.
ROOT_LEVEL = 1

MAPPINGS_COLLECTION = "embedding_mappings"
CACHE_TTL_S = 2.0
# Everything the retrieval side reads, minus Mongo's _id (an ObjectId, which
# would break any caller that serialises an entry).
PROJECTION = {"_id": 0}

_client = None
_client_lock = threading.Lock()


def _collection():
    """The embedding_mappings collection on a lazily created sync client."""
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                from pymongo import MongoClient

                _client = MongoClient(settings.MONGO_URL, serverSelectionTimeoutMS=5000,
                                      connectTimeoutMS=5000)
    return _client[settings.DB_NAME][MAPPINGS_COLLECTION]


def _normalise(row: dict) -> dict:
    """Add the retrieval-side field names to a raw embedding_mappings row."""
    enriched = dict(row)
    enriched["mongo_doc_id"] = row.get("node_id") or row.get("nodeid") or ""
    enriched["judgment_id"] = row.get("file_id") or row.get("pdf_id") or ""
    enriched["node_type"] = "root" if row.get("level") == ROOT_LEVEL else "section"
    return enriched


class _Index:
    """Short-lived cache over embedding_mappings."""

    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.by_judgment: dict[str, tuple[float, list[dict]]] = {}
        self.by_mongo_id: dict[str, tuple[float, dict | None]] = {}
        self.ids: tuple[float, list[str]] | None = None

    def clear(self) -> None:
        with self.lock:
            self.by_judgment.clear()
            self.by_mongo_id.clear()
            self.ids = None

    @staticmethod
    def _fresh(stamp: float) -> bool:
        return (time.monotonic() - stamp) < CACHE_TTL_S

    def judgment(self, judgment_id: str) -> list[dict]:
        with self.lock:
            hit = self.by_judgment.get(judgment_id)
            if hit and self._fresh(hit[0]):
                return hit[1]
        try:
            rows = list(_collection().find({"file_id": judgment_id}, PROJECTION))
        except Exception as e:  # noqa: BLE001 - never fail a search on the index
            logger.warning(f"index lookup failed for judgment {judgment_id}: {e}")
            return []
        entries = [e for e in (_normalise(r) for r in rows) if e["mongo_doc_id"]]
        with self.lock:
            self.by_judgment[judgment_id] = (time.monotonic(), entries)
            for e in entries:
                self.by_mongo_id[e["mongo_doc_id"]] = (time.monotonic(), e)
        return entries

    def node(self, mongo_doc_id: str) -> dict | None:
        with self.lock:
            hit = self.by_mongo_id.get(mongo_doc_id)
            if hit and self._fresh(hit[0]):
                return hit[1]
        try:
            row = _collection().find_one({"node_id": mongo_doc_id}, PROJECTION)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"index lookup failed for node {mongo_doc_id}: {e}")
            return None
        entry = _normalise(row) if row else None
        with self.lock:
            self.by_mongo_id[mongo_doc_id] = (time.monotonic(), entry)
        return entry

    def judgment_ids(self) -> list[str]:
        with self.lock:
            if self.ids and self._fresh(self.ids[0]):
                return self.ids[1]
        try:
            found = sorted(j for j in _collection().distinct("file_id") if j)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"index judgment listing failed: {e}")
            return []
        with self.lock:
            self.ids = (time.monotonic(), found)
        return found


_index = _Index()


def get_by_mongo_id(mongo_doc_id: str) -> dict | None:
    """Look up one index entry by its MongoDB node id.

    Args:
        mongo_doc_id: The node id, as returned by the stage 1 / stage 2 search.

    Returns:
        The index entry, or None if the id is not in the index.
    """
    entry = _index.node(mongo_doc_id)
    if entry is None:
        logger.warning(f"mongo_doc_id not found in index: {mongo_doc_id}")
    return entry


def get_nodes_for_judgment(judgment_id: str) -> list[dict]:
    """Return every index entry belonging to one judgment, or [] if unknown."""
    return list(_index.judgment(judgment_id))


def get_all_judgment_ids() -> list[str]:
    """Return every judgment id in the index, sorted."""
    return list(_index.judgment_ids())


def reload_index() -> int:
    """Drop the cache so the next lookup re-reads MongoDB. Returns the entry count."""
    _index.clear()
    try:
        total = _collection().estimated_document_count()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"index reload could not count mappings: {e}")
        return 0
    logger.info(f"Index cache cleared: {total} mapping rows in MongoDB")
    return total


def __getattr__(name):
    # Backwards compatibility for code that read the old module globals.
    if name == "_by_mongo_id":
        return {k: v[1] for k, v in _index.by_mongo_id.items() if v[1]}
    if name == "_by_judgment":
        return {k: v[1] for k, v in _index.by_judgment.items()}
    raise AttributeError(name)


if __name__ == "__main__":
    SCRATCH = "legal_rag_scratch_index"
    assert settings.DB_NAME == SCRATCH, (
        f"refusing to run against {settings.DB_NAME!r}; use DB_NAME={SCRATCH}")

    coll = _collection()
    coll.delete_many({})
    try:
        coll.insert_many([
            {"node_id": "n1", "file_id": "J1", "level": 1, "heading": "root"},
            {"node_id": "n2", "file_id": "J1", "level": 2, "heading": "FACTS"},
            {"node_id": "m1", "file_id": "J2", "level": 1, "heading": "root"},
        ])
        reload_index()

        nodes = get_nodes_for_judgment("J1")
        assert sorted(e["mongo_doc_id"] for e in nodes) == ["n1", "n2"], nodes
        assert [e["node_type"] for e in nodes if e["mongo_doc_id"] == "n1"] == ["root"]
        assert [e["node_type"] for e in nodes if e["mongo_doc_id"] == "n2"] == ["section"]
        assert all(e["judgment_id"] == "J1" for e in nodes)
        assert "_id" not in nodes[0], "ObjectId must not leak into entries"

        assert get_by_mongo_id("n1")["judgment_id"] == "J1"
        assert get_by_mongo_id("no-such-id") is None
        assert get_nodes_for_judgment("no-such-judgment") == []
        assert get_all_judgment_ids() == ["J1", "J2"]

        # A write by "another process" is visible after the cache is dropped.
        coll.delete_many({"file_id": "J1"})
        reload_index()
        assert get_nodes_for_judgment("J1") == []
        assert get_by_mongo_id("n1") is None
        assert get_all_judgment_ids() == ["J2"]
        print("OK: MongoDB-backed index lookups verified.")
    finally:
        coll.delete_many({})
        _client.drop_database(SCRATCH)
