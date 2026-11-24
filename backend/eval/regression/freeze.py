"""Record exactly what search returns for a fixed set of queries, to prove a
change leaves them alone. Run it twice before a change (the query analyser
uses an LLM, so a few results vary run to run) and once after; compare.py
reports what changed beyond that natural variation.

    venv/Scripts/python.exe eval/regression/freeze.py eval/regression/before_a.json
"""
import asyncio, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.local_models import prefer_local_models; prefer_local_models()
from app.database import connect_db
from app.retrieval import pipeline_v2 as p

# The owner's verified queries (as typed, typos included) and the probes run with them.
VERIFIED = [
    "pre arrest bail in 377", "nab case on naib bail ordinance", "NAB case on bail nab ordinance",
    "naib bail ordinance", "C.P.L.A. 4599 2017", "NAB casses", "NAB casey on bael nab ordinence",
    "NAB bail ordinance", "pre-arrest bail section 377 PPC", "pre arrest bail 337 PPC", "bail u/s 302/34 PPC",
    "bail in 489-F cheque dishonour case", "anticipatry bail in narcotiks case", "u/s 324 ppc post arrest bail",
    "khula suit and return of dower", "transfer of civil servant challenged before service tribunal",
    "acquittal in murdr case due to delay in FIR", "recovery of dower in family court",
    "promotion of civil servant service tribunal", "bail in narcotics case under section 9(c) CNSA",
]


def queries() -> list[str]:
    out = list(VERIFIED)
    for f in ("dev.jsonl", "test.jsonl"):     # the standard (non-description) evaluation queries
        path = Path(__file__).resolve().parents[1] / "datasets" / f
        out += [json.loads(l)["query"] for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    return list(dict.fromkeys(out))


async def main(out_path: str) -> None:
    await connect_db(wait_s=20)
    # Load both models first, in this thread, and refuse to record if they do
    # not work: a record of a broken search (models failed to load, so every
    # query "returns nothing") would make any comparison meaningless.
    from app.retrieval.readiness import check_now
    problems = check_now()
    if problems:
        sys.exit(f"Search is not ready, nothing recorded: {problems}")
    record = {}
    for q in queries():
        res = await p.retrieve_v2(q, 10)
        if p.last_debug.get("rerank_failed"):
            sys.exit(f"Search failed on {q!r} (models or indexes unavailable); nothing recorded.")
        record[q] = {
            "shown": [[r["judgment_id"], r["confidence"]] for r in res.get("parent_results", [])],
            "no_results": bool(res.get("no_results")), "notice": res.get("notice", ""),
            "message": res.get("message", ""), "is_narrative": bool((res.get("analysis") or {}).get("is_narrative")),
            "judge_used": bool(res.get("judge_used")),
        }
        print(f"{len(record):3} {'N' if record[q]['is_narrative'] else ' '} {q[:80]}", flush=True)
    Path(out_path).write_text(json.dumps(record, indent=1), encoding="utf-8")


asyncio.run(main(sys.argv[1]))
