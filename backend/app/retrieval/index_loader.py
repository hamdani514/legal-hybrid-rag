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

Read-through, not load-once
---------------------------
This module used to read the index once at import and expose reload_index(),
which nothing ever called: a judgment uploaded after server start had no
entries here (its summary came back empty until a restart), and a deleted one
stayed in memory. Calling reload_index() from the admin endpoints would fix
the server's own uploads but not the bulk CLI, which runs in another process
and writes the same files. So the cache now follows the files on disk:

* get_nodes_for_judgment(j) stats j's file on every call (one stat, ~10 us)
  and reloads it when its mtime/size changed, drops it when it is gone, and
  loads it when it is new. Per-judgment lookups are therefore never stale.
* lookups that span the whole index (get_by_mongo_id on a miss,
  get_all_judgment_ids) rescan the directory at most every RESCAN_INTERVAL_S
  seconds; os.scandir returns the stat data with the listing on Windows, so a
  rescan of 3,000 files costs a few milliseconds and re-reads only the files
  that changed.

reload_index() is kept (a forced full rescan) and is still called by the
admin path after embedding and delete, so the server's own writes show up
even inside the rescan interval.
"""

import json
import os
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

DEFAULT_INDEX_DIR = Path(__file__).resolve().parents[1] / "connection"
INDEX_GLOB = "*_mappings.json"
INDEX_SUFFIX = "_mappings.json"
RESCAN_INTERVAL_S = 2.0


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


def _read_file(file_path: Path) -> list[dict]:
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            raw_entries = json.load(f)
    except Exception as e:
        # One malformed (or half-written) file must not take down the index.
        logger.error(f"Skipping unreadable index file {file_path}: {e}")
        return []
    out = []
    for raw in raw_entries if isinstance(raw_entries, list) else []:
        entry = _normalise(raw)
        if entry["mongo_doc_id"]:
            out.append(entry)
    return out


class _Index:
    """Per-file cache of the connection JSONs, kept in step with the disk."""

    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.files: dict[str, tuple[int, int, list[dict]]] = {}  # path -> (mtime_ns, size, entries)
        self.by_mongo_id: dict[str, dict] = {}
        self.by_judgment: dict[str, list[dict]] = {}
        self.last_scan = 0.0

    # ── maintenance ─────────────────────────────────────────────────────
    def _drop_file(self, key: str) -> None:
        old = self.files.pop(key, None)
        if not old:
            return
        for e in old[2]:
            if self.by_mongo_id.get(e["mongo_doc_id"]) is e:
                del self.by_mongo_id[e["mongo_doc_id"]]
        for jid in {e["judgment_id"] for e in old[2]}:
            kept = [e for e in self.by_judgment.get(jid, []) if all(e is not o for o in old[2])]
            if kept:
                self.by_judgment[jid] = kept
            else:
                self.by_judgment.pop(jid, None)

    def _load_file(self, key: str, path: Path, mtime_ns: int, size: int) -> None:
        self._drop_file(key)
        entries = _read_file(path)
        self.files[key] = (mtime_ns, size, entries)
        for e in entries:
            self.by_mongo_id[e["mongo_doc_id"]] = e
            self.by_judgment.setdefault(e["judgment_id"], []).append(e)

    def rescan(self, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now - self.last_scan < RESCAN_INTERVAL_S:
            return
        with self.lock:
            root = _resolve_index_path()
            seen: dict[str, tuple[Path, int, int]] = {}
            if root.is_dir():
                with os.scandir(root) as it:
                    for de in it:
                        if de.name.endswith(INDEX_SUFFIX) and de.is_file():
                            st = de.stat()
                            seen[de.path] = (Path(de.path), st.st_mtime_ns, st.st_size)
            elif root.is_file():
                st = root.stat()
                seen[str(root)] = (root, st.st_mtime_ns, st.st_size)
            for key in [k for k in self.files if k not in seen]:
                self._drop_file(key)
            for key, (path, mtime_ns, size) in seen.items():
                cur = self.files.get(key)
                if cur is None or cur[0] != mtime_ns or cur[1] != size:
                    self._load_file(key, path, mtime_ns, size)
            self.last_scan = time.monotonic()

    def refresh_judgment(self, judgment_id: str) -> None:
        """Bring one judgment's file in step with the disk (directory mode only)."""
        root = _resolve_index_path()
        if not root.is_dir():
            self.rescan()
            return
        path = root / f"{judgment_id}{INDEX_SUFFIX}"
        key = str(path)
        with self.lock:
            try:
                st = path.stat()
            except OSError:
                self._drop_file(key)
                # An entry for this judgment could also come from a differently
                # named file; leave those to the periodic rescan.
                return
            cur = self.files.get(key)
            if cur is None or cur[0] != st.st_mtime_ns or cur[1] != st.st_size:
                self._load_file(key, path, st.st_mtime_ns, st.st_size)


