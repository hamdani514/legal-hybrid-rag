"""
Bulk ingestion of a folder of judgment PDFs.

The single-upload path (app.api.admin.upload_pdf + run_extraction) is built for
one file at a time behind an HTTP request. Ingesting the 3,000+ judgment corpus
through it would mean 3,000 requests, no OCR parallelism, unbounded concurrent
LLM calls the moment many uploads land together, and no way to resume after a
crash. This package wraps the SAME stage functions (detect_pdf_type, extract,
parse_sections, build_and_save_tree) in a batch driver:

    triage.py     fast, LLM-free pass: hash, dedupe, detect, catch corrupt files
    workers.py    process-pool entry points (triage + OCR), import-light
    llm_guard.py  bounded LLM concurrency, 429 detection, backoff with jitter
    state.py      append-only local state so pdf_ids and rejections survive restarts
    pipeline.py   the async driver: two queues (digital / scanned), DB records
    report.py     manifest + final report (throughput, stage timings, failures)

Entry point: backend/ingest_bulk.py.
"""
