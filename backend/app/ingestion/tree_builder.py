"""
Build the six-section judgment tree in MongoDB (nodes + document_trees).

The tree is the FIRST of the five stores a judgment needs before search can
find it (tree -> dense -> fts -> card -> card vector; see
app.retrieval.contracts.INDEX_STORES). This module used to flip
documents.status to "complete" as soon as the tree was saved, which made a
judgment with no vectors and no keyword rows look finished: bulk ingest
stopped there, and a re-run called it a duplicate. Now the tree step only
records `index_status.tree` and moves the document to "indexing"; the status
becomes "searchable"/"complete" in app.indexing.sync once the later stores are
written.

`ensure_tree` is the idempotent entry point every caller uses (admin upload,
bulk, retry, check --repair). build_and_save_tree inserts nodes, then the tree,
then updates the document, so a crash between those steps leaves either a tree
(finish the bookkeeping, never build a second one) or nodes without a tree
(orphans of the dead attempt: remove them and rebuild).
"""
import uuid
from datetime import datetime, timezone

from loguru import logger

from app.database import db

DEFAULT_LABELS = {
    "HEADER_CORAM": "Header / Coram",
    "FACTS": "Facts",
    "ARGUMENTS": "Arguments",
    "LEGAL_ISSUES": "Legal Issues",
    "ANALYSIS_RATIO": "Analysis / Ratio",
    "FINAL_ORDER": "Final Decision"
}

# documents.status after the tree is written and before dense + FTS are.
STATUS_INDEXING = "indexing"


def build_tree_documents(pdf_id: str, parsed_data: dict) -> tuple[dict, list[dict], dict]:
    """Pure construction: (parent_node, child_nodes, tree_document). No I/O."""
    tree_id = str(uuid.uuid4())
    parent_node_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    context_heading = parsed_data.get("context_heading") or "Unknown Case"
    context_summary = parsed_data.get("context_summary") or ""

    sections_by_type = {}
    for sec in parsed_data.get("sections", []):
        st = sec.get("section_type")
        if st:
            sections_by_type[st] = sec

    # Every standard section is in the tree, plus any extra the parser found.
    ordered_section_types = list(DEFAULT_LABELS.keys())
    for st in sections_by_type:
        if st not in ordered_section_types:
            ordered_section_types.append(st)

    child_nodes, tree_children_meta, child_node_ids = [], [], []
    for section_type in ordered_section_types:
        sec = sections_by_type.get(section_type)
        text = (sec.get("text", "") or "") if sec else ""
        heading_found = sec.get("heading_found") if sec else None
        child_node_id = str(uuid.uuid4())
        child_node_ids.append(child_node_id)
        title = heading_found or DEFAULT_LABELS.get(section_type, section_type)
        child_nodes.append({
            "node_id": child_node_id, "pdf_id": pdf_id, "tree_id": tree_id, "type": "child",
            "section_type": section_type, "title": title, "text": text,
            "parent_node_id": parent_node_id, "child_node_ids": [], "created_at": now,
        })
        tree_children_meta.append({"node_id": child_node_id, "section_type": section_type,
                                   "title": title, "type": "child"})

    parent_node = {
        "node_id": parent_node_id, "pdf_id": pdf_id, "tree_id": tree_id, "type": "parent",
        "section_type": "ROOT", "title": context_heading, "text": context_summary,
        "parent_node_id": None, "child_node_ids": child_node_ids, "created_at": now,
    }
    tree_document = {
        "tree_id": tree_id, "pdf_id": pdf_id, "root_node_id": parent_node_id,
        "structure": {"node_id": parent_node_id, "title": context_heading, "type": "parent",
                      "children": tree_children_meta},
        "created_at": now,
    }
    return parent_node, child_nodes, tree_document


