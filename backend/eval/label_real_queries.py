"""
Propose labels for the real logged user queries, for a human to confirm.

Why
---
The queries in app/query/*.json are the only record of how lawyers actually
phrase a search — short, misspelt, half-remembered party names, "imran khan
bail case". Synthetic queries cannot imitate that, so these are the most
valuable rows in the evaluation set. But their labels cannot come from the
system: scoring the system against its own output measures nothing. So this
script only PROPOSES — it runs each query through the real pipeline and writes
a review sheet a human fills in — and every row stays status "proposed" until
eval/import_labels.py reads the human's decisions back.

Making the review fast (target: under an hour for ~80 queries)
--------------------------------------------------------------
* Distinct queries only, most-asked first, with the ask count.
* Queries already labelled in eval/queries.json are pre-filled LEGACY and need
  no work.
* Each query shows the system's top 3 with filenames and scores; when the
  system abstained it shows the best candidates BELOW the floor, marked so, so
  the human rarely has to look anything up.
* One line to fill per query — see the instructions at the top of the sheet.

Usage
-----
    python eval/label_real_queries.py                 # all logged queries
    python eval/label_real_queries.py --limit 5       # smoke test
    python eval/label_real_queries.py --force         # overwrite an edited sheet

It refuses to overwrite a sheet that already has decisions filled in, unless
--force: losing an hour of someone's labelling to a re-run is the worst outcome.
"""

import argparse
import asyncio
import json
import re
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from loguru import logger

import evallib as E

QUERY_LOG_DIR = E.BACKEND_DIR / "app" / "query"
SHEET_INDEX_LIMIT = 60  # above this many judgments, list them is useless; use ids


def load_logged_queries(log_dir: Path) -> Counter:
    """Distinct original_query -> times asked. Tolerates truncated log files."""
    counts: Counter = Counter()
    decoder = json.JSONDecoder()
    for path in sorted(log_dir.glob("*.json")):
        text = path.read_text(encoding="utf-8", errors="replace")
        try:
            query = json.loads(text)["original_query"]
        except Exception:
            # A few log files were cut off mid-write; the query is near the top.
            at = text.find('"original_query"')
            if at == -1:
                logger.warning(f"no original_query in {path.name}")
                continue
            query = decoder.raw_decode(text, text.index('"', at + len('"original_query"') + 1))[0]
        query = (query or "").strip()
        if query:
            counts[query] += 1
    return counts


async def below_floor(query: str, k: int = 3) -> list[dict]:
    """Best judgments when the system abstained, ignoring the relevance floor.

    Shown to the reviewer only — a hint for which judgment, if any, the user
    might have meant. Uses pipeline internals, so any failure just returns [].
    """
    try:
        from app.retrieval.chroma_client import rank_judgments, search_chunks
        from app.retrieval.query_embedder import embed_query
        from app.retrieval.query_preprocessor import preprocess
        from app.retrieval.reranker import RELEVANCE_KEY, rerank

        cleaned, _ = preprocess(query)
        candidates = rerank(cleaned, search_chunks(embed_query(cleaned)))
        ranked = rank_judgments(candidates, top_k=k, score_key=RELEVANCE_KEY, threshold=-1e9)
        return [{"judgment_id": r["judgment_id"], "score": float(r["score"])} for r in ranked]
    except Exception as e:  # pragma: no cover - diagnostic only
        logger.warning(f"below-floor lookup failed for {query!r}: {e}")
        return []


def short(pid: str) -> str:
    return pid[:8]


async def case_cards() -> dict[str, dict]:
    """judgment_id -> {subject, headnote, appellant, respondent} from case_cards, if present."""
    from app.database import db

    if not db.is_connected or "case_cards" not in await db.database.list_collection_names():
        return {}
    out = {}
    fields = {"judgment_id": 1, "subject": 1, "headnote": 1, "appellant": 1, "respondent": 1, "_id": 0}
    async for card in db.database.case_cards.find({}, fields):
        out[card.get("judgment_id")] = card
    return out