_index = _Index()
_index.rescan(force=True)
logger.info(f"JSON index loaded: {len(_index.by_mongo_id)} entries")


def get_by_mongo_id(mongo_doc_id: str) -> dict | None:
    """Look up one index entry by its MongoDB node id.

    Args:
        mongo_doc_id: The node id, as returned by the stage 1 / stage 2 search.

    Returns:
        The index entry, or None if the id is not in the index.
    """
    entry = _index.by_mongo_id.get(mongo_doc_id)
    if entry is None:
        _index.rescan()
        entry = _index.by_mongo_id.get(mongo_doc_id)
    elif entry.get("judgment_id"):
        _index.refresh_judgment(entry["judgment_id"])  # deleted since?
        entry = _index.by_mongo_id.get(mongo_doc_id)
    if entry is None:
        logger.warning(f"mongo_doc_id not found in index: {mongo_doc_id}")
    return entry


def get_nodes_for_judgment(judgment_id: str) -> list[dict]:
    """Return every index entry belonging to one judgment, or [] if unknown."""
    _index.refresh_judgment(judgment_id)
    with _index.lock:
        return list(_index.by_judgment.get(judgment_id, []))


def get_all_judgment_ids() -> list[str]:
    """Return every judgment id in the index, sorted."""
    _index.rescan()
    with _index.lock:
        return sorted(_index.by_judgment)


def reload_index() -> int:
    """Force a full rescan of the index on disk. Returns the entry count."""
    _index.rescan(force=True)
    logger.info(f"JSON index reloaded: {len(_index.by_mongo_id)} entries")
    return len(_index.by_mongo_id)


def __getattr__(name):
    # Backwards compatibility for code that read the old module globals.
    if name == "_by_mongo_id":
        return _index.by_mongo_id
    if name == "_by_judgment":
        return _index.by_judgment
    raise AttributeError(name)


if __name__ == "__main__":
    import shutil
    import tempfile

    ids = get_all_judgment_ids()
    print(f"Index path: {_resolve_index_path()}")
    print(f"Total judgments in index: {len(ids)}  entries: {len(_index.by_mongo_id)}")
    if ids:
        nodes = get_nodes_for_judgment(ids[0])
        sample_id = nodes[0]["mongo_doc_id"]
        entry = get_by_mongo_id(sample_id)
        assert entry is not None and entry["mongo_doc_id"] == sample_id
    assert get_by_mongo_id("no-such-id") is None
    assert get_nodes_for_judgment("no-such-judgment") == []

    # Read-through on a temporary directory: a file written by "another
    # process" appears, a rewrite is picked up, a delete disappears — all
    # without reload_index().
    tmp = Path(tempfile.mkdtemp())
    real = settings.JSON_INDEX_PATH
    try:
        settings.JSON_INDEX_PATH = str(tmp)
        reload_index()
        assert get_all_judgment_ids() == []
        f = tmp / f"J1{INDEX_SUFFIX}"
        f.write_text(json.dumps([{"node_id": "n1", "file_id": "J1", "level": 1, "heading": "root"}]))
        assert [e["mongo_doc_id"] for e in get_nodes_for_judgment("J1")] == ["n1"]
        assert get_by_mongo_id("n1")["judgment_id"] == "J1"
        time.sleep(0.01)
        f.write_text(json.dumps([{"node_id": "n1", "file_id": "J1", "level": 1},
                                 {"node_id": "n2", "file_id": "J1", "level": 2}]))
        assert sorted(e["mongo_doc_id"] for e in get_nodes_for_judgment("J1")) == ["n1", "n2"]
        f.unlink()
        assert get_nodes_for_judgment("J1") == []
        assert get_by_mongo_id("n2") is None
        (tmp / f"J2{INDEX_SUFFIX}").write_text(json.dumps([{"node_id": "m1", "file_id": "J2", "level": 1}]))
        _index.last_scan = 0.0  # as if the rescan interval had elapsed
        assert get_all_judgment_ids() == ["J2"]
        assert get_by_mongo_id("n1") is None
    finally:
        settings.JSON_INDEX_PATH = real
        reload_index()
        shutil.rmtree(tmp, ignore_errors=True)
    print("\nOK: index lookups and read-through verified.")
