"""
The retrieval pipeline's single entry point.

STEP 10 of retrieval: runs every stage in order and returns the finished
response. This is the only module that imports from several pipeline steps at
once; it reimplements none of their logic.

    STAGE 1  preprocess          app.retrieval.query_preprocessor
    STAGE 2  embed               app.retrieval.query_embedder
    STAGE 3  judgment search     app.retrieval.chroma_client
    STAGE 4  section search      app.retrieval.node_searcher
    STAGE 5  expand context      app.retrieval.context_expander
    STAGE 6  assemble context    app.retrieval.context_assembler
    STAGE 7  generate answer     app.retrieval.llm_responder

Every query's artefacts are written to backend/app/query/<query_id>.json so
each stage can be inspected after the fact.
"""

import sys
import time
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from loguru import logger

from app.database import db
from app.retrieval.chroma_client import search_judgments
from app.retrieval.context_assembler import assemble_all_judgments, assemble_judgment_context
from app.retrieval.context_expander import expand_all_judgments
from app.retrieval.index_loader import get_nodes_for_judgment
from app.retrieval.llm_responder import generate_answer, generate_summary
from app.retrieval.mongo_fetcher import ID_FIELD, fetch_nodes
from app.retrieval.node_searcher import search_all_judgments
from app.retrieval.query_embedder import embed_query
from app.retrieval.query_preprocessor import preprocess
from app.retrieval.query_recorder import record_query

# Ingestion writes level 1 for root nodes; the index mirrors it as node_type.
ROOT_NODE_TYPE = "root"

MODE_ANSWER = "answer"
MODE_RETRIEVE_ONLY = "retrieve_only"


async def _documents_meta_for(judgment_ids: list[str]) -> dict[str, dict]:
    """Map judgment ids to their original PDF filenames and drive information.

    Node documents do not carry the filename; it lives on the `documents`
    collection, keyed by pdf_id.
    """
    if db.database is None or not judgment_ids:
        return {}

    cursor = db.database.documents.find(
        {"pdf_id": {"$in": judgment_ids}}, {"pdf_id": 1, "filename": 1, "drive": 1}
    )
    meta = {}
    async for d in cursor:
        drive_info = d.get("drive") if isinstance(d.get("drive"), dict) else {}
        meta[d["pdf_id"]] = {
            "filename": d.get("filename", ""),
            "has_drive_file": bool(drive_info.get("file_id")),
            "drive_file_id": drive_info.get("file_id"),
        }
    return meta


async def retrieve_and_answer(
    raw_query: str,
    top_k_judgments: int = 5,
    top_k_sections: int = 3,
    mode: str = MODE_ANSWER,
) -> dict:
    """Run the whole retrieval pipeline for one query.

    Args:
        raw_query: The researcher's question, as typed.
        top_k_judgments: How many judgments stage 3 should return.
        top_k_sections: How many sections stage 4 keeps per judgment.
        mode: ``"answer"`` to generate an answer for the best match,
            ``"retrieve_only"`` to stop after assembling context.

    Returns:
        The finished response: the query, its intent, the ranked judgments with
        their assembled context, and the answer for the top match.
    """
    timings: dict[str, float] = {}
    started = time.perf_counter()

    def mark(stage: str, since: float) -> float:
        now = time.perf_counter()
        timings[stage] = (now - since) * 1000
        return now

    # STAGE 1 — preprocess
    cleaned_query, intent = preprocess(raw_query)
    t = mark("preprocess", started)

    # STAGE 2 — embed
    query_vector = embed_query(cleaned_query)
    t = mark("embed", t)

    # STAGE 3 — judgment-level search
    parent_results = search_judgments(query_vector, top_k=top_k_judgments)
    judgment_ids = [r["judgment_id"] for r in parent_results]
    t = mark("judgment_search", t)

    # STAGE 4 — section-level search
    stage2_results = search_all_judgments(
        query_vector, judgment_ids, top_k_per_judgment=top_k_sections
    )
    t = mark("section_search", t)

    # STAGE 5 — expand context
    expanded = await expand_all_judgments(stage2_results)
    t = mark("expand", t)

    # STAGE 6 — assemble context
    assembled = assemble_all_judgments(expanded)
    t = mark("assemble", t)

    # STAGE 7 — generate an answer for the top match only.
    top_judgment_answer: str | None = None
    if mode == MODE_ANSWER and assembled and assembled[0].get("context"):
        top_judgment_answer = await generate_answer(cleaned_query, assembled[0]["context"])
    mark("generate", t)

    # Section labels come from the expanded documents; the Chroma metadata that
    # stage 4 returns does not carry section_type.
    sections_by_judgment = {
        e["judgment_id"]: [s["section_type"] for s in e["retrieved_sections"]]
        for e in expanded
    }
    scores_by_judgment = {r["judgment_id"]: r["score"] for r in parent_results}
    docs_meta = await _documents_meta_for(judgment_ids)

    judgments = [
        {
            "judgment_id": c["judgment_id"],
            "filename": docs_meta.get(c["judgment_id"], {}).get("filename", ""),
            "heading": c.get("heading", ""),
            "similarity_score": scores_by_judgment.get(c["judgment_id"], 0.0),
            "sections_retrieved": sections_by_judgment.get(c["judgment_id"], []),
            "context": c["context"],
            "token_count": c["token_count"],
            # Only the best match is answered, so the rest carry None.
            "llm_answer": top_judgment_answer if idx == 0 else None,
            "download_url": f"/api/admin/judgments/{c['judgment_id']}/download",
            "has_drive_file": docs_meta.get(c["judgment_id"], {}).get("has_drive_file", False),
        }
        for idx, c in enumerate(assembled)
    ]

    total_ms = (time.perf_counter() - started) * 1000
    logger.info(
        "Retrieval complete in {:.0f}ms | ".format(total_ms)
        + " | ".join(f"{stage} {ms:.0f}ms" for stage, ms in timings.items())
    )

    record_query(
        original_query=raw_query,
        cleaned_query=cleaned_query,
        intent=intent,
        embedding=query_vector,
        extra={
            "mode": mode,
            "stage1_judgments": parent_results,
            "stage2_sections": stage2_results,
            "expanded_context": expanded,
            "assembled_contexts": assembled,
            "answer": top_judgment_answer,
            "timings_ms": {k: round(v, 1) for k, v in timings.items()},
        },
    )

    return {
        "query": raw_query,
        "cleaned_query": cleaned_query,
        "intent": intent,
        "mode": mode,
        "judgments": judgments,
        "top_judgment_answer": top_judgment_answer,
    }


