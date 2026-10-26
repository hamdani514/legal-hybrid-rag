import json
from pathlib import Path

import fitz
from loguru import logger


def _uploads_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "uploads"


def _page_separator(page_number: int) -> str:
    return f"\n\n--- PAGE {page_number} ---\n\n"


def _join_pages(pages: list[str]) -> str:
    return "".join(_page_separator(i) + (t or "") for i, t in enumerate(pages, start=1))


# ---------------------------------------------------------------------------
# Digital (typed) text extraction
# ---------------------------------------------------------------------------

def extract_digital(pdf_path: str, pdf_id: str) -> str:
    logger.info(f"[{pdf_id}] Starting digital extraction")
    with fitz.open(pdf_path) as doc:
        result = _join_pages([page.get_text("text") or "" for page in doc])
    logger.info(f"[{pdf_id}] Digital extraction complete (chars={len(result)})")
    return result


# ---------------------------------------------------------------------------
# Scanned PDF extraction (OCR)
# ---------------------------------------------------------------------------

def _easyocr_pages(pdf_path: str) -> list[str]:
    """Last resort when Tesseract itself cannot run (not installed, crashed)."""
    import easyocr  # deferred: loads torch, hundreds of MB
    import numpy as np

    reader = easyocr.Reader(["en"], gpu=False)
    out = []
    with fitz.open(pdf_path) as doc:
        for page in doc:
            pix = page.get_pixmap(dpi=300)
            img = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, pix.n)
            out.append("\n".join(reader.readtext(img, detail=0, paragraph=True)))
    return out


def extract_scanned(pdf_path: str, pdf_id: str) -> str:
    """Text of a scanned PDF: OCR (app.ingestion.ocr) for pages without a text layer,
    the text layer for pages that have one. Writes uploads/{pdf_id}.ocr.json with
    the OCR quality figures (mean confidence, vocabulary rate, low-quality pages)."""
    from app.ingestion.ocr import extract_pages

    logger.info(f"[{pdf_id}] Starting scanned extraction (OCR)")
    try:
        pages, summary = extract_pages(pdf_path, pdf_id)
    except Exception as e:  # noqa: BLE001
        logger.error(f"[{pdf_id}] Tesseract OCR failed ({type(e).__name__}: {e}); falling back to EasyOCR")
        pages, summary = _easyocr_pages(pdf_path), {"engine": "easyocr"}
    summary.setdefault("engine", "tesseract")
    try:
        (_uploads_dir() / f"{pdf_id}.ocr.json").write_text(json.dumps(summary), encoding="utf-8")
    except OSError:
        pass
    result = _join_pages(pages)
    logger.info(f"[{pdf_id}] Scanned extraction complete (chars={len(result)}, pages={len(pages)})")
    return result


def ocr_summary(pdf_id: str) -> dict | None:
    """The OCR quality figures extract_scanned recorded for this judgment, if it was OCR'd."""
    p = _uploads_dir() / f"{pdf_id}.ocr.json"
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def ocr_issues(summary: dict | None) -> list[str]:
    """Quality-issue lines for a judgment whose OCR came out weak, for the admin review list."""
    if not summary or summary.get("engine") != "tesseract":
        return [] if not summary else ["OCR fell back to EasyOCR (Tesseract unavailable): text quality unverified"]
    issues = []
    if summary.get("vocab_rate") is not None and summary["vocab_rate"] < 0.9:
        issues.append(f"OCR quality low: {summary['vocab_rate']:.0%} of words recognised (typed text ~99%)")
    if summary.get("low_quality_pages"):
        issues.append(f"OCR quality low on page(s) {', '.join(map(str, summary['low_quality_pages']))}")
    return issues


# ---------------------------------------------------------------------------
# Unified extraction entry point
# ---------------------------------------------------------------------------

def extract(pdf_path: str, pdf_id: str, detected_type: str) -> str:
    """
    Unified PDF text extraction — works for both typed and scanned PDFs.
    Caches results to avoid re-extraction.
    """
    uploads_dir = _uploads_dir()
    uploads_dir.mkdir(parents=True, exist_ok=True)
    txt_path = uploads_dir / f"{pdf_id}.txt"

    if txt_path.exists():
        logger.info(f"[{pdf_id}] Existing extracted text found, skipping extraction")
        return txt_path.read_text(encoding="utf-8", errors="ignore")

    if detected_type == "text":
        text = extract_digital(pdf_path, pdf_id)
    else:
        text = extract_scanned(pdf_path, pdf_id)

    # Validate extraction produced usable content
    if len(text.strip()) < 100:
        logger.warning(
            f"[{pdf_id}] Extraction produced very little text ({len(text.strip())} chars). "
            "Attempting opposite extraction method as fallback."
        )
        if detected_type == "text":
            fallback_text = extract_scanned(pdf_path, pdf_id)
        else:
            fallback_text = extract_digital(pdf_path, pdf_id)

        if len(fallback_text.strip()) > len(text.strip()):
            logger.info(f"[{pdf_id}] Fallback extraction produced better result")
            text = fallback_text

    txt_path.write_text(text, encoding="utf-8")
    logger.info(f"[{pdf_id}] Saved extracted text to {txt_path}")
    return text
