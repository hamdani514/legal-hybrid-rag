import difflib
import re
from pathlib import Path

import fitz
from loguru import logger


def _ocr_page(pdf_path: str, index: int = 0) -> str:
    """OCR one page with the same engine the extractor uses (app.ingestion.ocr)."""
    from app.ingestion.ocr import ocr_page

    try:
        with fitz.open(pdf_path) as doc:
            if len(doc) <= index:
                return ""
            text, _ = ocr_page(doc[index])
            return text
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Validation OCR failed: {e}")
        return ""


def _page1_is_scan(pdf_path: str) -> bool:
    from app.ingestion.ocr import page_is_scan

    with fitz.open(pdf_path) as doc:
        return len(doc) > 0 and page_is_scan(doc[0])


def _fuzzy_has(words: list[str], target: str, cutoff: float = 0.75) -> bool:
    """True if some word reads as `target` allowing OCR misreads (PAKIGPAN, SUPREMB, COURL)."""
    return bool(difflib.get_close_matches(target, words, n=1, cutoff=cutoff))


# Keywords matching Pakistan Supreme Court
_COURT_PATTERNS = [
    r"supreme\s*court",
    r"supresme",
    r"suprime",
    r"supremecourt",
    r"tsupbmt",
    r"tsujpbmt",
    r"s\s*u\s*p\s*r\s*e\s*m\s*e",
]
_PAKISTAN_PATTERNS = [
    r"pakistan",
    r"0lpakistan",
    r"0fpakistan",
    r"0f\s*pakistan",
    r"p\s*a\s*k\s*i\s*s\s*t\s*a\s*n",
]


def _court_markers(text: str, ocr_used: bool) -> tuple[bool, bool]:
    """(mentions the Supreme Court, mentions Pakistan) for one page's text."""
    normalized = re.sub(r"\s+", " ", text.lower()).strip()
    logger.debug(f"Normalized validation text: {normalized[:300]}")
    has_court = any(re.search(pat, normalized) for pat in _COURT_PATTERNS)
    has_pakistan = any(re.search(pat, normalized) for pat in _PAKISTAN_PATTERNS)
    if ocr_used and not (has_court and has_pakistan):
        # OCR of an old or faint scan misreads a letter or two of the heading.
        # Only for OCR text: on a typed page "supremacy" would pass for "supreme".
        words = re.findall(r"[a-z]+", normalized)
        has_court = has_court or _fuzzy_has(words, "supreme")
        has_pakistan = has_pakistan or _fuzzy_has(words, "pakistan")
    return has_court, has_pakistan


_LOWER_FORUM = (r"(?:lahore|sindh|peshawar|balochistan|baluchistan|islamabad)\s+high\s+court|high\s+court\s+of\s+"
                r"(?:sindh|balochistan|baluchistan)|federal\s+shariat\s+court|service\s+tribunal|tribunal")


def _supreme_court_layout(text: str) -> bool:
    """A Supreme Court first page recognised by its layout when OCR cannot read the heading.

    Four of the 260 scanned judgments have a heading no OCR recovers (faded, cut
    off, or read as "CTW ER QUTRREMR COTIRT OF PAKISTAN"), yet every one has the
    Court's page-1 structure: a "(... Jurisdiction)" line, "Present:" (or
    "Bench:") and the judges as "Mr. Justice ...", or an appeal "against (the)
    judgment of the
    Lahore High Court" / a tribunal, which only the Supreme Court hears. A High
    Court judgment names its own court in its first lines and is refused.
    Applied to OCR text only. Measured: all 260 scanned judgments and the 10
    tilted scans in `not judgement document` accepted; the 40 Urdu judgments
    there (English-only pipeline) are still refused.
    """
    t = re.sub(r"[ \t]+", " ", text.lower())
    lines = [l.strip() for l in t.splitlines() if len(re.sub(r"[^a-z]", "", l)) >= 3]
    if any("high court" in l or "judicial department" in l or "judgment sheet" in l for l in lines[:3]):
        return False
    words = re.findall(r"[a-z]+", " ".join(lines[:30]))
    justices = len(re.findall(r"\bjustice\b", " ".join(lines[:30])))
    if not justices:
        return False
    if _fuzzy_has(words, "jurisdiction", 0.8) and (_fuzzy_has(words, "present", 0.8) or "bench" in words):
        return True
    return bool(re.search(r"against\s+(?:the\s+)?(?:impugned\s+)?(?:judgment|judgement|order)s?\b[^|]{0,120}?\b(?:of|by|passed\s+by)\s+"
                          r"(?:the\s+)?(?:learned\s+)?(?:" + _LOWER_FORUM + ")", " ".join(lines[:40]))) and justices >= 1


def validate_judgment(pdf_path: str) -> tuple[bool, str]:
    """
    Checks if the PDF is a Pakistan Supreme Court judgment.
    Looks at the first page for court indicators (digital or OCR); for a scanned
    file whose first page lacks them, also at page 2.
    Returns (is_valid: bool, message: str)
    """
    try:
        # Check if file exists and is not empty
        p_path = Path(pdf_path)
        if not p_path.exists() or p_path.stat().st_size == 0:
            return False, "Uploaded file is empty or missing."

        # Extract digital text from first page
        first_page_text = ""
        ocr_used = False
        with fitz.open(pdf_path) as doc:
            if len(doc) == 0:
                return False, "PDF document contains no pages."
            first_page_text = doc[0].get_text("text") or ""

        # If digital text is missing/too short, run OCR on first page. Also when page 1
        # is a scanned image whose text layer (the scanner's own OCR) lacks the court
        # heading: that layer is the problem, not the judgment.
        if len(first_page_text.strip()) < 80 or (
                not all(_court_markers(first_page_text, False)) and _page1_is_scan(pdf_path)):
            logger.info(f"Digital text on page 1 too short ({len(first_page_text)} chars). Running OCR for validation.")
            first_page_text = _ocr_page(pdf_path, 0)
            ocr_used = True

        has_court, has_pakistan = _court_markers(first_page_text, ocr_used)
        if ocr_used and not (has_court and has_pakistan) and _supreme_court_layout(first_page_text):
            has_court = has_pakistan = True
        if ocr_used and not (has_court and has_pakistan):
            # Some scanned judgments open with a one-page order of the bench and
            # carry the court heading on page 2.
            second = _ocr_page(pdf_path, 1)
            has_court, has_pakistan = _court_markers(second, True)
            if not (has_court and has_pakistan) and _supreme_court_layout(second):
                has_court = has_pakistan = True

        if has_court and has_pakistan:
            logger.info("PDF validated successfully as a Pakistan Supreme Court judgment.")
            return True, ""

        logger.warning("PDF validation failed: does not appear to be a Pakistan Supreme Court judgment.")
        return False, "The uploaded PDF is not a Pakistan Supreme Court judgment."

    except Exception as e:
        logger.exception(f"Error validating PDF judgment: {e}")
        return False, f"Failed to validate PDF judgment: {e}"
