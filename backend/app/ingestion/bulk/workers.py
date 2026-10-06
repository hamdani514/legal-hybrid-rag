"""
Process-pool entry points for bulk ingestion.

Why a separate module: on Windows ProcessPoolExecutor spawns fresh interpreters,
so every worker re-imports whatever module its target function lives in. These
functions therefore live here, away from the async driver, and the pool
initializer keeps each worker light:

* `easyocr` is replaced by a stub that imports the real package on first
  attribute access. `app.ingestion.extractor` and `validator` import easyocr at
  module level, which drags in torch: measured 391 MB RSS per worker with it,
  129 MB without. Twelve OCR workers is the difference between ~4.7 GB and
  ~1.5 GB. EasyOCR is only the fallback when Tesseract throws, so most workers
  never pay for it; when one does, the stub loads the real module and
  extractor's cached Reader takes over.
* loguru is turned down to WARNING in workers: detect_pdf_type / validator log
  one INFO line per file, which is noise across 3,000 files.

Both functions return plain dicts (picklable) and never raise: a failure is a
result with an `error`, so one bad PDF cannot take down the pool.
"""
from __future__ import annotations

import hashlib
import sys
import time
from pathlib import Path


# Pool bootstrap, passed as ProcessPoolExecutor(initializer=exec,
# initargs=(BOOTSTRAP_SRC,)). It has to be source run by a builtin rather than a
# function in this module: unpickling any function from app.ingestion.* first
# imports app/ingestion/__init__.py, which imports extractor, which imports
# easyocr -> torch, before an initializer from here could install the stub.
# The worker runs the initializer before it unpickles any task, so this wins.
BOOTSTRAP_SRC = r"""
def _bulk_bootstrap(log_level):
    import importlib, sys, types
    if "easyocr" not in sys.modules:
        stub = types.ModuleType("easyocr")
        stub.__spec__ = None
        def _load(name):
            if name.startswith("__"):
                raise AttributeError(name)
            if sys.modules.get("easyocr") is stub:
                del sys.modules["easyocr"]
            return getattr(importlib.import_module("easyocr"), name)
        stub.__getattr__ = _load  # PEP 562: only for missing attributes
        sys.modules["easyocr"] = stub
    from loguru import logger
    logger.remove()
    logger.add(sys.stderr, level=log_level)
_bulk_bootstrap(%r)
del _bulk_bootstrap
"""


def pool_kwargs(log_level: str = "WARNING") -> dict:
    """initializer/initargs for a ProcessPoolExecutor running these tasks."""
    return {"initializer": exec, "initargs": (BOOTSTRAP_SRC % log_level,)}


def _probe_torch() -> dict:
    import app.ingestion.extractor as ex  # noqa: F401
    import psutil

    return {"torch_loaded": "torch" in sys.modules,
            "rss_mb": psutil.Process().memory_info().rss / 1e6}


