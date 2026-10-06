"""
Manifest and final report for a bulk ingestion run.

The report exists so that a 3,000-file run can be audited without reading
logs: every file ends in exactly one outcome, every failure carries its
reason, and every parse the quality validator flagged (quality_passed False)
is listed as "needs review" with its issues. Throughput is split by queue
because digital and scanned files are limited by different things (the LLM
quota vs. OCR CPU), and the projection for the full corpus depends on both.

Throughput definition: docs completed in a queue / that queue's makespan
(processing start -> its last completion). Both queues run concurrently, so
the two rates are not additive over the same wall clock; the overall rate is
total completed / total processing wall time.
"""
from __future__ import annotations

import json
import statistics
from pathlib import Path


def stage_stats(values: list[float]) -> dict:
    vals = sorted(v for v in values if v is not None)
    if not vals:
        return {"n": 0}

    def pct(p: float) -> float:
        k = min(len(vals) - 1, max(0, round(p * (len(vals) - 1))))
        return round(vals[k], 3)

    return {"n": len(vals), "total_s": round(sum(vals), 2),
            "mean_s": round(statistics.fmean(vals), 3), "p50_s": pct(0.5),
            "p95_s": pct(0.95), "max_s": round(vals[-1], 3)}


def build_report(*, run_id: str, db_name: str, options: dict, triage_summary: dict,
                 results: list[dict], processing_wall_s: float, llm_stats: dict,
                 interrupted: bool) -> dict:
    outcomes: dict[str, int] = {}
    for r in results:
        outcomes[r["outcome"]] = outcomes.get(r["outcome"], 0) + 1

    done = [r for r in results if r["outcome"] == "done"]
    by_queue = {}
    for q in ("digital", "scanned"):
        qd = [r for r in done if r["queue"] == q]
        makespan = max((r["finished_offset_s"] for r in qd), default=0.0)
        pages = sum(r.get("pages") or 0 for r in qd)
        by_queue[q] = {
            "completed": len(qd),
            "pages": pages,
            "makespan_s": round(makespan, 2),
            "docs_per_min": round(len(qd) / (makespan / 60), 2) if makespan > 0 else None,
            "mean_doc_latency_s": round(statistics.fmean(r["total_s"] for r in qd), 2) if qd else None,
        }

    stage_names = ["validate", "ocr", "extract", "parse_llm", "tree", "index", "drive", "total"]
    stages = {s: stage_stats([r["timings"].get(s) for r in results if s in r["timings"]])
              for s in stage_names}
    ocr_pages = sum(r.get("pages") or 0 for r in results if "ocr" in r["timings"])
    ocr_total = sum(r["timings"]["ocr"] for r in results if "ocr" in r["timings"])
    parse_modes: dict[str, int] = {}
    for r in done:
        parse_modes[r.get("parse_mode") or "?"] = parse_modes.get(r.get("parse_mode") or "?", 0) + 1

    return {
        "run_id": run_id,
        "db_name": db_name,
        "interrupted": interrupted,
        "options": options,
        "triage": triage_summary,
        "processed": len(results),
        "outcomes": dict(sorted(outcomes.items())),
        "processing_wall_s": round(processing_wall_s, 2),
        "throughput": {
            "overall_docs_per_min": round(len(done) / (processing_wall_s / 60), 2)
            if processing_wall_s > 0 and done else None,
            **by_queue,
            "ocr_seconds_per_page": round(ocr_total / ocr_pages, 2) if ocr_pages else None,
        },
        "stage_timings": stages,
        "llm": llm_stats,
        "parse_modes": parse_modes,
        # After the full chain a finished file is searchable at once; the card
        # (and so "complete") comes from the card wave.
        "doc_status": {k: sum(1 for r in done if r.get("doc_status") == k)
                       for k in sorted({r.get("doc_status") or "?" for r in done})},
        "failures": [{"file": r["filename"], "pdf_id": r.get("pdf_id"), "stage": r.get("stage"),
                      "reason": r.get("error")} for r in results if r["outcome"] == "failed"],
        "rejected": [{"file": r["filename"], "reason": r.get("error")}
                     for r in results if r["outcome"] == "rejected"],
        "needs_review": [{"file": r["filename"], "pdf_id": r.get("pdf_id"),
                          "confidence": r.get("confidence"), "issues": r.get("quality_issues")}
                         for r in done if r.get("quality_passed") is False],
        "documents": results,
    }


