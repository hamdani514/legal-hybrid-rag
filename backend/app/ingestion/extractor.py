from pathlib import Path
import shutil

import cv2
import easyocr
import fitz
import numpy as np
from loguru import logger
from PIL import Image
import pytesseract


# ---------------------------------------------------------------------------
# Configure Tesseract path for Windows
# ---------------------------------------------------------------------------
_TESSERACT_PATHS = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
]

for _path in _TESSERACT_PATHS:
    if Path(_path).exists():
        pytesseract.pytesseract.tesseract_cmd = _path
        logger.info(f"Tesseract configured at: {_path}")
        break
else:
    logger.warning("Tesseract not found in default locations - relying on PATH")


# One EasyOCR Reader per process, built on first use. Constructing a Reader
# loads its detection and recognition models (seconds of CPU and hundreds of
# MB), so building it inside the per-page fallback reloaded the model on every
# page Tesseract failed on. Lazy, because most runs never reach the fallback.
_EASYOCR_READER = None


def _get_easyocr_reader():
    global _EASYOCR_READER
    if _EASYOCR_READER is None:
        _EASYOCR_READER = easyocr.Reader(["en"], gpu=False)
    return _EASYOCR_READER


def _uploads_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "uploads"


def _page_separator(page_number: int) -> str:
    return f"\n\n--- PAGE {page_number} ---\n\n"


# ---------------------------------------------------------------------------
# Image pre-processing for better OCR accuracy
# ---------------------------------------------------------------------------

def _preprocess_image_for_ocr(img_path: str) -> Image.Image:
    """
    Apply image pre-processing to improve OCR accuracy on scanned documents.

    Steps:
      1. Convert to grayscale
      2. Resize (upscale) for better character recognition
      3. Apply adaptive thresholding to binarize
      4. Denoise to remove speckle artifacts
      5. Deskew if tilted
    """
    # Read image with OpenCV
    img = cv2.imread(img_path)
    if img is None:
        # Fallback: just return the PIL image as-is
        return Image.open(img_path)

    # 1. Convert to grayscale
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # 2. Upscale if the image is small (improves Tesseract accuracy)
    height, width = gray.shape
    if height < 2000:
        scale_factor = 2.0
        gray = cv2.resize(
            gray,
            None,
            fx=scale_factor,
            fy=scale_factor,
            interpolation=cv2.INTER_CUBIC,
        )

    # 3. Denoise
    denoised = cv2.fastNlMeansDenoising(gray, h=10, templateWindowSize=7, searchWindowSize=21)

    # 4. Adaptive thresholding for binarization
    binary = cv2.adaptiveThreshold(
        denoised, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        blockSize=15,
        C=8,
    )

    # 5. Deskew detection (optional — only if skew is significant)
    try:
        coords = np.column_stack(np.where(binary < 128))
        if len(coords) > 100:
            angle = cv2.minAreaRect(coords)[-1]
            if angle < -45:
                angle = -(90 + angle)
            else:
                angle = -angle
            # Only deskew if tilt is noticeable but not extreme
            if 0.5 < abs(angle) < 10:
                (h, w) = binary.shape
                center = (w // 2, h // 2)
                M = cv2.getRotationMatrix2D(center, angle, 1.0)
                binary = cv2.warpAffine(
                    binary, M, (w, h),
                    flags=cv2.INTER_CUBIC,
                    borderMode=cv2.BORDER_REPLICATE,
                )
    except Exception:
        pass  # Deskew is best-effort

    # Convert back to PIL Image
    return Image.fromarray(binary)


# ---------------------------------------------------------------------------
# Digital (typed) text extraction
# ---------------------------------------------------------------------------

def extract_digital(pdf_path: str, pdf_id: str) -> str:
    logger.info(f"[{pdf_id}] Starting digital extraction")
    chunks = []

    with fitz.open(pdf_path) as doc:
        for idx, page in enumerate(doc, start=1):
            text = page.get_text("text") or ""
            chunks.append(_page_separator(idx))
            chunks.append(text)

    result = "".join(chunks)
    logger.info(f"[{pdf_id}] Digital extraction complete (chars={len(result)})")
    return result


# ---------------------------------------------------------------------------
# Scanned PDF OCR extraction (enhanced)
# ---------------------------------------------------------------------------

def extract_scanned(pdf_path: str, pdf_id: str) -> str:
    """
    Extract text from scanned PDF using OCR with image pre-processing.

    Pipeline per page:
      1. Render page to high-DPI image via PyMuPDF
      2. Pre-process image (grayscale, denoise, binarize, deskew)
      3. Run Tesseract OCR with optimized config
      4. Fallback to EasyOCR if Tesseract fails
    """
    logger.info(f"[{pdf_id}] Starting enhanced scanned extraction (OCR)")
    ocr_dir = _uploads_dir() / f"ocr_tmp_{pdf_id}"
    ocr_dir.mkdir(parents=True, exist_ok=True)
    chunks = []

    try:
        with fitz.open(pdf_path) as doc:
            total_pages = len(doc)
            logger.info(f"[{pdf_id}] Processing {total_pages} pages with OCR")

            for idx, page in enumerate(doc, start=1):
                img_path = ocr_dir / f"page_{idx}.png"

                # Render at 300 DPI for good OCR quality
                pix = page.get_pixmap(dpi=300)
                pix.save(str(img_path))

                text = ""

                # --- Attempt 1: Tesseract with pre-processed image ---
                try:
                    processed_img = _preprocess_image_for_ocr(str(img_path))
                    text = pytesseract.image_to_string(
                        processed_img,
                        lang="eng",
                        config="--oem 3 --psm 6",
                    )

                    # If pre-processed text is too short, try raw image too
                    if len(text.strip()) < 100:
                        with Image.open(img_path) as raw_img:
                            raw_text = pytesseract.image_to_string(
                                raw_img,
                                lang="eng",
                                config="--oem 3 --psm 6",
                            )
                        # Use whichever got more text
                        if len(raw_text.strip()) > len(text.strip()):
                            text = raw_text
                            logger.debug(f"[{pdf_id}] Page {idx}: raw image gave better result")

                except Exception as e:
                    logger.warning(
                        f"[{pdf_id}] pytesseract failed on page {idx}: {e}. "
                        "Falling back to EasyOCR."
                    )
                    # --- Attempt 2: EasyOCR fallback ---
                    try:
                        reader = _get_easyocr_reader()
                        result = reader.readtext(str(img_path), detail=0)
                        text = " ".join(result)
                    except Exception as e2:
                        logger.error(f"[{pdf_id}] EasyOCR also failed on page {idx}: {e2}")
                        text = ""

                chunks.append(_page_separator(idx))
                chunks.append(text or "")

                if idx % 5 == 0 or idx == total_pages:
                    logger.info(f"[{pdf_id}] OCR progress: {idx}/{total_pages} pages")

        result = "".join(chunks)
        logger.info(
            f"[{pdf_id}] Scanned extraction complete "
            f"(chars={len(result)}, pages={total_pages})"
        )
        return result

    finally:
        shutil.rmtree(ocr_dir, ignore_errors=True)
        logger.info(f"[{pdf_id}] Cleaned OCR temp directory: {ocr_dir}")


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
        # Try the other method
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