def sha256_file(path: str) -> str:
    """Same digest upload_pdf computes (sha256 over the whole file), streamed."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def triage_one(path: str) -> dict:
    """Hash, sanity-check, detect type; validate digital files (cheap).

    Scanned files are NOT validated here: validate_judgment OCRs page 1 when the
    page has no text layer, which costs seconds. That happens in ocr_one instead.
    """
    t0 = time.perf_counter()
    out: dict = {"path": path, "size": 0, "pages": None, "file_hash": None,
                 "detected_type": None, "valid": None, "reason": "", "error": ""}
    try:
        p = Path(path)
        out["size"] = p.stat().st_size
        if out["size"] == 0:
            out["error"] = "empty file"
            return out
        with open(path, "rb") as fh:
            head = fh.read(1024)
        out["file_hash"] = sha256_file(path)
        # upload_pdf requires the bytes to start with %PDF.
        if not head.startswith(b"%PDF"):
            out["error"] = "not a PDF (missing %PDF header)"
            return out

        import fitz

        try:
            with fitz.open(path) as doc:
                if doc.needs_pass:
                    out["error"] = "encrypted PDF (password required)"
                    return out
                out["pages"] = len(doc)
                if out["pages"] == 0:
                    out["error"] = "PDF has no pages"
                    return out
                doc[0].get_text("text")  # forces page 1 to parse
        except Exception as e:  # noqa: BLE001
            out["error"] = f"unreadable PDF: {e}"
            return out

        from app.ingestion.detector import detect_pdf_type

        out["detected_type"] = detect_pdf_type(path)
        if out["detected_type"] == "text":
            from app.ingestion.validator import validate_judgment

            ok, msg = validate_judgment(path)
            out["valid"], out["reason"] = bool(ok), msg
    except Exception as e:  # noqa: BLE001
        out["error"] = f"triage error: {e}"
    finally:
        out["seconds"] = round(time.perf_counter() - t0, 4)
    return out


def ocr_one(path: str, pdf_id: str, validate: bool = True) -> dict:
    """Validate (OCRs page 1 if needed) then run the existing extract().

    extract() writes uploads/{pdf_id}.txt, which doubles as the resume cache:
    a re-run with the same pdf_id finds the file and skips OCR entirely.
    """
    out: dict = {"pdf_id": pdf_id, "path": path, "valid": True, "reason": "",
                 "chars": 0, "pages": None, "validate_s": 0.0, "extract_s": 0.0,
                 "error": ""}
    try:
        if validate:
            t0 = time.perf_counter()
            from app.ingestion.validator import validate_judgment

            ok, msg = validate_judgment(path)
            out["validate_s"] = round(time.perf_counter() - t0, 3)
            if not ok:
                out["valid"], out["reason"] = False, msg
                return out

        import fitz

        with fitz.open(path) as doc:
            out["pages"] = len(doc)

        from app.ingestion.extractor import extract

        t0 = time.perf_counter()
        text = extract(pdf_path=path, pdf_id=pdf_id, detected_type="scanned")
        out["extract_s"] = round(time.perf_counter() - t0, 3)
        out["chars"] = len(text)
    except Exception as e:  # noqa: BLE001
        out["error"] = f"OCR extraction failed: {type(e).__name__}: {e}"
    return out


# -- LLM parse worker --------------------------------------------------------
# Why parsing runs in processes even though it is "just" async I/O: measured
# in the 4-doc pilot, every Gemini call froze the shared event loop for
# 2.3-11.6 s. parser.call_gemini builds a new genai.Client per call (1.3 s of
# synchronous CPU each, measured) plus lazy imports on first use, and none of
# that can be fixed from here without editing the parser. In one loop those
# stalls serialise all in-flight parses, so --llm-concurrency 3 behaved like
# ~1. One process per LLM slot lets the stalls overlap. Rate-limit detection
# works as in llm_guard: a loguru sink in the worker collects 429/timeout
# records emitted by app.ingestion.* during the task (one task per process at
# a time, so no ContextVar is needed).
_PARSE_STATE: dict = {}


def _parse_worker_setup() -> dict:
    if _PARSE_STATE.get("ready"):
        return _PARSE_STATE
    from loguru import logger

    from app.ingestion import parser
    from app.ingestion.bulk.llm_guard import RATE_LIMIT_RE

    # Counters live in the module-level dict itself: the closures below must
    # mutate the same object parse_one reads (a copy froze them at 0).
    st = _PARSE_STATE
    st.update(hits=[], gemini=0, groq=0)

    def _sink(message) -> None:
        rec = message.record
        name = rec["name"] or ""
        if not name.startswith("app.ingestion") or name.startswith("app.ingestion.bulk"):
            return
        text = rec["message"]
        if "Calling Groq (" in text:
            st["groq"] += 1
        elif rec["level"].no >= 30 and RATE_LIMIT_RE.search(text):
            st["hits"].append(text[:300])

    logger.add(_sink, level="INFO")
    orig = parser.call_ollama

    async def _counted(prompt, system):
        st["gemini"] += 1
        return await orig(prompt, system)

    parser.call_ollama = _counted
    st["ready"] = True
    return st


def parse_one(pdf_id: str, text: str, timeout: float) -> dict:
    """parse_sections in this process's own event loop; never raises."""
    import asyncio

    st = _parse_worker_setup()
    st["hits"].clear()
    g0, q0 = st["gemini"], st["groq"]
    out = {"final": None, "hits": [], "timed_out": False, "error": "",
           "gemini_calls": 0, "groq_calls": 0}
    try:
        from app.ingestion.parser import parse_sections

        async def _run():
            return await asyncio.wait_for(parse_sections(pdf_id=pdf_id, extracted_text=text),
                                          timeout=timeout)

        out["final"] = asyncio.run(_run())
    except asyncio.TimeoutError:
        out["timed_out"] = True
    except Exception as e:  # noqa: BLE001
        out["error"] = f"parse failed: {type(e).__name__}: {e}"
    out["hits"] = list(st["hits"])
    out["gemini_calls"], out["groq_calls"] = st["gemini"] - g0, st["groq"] - q0
    return out