def render_sheet(entries: list[dict], corpus: dict[str, dict], cards: dict[str, dict] | None = None) -> str:
    cards = cards or {}
    def name(pid: str) -> str:
        meta = corpus.get(pid, {})
        return meta.get("filename") or meta.get("title") or "(not in corpus)"

    todo = sum(1 for e in entries if not e["legacy_match"])
    lines = [
        "# Real query review sheet",
        "",
        f"Generated {datetime.now().isoformat(timespec='seconds')} from {len(entries)} distinct "
        f"logged queries ({todo} need a decision; {len(entries) - todo} are pre-filled LEGACY).",
        "",
        "## How to fill it in",
        "",
        "For each query, edit the `DECISION:` line (and `TYPE:` if the guess is wrong).",
        "Leave DECISION empty to skip a query for now; it stays unlabelled.",
        "",
        "| DECISION | meaning |",
        "|---|---|",
        "| `1` | proposed result #1 is THE answer (grade 2) |",
        "| `2` / `3` | proposed result #2 / #3 is the answer |",
        "| `1 3:1` | #1 is the answer, #3 is a relevant alternate (grade 1) |",
        "| `3eff8217` | that judgment (pdf_id prefix, or a filename) is the answer — use when it is not in the top 3 |",
        "| `3eff8217 5a06e4ef:1` | answer plus an alternate, by id |",
        "| `NEG` | out of corpus: the correct behaviour is to abstain |",
        "| `SKIP` | not a real search (greetings, test input); drop it |",
        "| `LEGACY` | already labelled in eval/queries.json; nothing to do |",
        "",
        "Below-floor candidates (shown when the system abstained) are numbered too:",
        "`1` then means the first below-floor candidate.",
        "",
        "TYPE is one of: citation, entity, statute, issue, paraphrase, disposition, vague, unknown.",
        "",
        "When done: `python eval/import_labels.py` then `python eval/build_datasets.py`.",
        "",
    ]

    if len(corpus) <= SHEET_INDEX_LIMIT:
        lines += ["## Judgments in the corpus", "",
                  "| id | file | parties | subject | headnote |", "|---|---|---|---|---|"]
        for pid, meta in sorted(corpus.items(), key=lambda kv: kv[1].get("filename", "")):
            card = cards.get(pid, {})
            parties = " v. ".join(p for p in (card.get("appellant"), card.get("respondent")) if p) or meta.get("title", "")
            headnote = " ".join((card.get("headnote") or "").replace("|", "/").split())
            headnote = headnote[:220] + ("..." if len(headnote) > 220 else "")
            lines.append(f"| `{short(pid)}` | {meta.get('filename', '')} | {parties} | "
                         f"{card.get('subject', '')} | {headnote} |")
        lines.append("")

    lines += ["## Queries", ""]
    for entry in entries:
        lines.append(f"### {entry['id']}  (asked {entry['count']}x)")
        lines.append("")
        lines.append(f"QUERY: {entry['query']}")
        if entry["abstained"]:
            lines.append("System: ABSTAINED (nothing above the relevance floor).")
            if entry["below_floor"]:
                lines.append("Below-floor candidates:")
            shown = entry["below_floor"]
        else:
            lines.append("System top 3:")
            shown = entry["top"]
        for rank, hit in enumerate(shown, start=1):
            pid = hit["judgment_id"]
            lines.append(f"  {rank}. `{short(pid)}` {name(pid)}  score {hit['score']:.3f}")
        if entry["legacy_match"]:
            legacy_pid = entry["legacy_match"]
            lines.append(f"Already labelled (legacy): `{short(legacy_pid)}` {name(legacy_pid)}")
            lines.append("DECISION: LEGACY")
        else:
            lines.append("DECISION: ")
        lines.append(f"TYPE: {entry['proposed_type']}")
        lines.append("")
    return "\n".join(lines) + "\n"