def render_triage(summary: dict, entries: list[dict]) -> str:
    lines = ["", "=== TRIAGE ===",
             f"files: {summary['files']}   ({summary['seconds']}s)"]
    for k, v in summary["by_category"].items():
        lines.append(f"  {k:<20} {v}")
    lines.append(f"detected text/scanned: {summary['detected']['text']}/{summary['detected']['scanned']}"
                 f"   total pages: {summary['total_pages']}"
                 f"   pages to process (digital/scanned): {summary['pages_to_process']['digital']}"
                 f"/{summary['pages_to_process']['scanned']}")
    for e in entries:
        if e["category"] in ("corrupt", "rejected", "failed", "duplicate_in_folder"):
            lines.append(f"  [{e['category']}] {Path(e['path']).name}: {e.get('reason', '')}")
    return "\n".join(lines)


def render_report(rep: dict) -> str:
    t = rep["throughput"]
    lines = ["", "=== BULK INGEST REPORT ===",
             f"run {rep['run_id']}  db={rep['db_name']}"
             + ("  ** INTERRUPTED **" if rep["interrupted"] else ""),
             f"processed {rep['processed']} files in {rep['processing_wall_s']}s: {rep['outcomes']}",
             f"throughput overall: {t['overall_docs_per_min']} docs/min",
             f"  digital: {t['digital']['completed']} docs, {t['digital']['docs_per_min']} docs/min,"
             f" mean latency {t['digital']['mean_doc_latency_s']}s",
             f"  scanned: {t['scanned']['completed']} docs ({t['scanned']['pages']} pages),"
             f" {t['scanned']['docs_per_min']} docs/min, mean latency {t['scanned']['mean_doc_latency_s']}s,"
             f" OCR {t['ocr_seconds_per_page']} s/page",
             "stage timings (mean / p95 / total, seconds):"]
    for s, st in rep["stage_timings"].items():
        if st.get("n"):
            lines.append(f"  {s:<10} n={st['n']:<4} {st['mean_s']:>8} / {st['p95_s']:>8} / {st['total_s']:>9}")
    llm = rep["llm"]
    lines.append(f"LLM: gemini calls {llm['gemini_calls']}, groq calls {llm['groq_calls']}, "
                 f"rate-limit hits {llm['rate_limit_hits']}, retries {llm['retries']}, "
                 f"event-loop lag {llm.get('event_loop_lag')}")
    lines.append(f"parse modes: {rep['parse_modes']}")
    lines.append(f"document status after this run: {rep.get('doc_status')}  "
                 f"(searchable = tree + dense + fts; complete also has its card)")
    if rep["failures"]:
        lines.append(f"FAILURES ({len(rep['failures'])}):")
        lines += [f"  {f['file']} [{f['stage']}]: {f['reason']}" for f in rep["failures"]]
    if rep["rejected"]:
        lines.append(f"REJECTED ({len(rep['rejected'])}):")
        lines += [f"  {f['file']}: {f['reason']}" for f in rep["rejected"]]
    if rep["needs_review"]:
        lines.append(f"NEEDS REVIEW - parse quality check failed ({len(rep['needs_review'])}):")
        lines += [f"  {f['file']} ({f['pdf_id']}) confidence {f['confidence']}: {f['issues']}"
                  for f in rep["needs_review"]]
    return "\n".join(lines)


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2, default=str, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


if __name__ == "__main__":
    s = stage_stats([1, 2, 3, 4, 100])
    assert s["p50_s"] == 3 and s["max_s"] == 100 and s["n"] == 5, s
    res = [
        {"filename": "a.pdf", "queue": "digital", "outcome": "done", "finished_offset_s": 30.0,
         "total_s": 10.0, "timings": {"parse_llm": 8.0, "total": 10.0}, "quality_passed": False,
         "confidence": 0.4, "quality_issues": ["x"], "pdf_id": "p", "parse_mode": "hybrid_llm_ner"},
        {"filename": "b.pdf", "queue": "scanned", "outcome": "done", "finished_offset_s": 120.0,
         "total_s": 100.0, "pages": 10, "timings": {"ocr": 50.0, "total": 100.0}},
        {"filename": "c.pdf", "queue": "digital", "outcome": "failed", "stage": "parse",
         "error": "gave up", "finished_offset_s": 5.0, "total_s": 5.0, "timings": {}},
    ]
    rep = build_report(run_id="r", db_name="x", options={}, triage_summary={}, results=res,
                       processing_wall_s=120.0, llm_stats={"gemini_calls": 1, "groq_calls": 0,
                                                           "rate_limit_hits": 0, "retries": 0},
                       interrupted=False)
    assert rep["throughput"]["digital"]["docs_per_min"] == 2.0
    assert rep["throughput"]["scanned"]["docs_per_min"] == 0.5
    assert rep["throughput"]["overall_docs_per_min"] == 1.0
    assert rep["throughput"]["ocr_seconds_per_page"] == 5.0
    assert len(rep["needs_review"]) == 1 and len(rep["failures"]) == 1
    print(render_report(rep))
    print("report self-check OK")