BACKEND_UPLOADS_SAMPLE = Path(__file__).resolve().parents[3] / "uploads" / "5a14105d-8a45-413c-8c93-26d6301cf028.txt"

_SELF_CHECK_DRIVER = r"""
import json, sys
from concurrent.futures import ProcessPoolExecutor
from app.ingestion.bulk import workers
if __name__ == "__main__":
    with ProcessPoolExecutor(max_workers=1, **workers.pool_kwargs("ERROR")) as pool:
        probe = pool.submit(workers._probe_torch).result()
        bad = pool.submit(workers.triage_one, sys.argv[1]).result()
    print(json.dumps({"probe": probe, "bad": bad}))
"""


if __name__ == "__main__":
    # Self-check: a pooled worker must import the extractor without torch, and
    # triage must classify a non-PDF as corrupt rather than raise. Driven from
    # a `-c` main because spawn re-imports a file-based __main__ in every
    # worker (running this module as main would import app.ingestion first).
    # The same rule binds ingest_bulk.py: no app.* imports at module level.
    import json
    import subprocess

    backend = Path(__file__).resolve().parents[3]
    proc = subprocess.run([sys.executable, "-c", _SELF_CHECK_DRIVER, __file__],
                          cwd=backend, capture_output=True, text=True, timeout=300)
    assert proc.returncode == 0, proc.stderr[-2000:]
    res = json.loads(proc.stdout.strip().splitlines()[-1])
    print("worker probe:", res["probe"])
    assert res["probe"]["torch_loaded"] is False, "easyocr stub failed: torch imported eagerly"
    assert res["bad"]["error"].startswith("not a PDF"), res["bad"]
    assert res["bad"]["file_hash"] == sha256_file(__file__)

    # parse_one in-process with Gemini faked: counts calls, collects a 429
    # logged by the parser, never makes a network call.
    import tempfile

    from loguru import logger as _lg

    from app.ingestion import parser as _parser

    _tmp = Path(tempfile.mkdtemp())
    _parser._uploads_dir = lambda: _tmp

    async def _fake_gemini(prompt, system):
        _lg.patch(lambda r: r.update(name="app.ingestion.parser")).error(
            "Gemini API error in parser: 429 RESOURCE_EXHAUSTED")
        return ""

    _parser.call_gemini = _fake_gemini
    sample = (BACKEND_UPLOADS_SAMPLE.read_text(encoding="utf-8")
              if BACKEND_UPLOADS_SAMPLE.exists() else "SUPREME COURT OF PAKISTAN\n" * 200)
    r1 = parse_one("selfcheck_a", sample, 120)
    assert r1["error"] == "" and r1["final"] is not None, r1["error"]
    assert r1["gemini_calls"] >= 1, r1
    assert any("429" in h for h in r1["hits"]), r1["hits"]
    print("parse_one:", {k: r1[k] for k in ("gemini_calls", "groq_calls", "timed_out")},
          "hits", len(r1["hits"]))
    print("workers self-check OK")