async def _mark_tree_done(pdf_id: str, tree_id: str, root_node_id: str, total_nodes: int) -> None:
    """Document bookkeeping + index_status.tree; never sets "complete"."""
    from app.indexing.sync import record_index_status

    await db.documents.update_one(
        {"pdf_id": pdf_id, "status": {"$nin": ["searchable", "complete"]}},
        {"$set": {"status": STATUS_INDEXING}},
    )
    await db.documents.update_one(
        {"pdf_id": pdf_id},
        {"$set": {"tree_id": tree_id, "root_node_id": root_node_id, "total_nodes": total_nodes}},
    )
    await record_index_status(pdf_id, tree=True)


async def build_and_save_tree(pdf_id: str, parsed_data: dict) -> str:
    """Insert a NEW tree for `pdf_id`. Prefer ensure_tree, which is idempotent."""
    if db.database is None or db.nodes is None or db.documents is None:
        logger.error(f"[{pdf_id}] Database not connected - cannot save tree")
        raise RuntimeError("Database connection not initialized")

    parent_node, child_nodes, tree_document = build_tree_documents(pdf_id, parsed_data)
    logger.info(f"[{pdf_id}] Inserting root node and {len(child_nodes)} child nodes into MongoDB")
    await db.nodes.insert_one(parent_node)
    if child_nodes:
        await db.nodes.insert_many(child_nodes)
    await db.database.document_trees.insert_one(tree_document)

    total_nodes = len(child_nodes) + 1
    await _mark_tree_done(pdf_id, tree_document["tree_id"], tree_document["root_node_id"], total_nodes)
    logger.info(f"[{pdf_id}] Tree build completed. Total nodes: {total_nodes}")
    return tree_document["tree_id"]


async def ensure_tree(pdf_id: str, parsed_data: dict | None, allow_delete: bool = True) -> str | None:
    """Make sure `pdf_id` has exactly one tree. Safe to call any number of times.

    Returns the tree_id, or None when no tree exists and `parsed_data` is None
    (the caller has nothing to build from).

    allow_delete=False refuses to remove orphan nodes left by a crashed build
    (the bulk CLI passes False on the production DB without --allow-main-db).
    """
    if db.database is None:
        raise RuntimeError("Database connection not initialized")
    existing = await db.database.document_trees.find_one({"pdf_id": pdf_id})
    if existing:
        total = await db.nodes.count_documents({"pdf_id": pdf_id, "tree_id": existing["tree_id"]})
        if total:
            await _mark_tree_done(pdf_id, existing["tree_id"], existing["root_node_id"], total)
            logger.info(f"[{pdf_id}] Tree already built by an earlier run; record finalised")
            return existing["tree_id"]
        # A tree document with no nodes is useless: drop it and rebuild.
        await db.database.document_trees.delete_many({"pdf_id": pdf_id})

    if parsed_data is None:
        return None
    orphans = await db.nodes.count_documents({"pdf_id": pdf_id})
    if orphans:
        if not allow_delete:
            raise RuntimeError(f"{orphans} orphan nodes for {pdf_id} need removal, but deletes "
                               f"are not allowed on this database")
        await db.nodes.delete_many({"pdf_id": pdf_id})
        logger.warning(f"[{pdf_id}] Removed {orphans} orphan nodes from an interrupted tree build")
    return await build_and_save_tree(pdf_id, parsed_data)


if __name__ == "__main__":
    # Offline self-check of the pure construction (no DB).
    parent, children, tree = build_tree_documents(
        "p1", {"context_heading": "C.A. 1/2020", "sections": [
            {"section_type": "FACTS", "text": "facts", "heading_found": "FACTS:"},
            {"section_type": "EXTRA", "text": "x"}]})
    assert parent["type"] == "parent" and parent["title"] == "C.A. 1/2020"
    assert [c["section_type"] for c in children] == list(DEFAULT_LABELS) + ["EXTRA"]
    assert children[1]["title"] == "FACTS:" and children[1]["text"] == "facts"
    assert all(c["tree_id"] == tree["tree_id"] == parent["tree_id"] for c in children)
    assert parent["child_node_ids"] == [c["node_id"] for c in children]
    assert tree["root_node_id"] == parent["node_id"]
    print("tree_builder self-check OK")
