"""
Context expansion for the retrieval pipeline.

STEP 7 of retrieval: the stage 2 search returns a handful of matching sections
per judgment, which is rarely enough to reason from — a strong hit in
ANALYSIS_RATIO means little without the FACTS it rests on. This module fetches
those sections from MongoDB and rounds them out with the rest of the judgment,
so each result carries its full structure.

Everything here builds on modules already written:
    app.retrieval.index_loader   locating a judgment's root node
    app.retrieval.mongo_fetcher  fetching node documents

Where section_type comes from
-----------------------------
ChromaDB does not store section_type, so the stage 2 results arrive with it
blank. MongoDB does store it, so the labels (HEADER_CORAM, LEGAL_ISSUES,
ARGUMENTS, FACTS, ANALYSIS_RATIO, FINAL_ORDER) are recovered here from the
fetched documents rather than trusted from the search results.
"""

import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from loguru import logger

from app.retrieval.index_loader import get_nodes_for_judgment
from app.retrieval.mongo_fetcher import (
    ID_FIELD,
    PARENT_FIELD,
    fetch_node,
    fetch_nodes,
    fetch_siblings,
)


def _as_section(node: dict, score: float, is_directly_retrieved: bool) -> dict:
    """Shape one node document into a context section entry."""
    return {
        # Recovered from MongoDB — the Chroma metadata does not carry it.
        "section_type": node.get("section_type") or "",
        "text": node.get("text") or "",
        "score": float(score),
        "is_directly_retrieved": is_directly_retrieved,
        # Carried through so later steps can cite and de-duplicate.
        "mongo_doc_id": node.get(ID_FIELD, ""),
        "heading": node.get("title") or "",
    }


async def _fetch_root_node(judgment_id: str, fallback_parent: dict | None) -> dict | None:
    """Locate and fetch a judgment's root node via the JSON index."""
    root_entries = [
        e for e in get_nodes_for_judgment(judgment_id)
        if e.get("node_type") == "root"
    ]
    if root_entries:
        return await fetch_node(root_entries[0]["mongo_doc_id"])

    # The index can lag behind a re-ingest; the parent walked during sibling
    # expansion is the same node, so use it rather than returning nothing.
    if fallback_parent is not None:
        logger.warning(
            f"No root entry in the JSON index for judgment_id={judgment_id}; "
            "falling back to the parent reached from the retrieved sections."
        )
        return fallback_parent

    logger.warning(f"No root node could be resolved for judgment_id={judgment_id}")
    return None


async def expand_judgment_context(
    judgment_id: str,
    retrieved_sections: list[dict],
) -> dict:
    """Assemble the full context for one judgment around its retrieved sections.

    Args:
        judgment_id: The judgment being expanded.
        retrieved_sections: That judgment's stage 2 hits, each carrying at
            least ``mongo_doc_id`` and ``score``.

    Returns:
        A dict with ``judgment_id``, ``root_node``, ``retrieved_sections`` and
        ``expanded_sections``. The expanded list holds the judgment's other
        sections, which carry a score of 0.0 because nothing matched them.
    """
    scores = {s["mongo_doc_id"]: s.get("score", 0.0) for s in retrieved_sections}
    fetched = await fetch_nodes(list(scores))

    # Pull in the rest of each judgment's sections. Every section of a judgment
    # shares one parent, so expanding per distinct parent collapses what would
    # otherwise be the same lookup repeated for each hit.
    siblings: dict[str, dict] = {}
    parents_seen: set[str] = set()

    for node in fetched.values():
        parent_id = node.get(PARENT_FIELD)
        if not parent_id or parent_id in parents_seen:
            continue
        parents_seen.add(parent_id)

        for sibling in await fetch_siblings(node):
            sibling_id = sibling[ID_FIELD]
            if sibling_id not in fetched:
                siblings[sibling_id] = sibling

    fallback_parent = await fetch_node(next(iter(parents_seen))) if parents_seen else None
    root_node = await _fetch_root_node(judgment_id, fallback_parent)

    directly_retrieved = [
        _as_section(fetched[doc_id], scores[doc_id], True)
        for doc_id in scores
        if doc_id in fetched
    ]
    directly_retrieved.sort(key=lambda s: s["score"], reverse=True)

    # Nothing matched these, so they carry no score; they keep document order.
    expanded = [_as_section(node, 0.0, False) for node in siblings.values()]

    return {
        "judgment_id": judgment_id,
        "root_node": root_node,
        "retrieved_sections": directly_retrieved,
        "expanded_sections": expanded,
    }


async def expand_all_judgments(stage2_results: dict[str, list[dict]]) -> list[dict]:
    """Expand every judgment returned by the stage 2 search.

    Args:
        stage2_results: The dict from
            :func:`app.retrieval.node_searcher.search_all_judgments`.

    Returns:
        One expanded context dict per judgment, in stage 2 order.
    """
    results = [
        await expand_judgment_context(judgment_id, sections)
        for judgment_id, sections in stage2_results.items()
    ]

    logger.info(f"Context expanded for {len(results)} judgments")
    return results


if __name__ == "__main__":
    import asyncio

    from app.database import connect_db
    from app.retrieval.chroma_client import search_judgments
    from app.retrieval.node_searcher import search_all_judgments
    from app.retrieval.query_embedder import embed_query

    async def main() -> None:
        await connect_db()

        # Drive it with real stage 1 + stage 2 output rather than fixtures.
        vec = embed_query("bail granted despite murder charges")
        judgments = search_judgments(vec, top_k=2)
        stage2 = search_all_judgments(
            vec, [j["judgment_id"] for j in judgments], top_k_per_judgment=2
        )

        expanded = await expand_all_judgments(stage2)

        for ctx in expanded:
            root = ctx["root_node"]
            root_label = f"{root['section_type']} ({root['title'][:40]!r})" if root else "None"
            retrieved = [(s["section_type"], round(s["score"], 4)) for s in ctx["retrieved_sections"]]
            print(f"\njudgment_id: {ctx['judgment_id']}")
            print(f"  root_node: {root_label}")
            print(f"  retrieved: {retrieved}")
            print(f"  expanded:  {[s['section_type'] for s in ctx['expanded_sections']]}")

        one = expanded[0]
        assert one["root_node"] is not None, "root node missing"
        assert one["retrieved_sections"], "no retrieved sections"
        assert all(s["is_directly_retrieved"] for s in one["retrieved_sections"])
        assert all(not s["is_directly_retrieved"] for s in one["expanded_sections"])
        assert all(s["score"] == 0.0 for s in one["expanded_sections"])
        assert all(s["section_type"] for s in one["retrieved_sections"]), "section_type not recovered"

        retrieved_ids = {s["mongo_doc_id"] for s in one["retrieved_sections"]}
        expanded_ids = {s["mongo_doc_id"] for s in one["expanded_sections"]}
        assert not (retrieved_ids & expanded_ids), "a section appears in both lists"
        print("\nOK: context expansion verified.")

    asyncio.run(main())