def sheet_has_decisions(path: Path) -> bool:
    if not path.exists():
        return False
    return any(
        re.match(r"^DECISION:\s*(?!LEGACY\s*$)\S", line)
        for line in path.read_text(encoding="utf-8").splitlines()
    )


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--limit", type=int, help="Only the N most-asked queries (smoke test).")
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--force", action="store_true", help="Overwrite a sheet with decisions in it.")
    parser.add_argument("--sheet", type=Path, default=E.REAL_REVIEW_PATH)
    parser.add_argument("--out", type=Path, default=E.REAL_PROPOSED_PATH)
    parser.add_argument("--from-proposed", action="store_true",
                        help="Re-render the sheet from the proposals file; no pipeline runs.")
    args = parser.parse_args()

    logger.remove()
    logger.add(sys.stderr, level="WARNING")

    if sheet_has_decisions(args.sheet) and not args.force:
        print(f"{args.sheet} already has decisions filled in; refusing to overwrite (use --force).")
        return 2

    if args.from_proposed:
        entries = json.loads(args.out.read_text(encoding="utf-8"))["queries"]
        corpus = await E.corpus_judgments()
        args.sheet.write_text(render_sheet(entries, corpus, await case_cards()), encoding="utf-8")
        print(f"re-rendered {args.sheet} from {len(entries)} proposals")
        return 0

    counts = load_logged_queries(QUERY_LOG_DIR)
    ordered = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0].lower()))
    if args.limit:
        ordered = ordered[: args.limit]
    print(f"{sum(counts.values())} logged queries, {len(counts)} distinct; labelling {len(ordered)}")

    legacy = {E.normalise_query(r["query"]): next(iter(r["relevant"]))
              for r in E.load_legacy_file(E.LEGACY_PATH)}

    E.quiet_pipeline()
    corpus = await E.corpus_judgments()
    print(f"corpus: {len(corpus)} judgments")

    entries = []
    started = time.perf_counter()
    for index, (query, count) in enumerate(ordered, start=1):
        run = await E.run_query(query, args.top_k)
        top = [{"judgment_id": pid, "score": score, "filename": fn}
               for pid, score, fn in zip(run["ranked"], run["scores"], run["filenames"])]
        floor_hits = await below_floor(query) if run["no_results"] else []
        entry = {
            "id": E.stable_id("real", query),
            "query": query,
            "count": count,
            "abstained": run["no_results"],
            "top": top[:3],
            "top_all": top,
            "below_floor": floor_hits,
            "proposed_relevant": ({top[0]["judgment_id"]: 2} if top else {}),
            "proposed_type": E.LEGACY_TYPES.get(query) or E.guess_query_type(query),
            "legacy_match": legacy.get(E.normalise_query(query)),
            "status": "proposed",
            "origin": "real",
            "latency_ms": round(run["latency_ms"], 1),
        }
        entries.append(entry)
        mark = "ABSTAIN" if run["no_results"] else f"top {short(top[0]['judgment_id'])} {top[0]['score']:.2f}"
        print(f"  [{index:>2}/{len(ordered)}] {mark:<22} {query[:60]}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({
        "_README": "System PROPOSALS for the real logged queries. Never a label: "
                   "proposed_relevant is just the system's top-1. Confirm via the review sheet.",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "corpus_judgments": len(corpus),
        "queries": entries,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    args.sheet.write_text(render_sheet(entries, corpus, await case_cards()), encoding="utf-8")

    abstained = sum(1 for e in entries if e["abstained"])
    legacy_n = sum(1 for e in entries if e["legacy_match"])
    assert len(entries) == len(ordered)
    assert all(e["status"] == "proposed" for e in entries)
    print(f"\n{len(entries)} queries in {time.perf_counter() - started:.0f}s: "
          f"{abstained} abstained, {legacy_n} already legacy-labelled")
    print(f"wrote {args.sheet}")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
