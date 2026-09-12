"""
MongoDB access for the retrieval pipeline.

STEP 6 of retrieval: turns the ids coming out of the ChromaDB searches into
full node documents. No ChromaDB, no JSON file reads.

Notes on this project's actual MongoDB schema
---------------------------------------------
Nodes live in the `nodes` collection of the database named by DB_NAME, reached
through the app's existing motor client (app.database.db), which the ingestion
pipeline and API also share. There is no separate MONGO_COLLECTION setting.

Documents are keyed for retrieval by `node_id`, a UUID *string* — not by the
BSON `_id` ObjectId. `node_id` is exactly what ChromaDB stores as its vector id
and what the searches return as `mongo_doc_id`, so no ObjectId conversion is
involved anywhere in this module.

    node_id         str        this node's id (the retrieval key)
    pdf_id          str        the judgment this node belongs to
    type            str        "parent" for a root, "child" for a section
    section_type    str        ROOT | HEADER_CORAM | LEGAL_ISSUES |
                               ARGUMENTS | FACTS | ANALYSIS_RATIO | FINAL_ORDER
    title           str        the node's heading
    text            str        the node's body text
    parent_node_id  str|None   None on a root
    child_node_ids  list[str]  section ids, empty on a section
"""

import sys
from datetime import date, datetime
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from bson import ObjectId
from loguru import logger

from app.database import db

COLLECTION_NAME = "nodes"

# The retrieval key and the parent/child link fields, as ingestion writes them.
ID_FIELD = "node_id"
PARENT_FIELD = "parent_node_id"
CHILDREN_FIELD = "child_node_ids"

logger.info(f"MongoDB fetcher ready. Collection: {COLLECTION_NAME}")


def _collection():
    """Return the nodes collection, or None when the app has no DB connection."""
    if db.database is None:
        logger.error("MongoDB is not connected. Cannot fetch nodes.")
        return None
    return db.database[COLLECTION_NAME]


def _serialise(doc: dict) -> dict:
    """Make a raw Mongo document JSON-safe.

    Documents flow straight into API responses and into the query records
    written to app/query/, so BSON-only types (ObjectId) and datetimes have to
    become strings here rather than blowing up at json.dump time.
    """
    out: dict = {}
    for key, value in doc.items():
        if isinstance(value, ObjectId):
            out[key] = str(value)
        elif isinstance(value, (datetime, date)):
            out[key] = value.isoformat()
        else:
            out[key] = value
    return out


async def fetch_node(mongo_doc_id: str) -> dict | None:
    """Fetch one node document by its node_id.

    Args:
        mongo_doc_id: The node id returned by the ChromaDB searches.

    Returns:
        The node document, or None if it does not exist.
    """
    collection = _collection()
    if collection is None:
        return None

    doc = await collection.find_one({ID_FIELD: mongo_doc_id})
    if doc is None:
        logger.warning(f"Node not found in MongoDB: {mongo_doc_id}")
        return None
    return _serialise(doc)


async def fetch_nodes(mongo_doc_ids: list[str]) -> dict[str, dict]:
    """Batch fetch many node documents in a single query.

    Args:
        mongo_doc_ids: The node ids to fetch. Duplicates are fine.

    Returns:
        A dict mapping node_id to document. Ids with no matching document are
        simply absent from the result.
    """
    collection = _collection()
    if collection is None or not mongo_doc_ids:
        return {}

    unique_ids = list(dict.fromkeys(mongo_doc_ids))

    # One round trip for the whole batch, never a loop of fetch_node calls.
    cursor = collection.find({ID_FIELD: {"$in": unique_ids}})
    result = {doc[ID_FIELD]: _serialise(doc) async for doc in cursor}

    logger.info(f"Fetched {len(result)} / {len(unique_ids)} nodes")
    return result


async def fetch_parent(node_doc: dict) -> dict | None:
    """Fetch the parent of an already-fetched node, or None for a root."""
    parent_id = node_doc.get(PARENT_FIELD)
    if not parent_id:
        return None
    return await fetch_node(parent_id)


async def fetch_siblings(node_doc: dict) -> list[dict]:
    """Fetch the other sections sharing this node's parent.

    Args:
        node_doc: An already-fetched node document.

    Returns:
        The sibling documents, or [] for a root or a parentless node.
    """
    parent = await fetch_parent(node_doc)
    if parent is None:
        return []

    own_id = node_doc.get(ID_FIELD)
    sibling_ids = [cid for cid in (parent.get(CHILDREN_FIELD) or []) if cid != own_id]
    if not sibling_ids:
        return []

    fetched = await fetch_nodes(sibling_ids)
    # Preserve the parent's declared child order rather than Mongo's.
    return [fetched[cid] for cid in sibling_ids if cid in fetched]


if __name__ == "__main__":
    import asyncio

    from app.database import connect_db

    async def main() -> None:
        await connect_db()

        # Take a real section id from the DB rather than hardcoding one.
        collection = _collection()
        seed = await collection.find_one({"type": "child"})
        node = await fetch_node(seed[ID_FIELD])

        print(f"node_id:      {node[ID_FIELD]}")
        print(f"type:         {node['type']}")
        print(f"section_type: {node['section_type']}")
        print(f"text:         {node['text'][:80]!r}")

        parent = await fetch_parent(node)
        print(f"parent:       {parent['section_type'] if parent else 'None'} "
              f"({parent['title'][:40]!r})" if parent else "parent:       None")

        sibs = await fetch_siblings(node)
        print(f"siblings:     {[s['section_type'] for s in sibs]}")

        batch = await fetch_nodes([node[ID_FIELD], seed[ID_FIELD], "no-such-id"])
        print(f"batch:        {len(batch)} of 3 ids resolved")

        assert parent is not None and parent["type"] == "parent"
        assert node[ID_FIELD] not in [s[ID_FIELD] for s in sibs], "node is its own sibling"
        assert await fetch_node("no-such-id") is None
        assert await fetch_nodes([]) == {}
        print("OK: mongo fetcher verified.")

    asyncio.run(main())