async def build_judgment_context(judgment_id: str) -> tuple[str, str]:
    """Assemble the full context of one judgment, independent of any query.

    Used by summarisation, which names the judgment outright rather than
    searching for it.

    Args:
        judgment_id: The judgment to assemble.

    Returns:
        A ``(filename, context)`` tuple; context is "" if the judgment is
        unknown.
    """
    entries = get_nodes_for_judgment(judgment_id)
    if not entries:
        logger.warning(f"No index entries for judgment_id={judgment_id}")
        return "", ""

    nodes = await fetch_nodes([e["mongo_doc_id"] for e in entries])
    if not nodes:
        return "", ""

    root_ids = {e["mongo_doc_id"] for e in entries if e.get("node_type") == ROOT_NODE_TYPE}
    root_node = next((n for n in nodes.values() if n[ID_FIELD] in root_ids), None)

    # Every section counts as expanded here: nothing was retrieved by score.
    expanded = {
        "judgment_id": judgment_id,
        "root_node": root_node,
        "retrieved_sections": [],
        "expanded_sections": [
            {
                "section_type": n.get("section_type") or "",
                "text": n.get("text") or "",
                "score": 0.0,
                "is_directly_retrieved": False,
                "mongo_doc_id": n[ID_FIELD],
                "heading": n.get("title") or "",
            }
            for n in nodes.values()
            if n[ID_FIELD] not in root_ids
        ],
    }

    filenames = await _filenames_for([judgment_id])
    return filenames.get(judgment_id, ""), assemble_judgment_context(expanded)


async def summarize_judgment(judgment_id: str) -> tuple[str, str]:
    """Summarise one judgment.

    Args:
        judgment_id: The judgment to summarise.

    Returns:
        A ``(filename, summary)`` tuple.
    """
    filename, context = await build_judgment_context(judgment_id)
    if not context:
        return filename, "Judgment not found."
    return filename, await generate_summary(context)


if __name__ == "__main__":
    import asyncio

    from app.database import connect_db

    async def main() -> None:
        await connect_db()

        result = await retrieve_and_answer(
            "bail granted despite murder charges weak evidence",
            top_k_judgments=3,
            top_k_sections=2,
            mode=MODE_ANSWER,
        )

        print(f"Query: {result['query']}")
        print(f"Intent: {result['intent']}")
        print(f"Judgments found: {len(result['judgments'])}")
        for j in result["judgments"]:
            print(f"  {j['filename']}  score={j['similarity_score']:.4f}  "
                  f"sections={j['sections_retrieved']}")

        if result["top_judgment_answer"]:
            print("\nLLM Answer:")
            print(result["top_judgment_answer"])

        assert result["judgments"], "no judgments returned"
        assert all(j["filename"] for j in result["judgments"]), "filename not resolved"
        assert all(j["sections_retrieved"] for j in result["judgments"]), "no section labels"
        assert result["judgments"][0]["llm_answer"] == result["top_judgment_answer"]
        assert all(j["llm_answer"] is None for j in result["judgments"][1:]), \
            "only the top judgment should be answered"

        retrieve_only = await retrieve_and_answer(
            "service tribunal appeal", top_k_judgments=2, mode=MODE_RETRIEVE_ONLY
        )
        assert retrieve_only["top_judgment_answer"] is None, "retrieve_only generated an answer"
        print("\nOK: orchestrator verified (answer + retrieve_only).")

    asyncio.run(main())
