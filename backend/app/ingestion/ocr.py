"""OCR for scanned judgments.

Measured on 39 typed judgment pages degraded to look scanned (true text known)
and 40 real pages from the scanned set; see INGESTION.md, "Scanned PDFs":

    old pipeline (300 dpi, adaptive threshold, psm 6, tessdata_fast)
        word accuracy 94.1%  precision 86.7%  key tokens 87.4%  garbage lines 2.4%
    this module
        word accuracy 97.6%  precision 97.4%  key tokens 97.0%  garbage lines 0.4%

What made the difference, in order of effect:

1. Render the page through its own transform at ~300 dpi and hand Tesseract the
   grayscale image. Tesseract binarises internally; the old adaptive threshold
   broke thin strokes and turned paper grain into "words". A tilted page is
   straightened first (deskew), and one scanned sideways or upside down is
   turned upright (ocr_gray).
2. Paint scanner artefacts white before OCR: dark borders and the binding
   shadow, long ruling lines, isolated specks.
3. tessdata_best (LSTM) instead of tessdata_fast. backend/tessdata holds it;
   without it the system model is used.
4. Re-read, line by line, the lines the page pass skipped or garbled (bold
   underlined headings, case-number lines).
5. Rebuild text from Tesseract's word boxes and drop what is noise: whole lines
   of low-confidence non-words (stamps, handwriting), and short non-words that
   sit outside the text column (margin specks, handwritten page numbers).
   "Non-word" means not in the archive vocabulary, data/ocr_lexicon.json,
   built from the typed judgments.
6. A few pattern fixes that are unambiguous in this corpus: a lost date dot
   (7.122017 -> 7.12.2017), registry letter L read as 1 (933-1/2013), No0.
7. Lay the lines out in paragraphs separated by blank lines, as typed text is:
   the section parser splits a judgment at blank lines (see _paragraphs).

Correcting words against the vocabulary was tried and rejected: it made real
pages look cleaner but lowered accuracy on the pages whose true text is known,
because it "corrects" party names that are not in the vocabulary.
"""
from __future__ import annotations

import json
import os
import re
import threading
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from pathlib import Path

import cv2
import fitz
import numpy as np
import pytesseract
from loguru import logger
from PIL import Image

for _path in (r"C:\Program Files\Tesseract-OCR\tesseract.exe", r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"):
    if Path(_path).exists():
        pytesseract.pytesseract.tesseract_cmd = _path
        break

_BACKEND = Path(__file__).resolve().parents[2]
_TESSDATA = _BACKEND / "tessdata"
_LEXICON = Path(__file__).resolve().parent / "data" / "ocr_lexicon.json"

# A page counts as having a usable text layer (no OCR needed) above this.
TEXT_LAYER_MIN_CHARS = 200
TARGET_WIDTH_PX = 2500  # ~300 dpi for the page sizes in this archive


@lru_cache(maxsize=1)
def lexicon() -> frozenset:
    try:
        return frozenset(json.loads(_LEXICON.read_text(encoding="utf-8")))
    except OSError:
        logger.warning(f"OCR vocabulary missing ({_LEXICON}); noise filtering falls back to confidence only")
        return frozenset()


@lru_cache(maxsize=1)
def _tess_config() -> str:
    cfg = "--oem 1 --psm 6 -c preserve_interword_spaces=1"
    if (_TESSDATA / "eng.traineddata").exists() and " " not in str(_TESSDATA):
        return f"--tessdata-dir {_TESSDATA.as_posix()} " + cfg
    if (_TESSDATA / "eng.traineddata").exists():
        # pytesseract splits the config on spaces; a quoted path does not survive
        # that on Windows, so point Tesseract at the folder through the environment.
        os.environ["TESSDATA_PREFIX"] = str(_TESSDATA)
        return cfg
    logger.warning("tessdata_best not found in backend/tessdata; using the system Tesseract model (less accurate)")
    return cfg


# ── page image ──────────────────────────────────────────────────────────────

def render_gray(page: fitz.Page) -> np.ndarray:
    """The page as a grayscale image ~2500 px wide.

    Rendering (not extracting the embedded image) applies the image's placement
    transform and the page rotation: some scanners store the bitmap mirrored or
    rotated and rely on the transform, and extracting it raw OCRs mirror text.
    """
    dpi = max(150, min(400, int(TARGET_WIDTH_PX / (page.rect.width / 72.0))))
    pix = page.get_pixmap(dpi=dpi, colorspace=fitz.csGRAY)
    return np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width).copy()


def clean(gray: np.ndarray) -> np.ndarray:
    """Paint scanner artefacts white; text pixels are left untouched."""
    g = gray.copy()
    h, w = g.shape
    _, binv = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    colfill = binv.mean(axis=0) / 255.0
    rowfill = binv.mean(axis=1) / 255.0

    def edge_run(fill, idx):
        """Length of the dark band that starts at the image edge and continues unbroken.
        A scanner border or binding shadow touches the edge; a bold heading or a
        line of text does not, so it is never mistaken for one."""
        n = 0
        for i in idx:
            if fill[i] < 0.5:
                break
            n += 1
        return n

    # dark borders / binding shadow
    k = edge_run(colfill, range(0, int(w * 0.12)))
    if k:
        g[:, :k + 4] = 255
    k = edge_run(colfill, range(w - 1, int(w * 0.88), -1))
    if k:
        g[:, w - k - 4:] = 255
    k = edge_run(rowfill, range(0, int(h * 0.06)))
    if k:
        g[:k + 4, :] = 255
    k = edge_run(rowfill, range(h - 1, int(h * 0.94), -1))
    if k:
        g[h - k - 4:, :] = 255
    # long thin lines: the page edge of a photocopy, margin rules. Horizontal lines
    # only when longer than half the page: shorter ones are heading underlines,
    # and removing those shaved the letters above them so Tesseract dropped
    # "IN THE SUPREME COURT OF PAKISTAN" entirely.
    _, binv = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    vk = cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(60, h // 25)))
    hk = cv2.getStructuringElement(cv2.MORPH_RECT, (w // 2, 1))
    vlines = cv2.dilate(cv2.morphologyEx(binv, cv2.MORPH_OPEN, vk), np.ones((3, 3), np.uint8))
    hlines = cv2.morphologyEx(binv, cv2.MORPH_OPEN, hk)
    g[(vlines > 0) | (hlines > 0)] = 255
    # isolated specks: tiny components with no other ink nearby
    _, binv = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    n, lab, st, _ = cv2.connectedComponentsWithStats(binv, 8)
    small = np.zeros(n, bool)
    small[1:] = st[1:, cv2.CC_STAT_AREA] < 12
    is_small = small[lab]
    near = cv2.dilate(np.where(is_small, 0, binv).astype(np.uint8), np.ones((25, 25), np.uint8))
    g[is_small & (near == 0)] = 255
    return g


# ── OCR and noise filtering ─────────────────────────────────────────────────

_ALNUM = re.compile(r"[A-Za-z0-9]")


def _words(img: np.ndarray, config: str | None = None, dy: int = 0) -> list[list[tuple]]:
    """Tesseract words grouped by line: (text, confidence, left, width, top, height)."""
    d = pytesseract.image_to_data(Image.fromarray(img), lang="eng", config=config or _tess_config(),
                                  output_type=pytesseract.Output.DICT)
    lines: dict = {}
    for i, w in enumerate(d["text"]):
        if w.strip():
            k = (d["block_num"][i], d["par_num"][i], d["line_num"][i])
            lines.setdefault(k, []).append((w, float(d["conf"][i]), d["left"][i], d["width"][i],
                                            d["top"][i] + dy, d["height"][i]))
    return list(lines.values())


def _recover_lines(img: np.ndarray, lines: list) -> list:
    """Re-read lines of ink that Tesseract's page pass skipped, and put them back in place.

    In single-block mode Tesseract sometimes drops a whole line whose type is much
    larger or bolder than the body, typically a bold underlined heading: on the
    260 scanned judgments, "IN THE SUPREME COURT OF PAKISTAN" was missing from
    19 first pages and case-number lines from several; on some it reads the line
    as garbage instead ("HE S ME T P."). Each band of ink not covered by a line of
    real words is re-read on its own (on all 260 first pages this brought the
    heading back on 255, from 241); the result replaces whatever
    was read there only if it contains real words, so stamps and handwriting stay out.
    """
    h, w = img.shape
    lex = lexicon()

    def real(t, cmin=60):
        a = re.sub(r"[^a-z]", "", t[0].lower())
        return (t[1] >= cmin and len(a) >= 3 and a in lex) or (t[1] >= cmin + 10 and re.search(r"\d{2,}", t[0]))

    def good(ws):
        return sum(t[1] for t in ws) / len(ws) >= 60 and sum(1 for t in ws if real(t, 0)) >= max(1, len(ws) // 2)

    span = lambda ws: (min(t[4] for t in ws), max(t[4] + t[5] for t in ws))
    # Rows of ink that no properly read line accounts for. Working on rows, not on
    # whole bands of ink, matters: a heading set close above "(Appellate
    # Jurisdiction)" forms one band with it, and the band looked read.
    _, binv = cv2.threshold(img, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    ink = (binv > 0).sum(axis=1) > max(8, int(0.004 * w))
    for ws in lines:
        if good(ws):
            a, b = span(ws)
            ink[max(0, a - 3):b + 3] = False
    bands, y = [], 0
    while y < h:
        if ink[y]:
            y0 = y
            while y < h and (ink[y] or (y + 3 < h and ink[y + 1:y + 4].any())):
                y += 1
            if 12 <= y - y0 <= 160:
                bands.append((y0, y))
        y += 1
    overlap = lambda a, b, y0, y1: min(y1, b) - max(y0, a) >= 0.4 * min(y1 - y0, b - a)
    # Each band: exactly its rows, padded with white (bits of the neighbouring
    # lines throw Tesseract off), read as it is and with its underline removed:
    # an underline touching bold letters is what makes Tesseract garble a heading
    # ("HE S ME C T P" vs "IN THE SUPREME COURT OF PAKISTAN", measured). All bands
    # are stacked into one image per variant, so a page costs at most two extra
    # Tesseract runs (each run reloads the model; one run per band made bulk OCR
    # several times slower).
    todo = []
    for y0, y1 in bands[:40]:
        cols = np.where(binv[y0:y1].sum(axis=0) > 0)[0]
        if len(cols) == 0 or cols[-1] - cols[0] < 0.05 * w:
            continue
        crop = img[y0:y1]
        _, cb = cv2.threshold(crop, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        ul = cv2.morphologyEx(cb, cv2.MORPH_OPEN, cv2.getStructuringElement(
            cv2.MORPH_RECT, (max(40, int(0.25 * (cols[-1] - cols[0]))), 1)))
        bare = crop
        if ul.any():
            bare = crop.copy()
            bare[cv2.dilate(ul, np.ones((3, 1), np.uint8)) > 0] = 255
        todo.append((y0, y1, crop, bare))
    if not todo:
        return lines
    gap = 40
    reads = []
    underlined = any(item[3] is not item[2] for item in todo)
    for variant in ((2, 3) if underlined else (2,)):    # index of crop / bare in todo
        rows, offsets, y = [], [], gap
        for item in todo:
            c = item[variant]
            rows.append(np.full((gap, w), 255, np.uint8))
            rows.append(c)
            offsets.append((y, y + c.shape[0], item[0]))
            y += gap + c.shape[0]
        rows.append(np.full((gap, w), 255, np.uint8))
        stack = cv2.copyMakeBorder(np.vstack(rows), 0, 0, 15, 15, cv2.BORDER_CONSTANT, value=255)
        per_band = [[] for _ in todo]
        for ws in _words(stack):
            for t in ws:
                mid = t[4] + t[5] / 2
                for k, (s0, s1, y0) in enumerate(offsets):
                    if s0 - 10 <= mid <= s1 + 10:
                        per_band[k].append((t[0], t[1], t[2] - 15, t[3], t[4] - s0 + y0, t[5]))
                        break
        reads.append(per_band)
    replace, added = set(), []
    for k, (y0, y1, _, _) in enumerate(todo):
        got = max((r[k] for r in reads), key=lambda g: sum(1 for t in g if real(t)))
        if got and any(real(t) for t in got):
            added.append(got)
            # the garbage Tesseract read there, if any
            replace.update(i for i, ws in enumerate(lines) if not good(ws) and overlap(*span(ws), y0, y1))
    if not added:
        return lines
    merged = [ws for i, ws in enumerate(lines) if i not in replace] + added
    merged.sort(key=lambda ws: min(t[4] for t in ws))
    return merged


def _pct(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, max(0, int(q * len(xs))))] if xs else None


_PARA_NUMBER = re.compile(r"^\(?(?:\d{1,3}|[ivxlc]{1,5}|[a-h])[\.\)]\s")


def _is_heading(line: str) -> bool:
    letters = re.sub(r"[^A-Za-z]", "", line)
    return 3 <= len(letters) and letters.isupper() and len(line.split()) <= 3 and not line.rstrip().endswith(":")


def _paragraphs(lines: list) -> str:
    """Join OCR lines into text with a blank line between paragraphs.

    The section parser splits judgments into paragraphs at blank lines; joining
    every OCR line with a single newline made each page one "paragraph" (median
    7 per judgment against 27 for typed ones), and the parser's header section
    swallowed most of the judgment. A paragraph starts where the gap above a line
    is over twice the page's usual line spacing, where the line opens with a
    paragraph number ("2.", "(iii)", "b)"), and around a heading line.

    Tuned against the paragraph breaks of 30 typed judgments OCR'd from images
    (8,924 lines): indentation and "the line above ended short" were also tried
    and dropped, as they fired mostly where the typed text has no break
    (precision 0.13 and 0.33).
    """
    if not lines:
        return ""
    gaps = sorted(b[1] - a[2] for a, b in zip(lines, lines[1:]) if b[1] - a[2] > 0)
    usual_gap = gaps[len(gaps) // 2] if gaps else 0
    out = [lines[0][0]]
    for prev, cur in zip(lines, lines[1:]):
        text, top = cur[0], cur[1]
        new = top - prev[2] > 2.0 * usual_gap + 4
        new = new or bool(_PARA_NUMBER.match(text))
        # "JUDGMENT" / "ORDER" / "SHORT ORDER" stand alone: the parser finds the
        # start of the narrative by a paragraph that is exactly that word.
        new = new or _is_heading(text) or _is_heading(prev[0])
        # ...but a label ("PRESENT:", "For the Appellant(s):") stays with what
        # follows, as in typed text: a paragraph opening "Mr. Justice ..." is
        # what the parser takes for the judge beginning the judgment.
        if prev[0].rstrip().endswith(":"):
            new = False
        out.append(("\n\n" if new else "\n") + text)
    return "".join(out)


def filter_noise(lines) -> tuple[str, dict]:
    """Join the words back into lines and paragraphs, dropping scanner noise. Returns (text, stats)."""
    out, left, right, stats = _clean_lines(lines)
    return _paragraphs(out), stats


def _clean_lines(lines):
    """Kept lines as (text, top, bottom, x0, x1), the text column's left/right edge, and stats."""
    lex = lexicon()

    def letters(w):
        return re.sub(r"[^a-z]", "", w.lower())

    def known(w):
        a = letters(w)
        return (len(a) >= 2 and a in lex) or bool(re.search(r"\d{2,}", w))

    body = [ws for ws in lines if sum(1 for w, *_ in ws if known(w)) >= 4]
    left = _pct([ws[0][2] for ws in body], 0.05)
    right = _pct([ws[-1][2] + ws[-1][3] for ws in body], 0.95)
    out, kept_conf, dropped = [], [], 0
    for ws in lines:
        conf = sum(c for _, c, *_ in ws) / len(ws)
        if conf < 45 and sum(1 for w, *_ in ws if known(w)) / len(ws) < 0.35:
            dropped += len(ws)          # a line of low-confidence non-words: stamp, handwriting, border
            continue
        keep, boxes = [], []
        for w, c, x, wd, top, ht in ws:
            a = letters(w)
            if not _ALNUM.search(w) and c < 50:
                dropped += 1            # stray punctuation / specks
                continue
            if c < 25 and len(a) <= 2 and not re.search(r"\d", w) and a not in lex:
                dropped += 1
                continue
            if left is not None and (x + wd < left - 15 or x > right + 15) and not known(w) and (c < 85 or len(a) <= 3):
                dropped += 1            # outside the text column: margin marks
                continue
            keep.append(w)
            boxes.append((x, wd, top, ht))
            kept_conf.append(c)
        if keep:
            out.append((" ".join(keep), min(b[2] for b in boxes), max(b[2] + b[3] for b in boxes),
                        boxes[0][0], boxes[-1][0] + boxes[-1][1]))
    text = " ".join(o[0] for o in out)
    toks = [letters(t) for t in re.findall(r"[A-Za-z]+", text)]
    toks = [t for t in toks if len(t) >= 2]
    stats = {
        "words": len(kept_conf),
        "dropped": dropped,
        "mean_conf": round(sum(kept_conf) / len(kept_conf), 1) if kept_conf else 0.0,
        "vocab_rate": round(sum(1 for t in toks if t in lex) / len(toks), 3) if toks and lex else None,
    }
    return out, left, right, stats


def _valid_dm(d, m):
    return 1 <= int(d) <= 31 and 1 <= int(m) <= 12


def _fix_date3(m):
    a, y = m.group(1), m.group(2)
    ok = [(a[:k], a[k:]) for k in (1, 2) if _valid_dm(a[:k], a[k:])]
    return f"{ok[0][0]}.{ok[0][1]}.{y}" if len(ok) == 1 else m.group(0)


def fix_patterns(t: str) -> str:
    """Fixes that cannot be wrong in this corpus (anything ambiguous is left alone)."""
    # 7.122017 -> 7.12.2017: the dot before the year was lost
    t = re.sub(r"\b(\d{1,2})\.(\d{1,2})((?:19|20)\d\d)\b",
               lambda m: f"{m.group(1)}.{m.group(2)}.{m.group(3)}" if _valid_dm(m.group(1), m.group(2)) else m.group(0), t)
    # 712.2017 -> 7.12.2017, only when just one split is a valid day.month
    t = re.sub(r"(?<![\d.])(\d{3})\.((?:19|20)\d\d)\b", _fix_date3, t)
    # 933-1/2013 -> 933-L/2013: Lahore registry letter read as 1
    t = re.sub(r"\b(\d+)-1/(\d{2,4})\b", r"\1-L/\2", t)
    # No0.123 -> No.123
    t = re.sub(r"\b(Nos?)0\.(?=\s?\d)", r"\1.", t)
    return t


def _skew_angle(gray: np.ndarray, limit: float = 15.0) -> float:
    """The page's tilt in degrees (counter-clockwise positive), 0.0 if it is straight.

    Text lines are sharpest, as peaks in the row-by-row ink profile, when the
    page is level: the angle that maximises the profile's variance is the
    correction. Coarse search over +-15 degrees, then refined to 0.1 degree, on
    a quarter-size image (a few hundredths of a second a page)."""
    f = 600.0 / gray.shape[1]
    small = cv2.resize(gray, None, fx=f, fy=f, interpolation=cv2.INTER_AREA)
    _, b = cv2.threshold(small, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    h, w = b.shape

    def score(a):
        m = cv2.getRotationMatrix2D((w / 2, h / 2), float(a), 1.0)
        r = cv2.warpAffine(b, m, (w, h), flags=cv2.INTER_NEAREST, borderValue=0)
        return float(r.sum(axis=1, dtype=np.float64).var())

    level = score(0.0)
    best = max(np.arange(-limit, limit + 1e-9, 0.5), key=score)
    best = max(np.arange(best - 0.5, best + 0.5 + 1e-9, 0.1), key=score)
    # no line structure to go by (a photo, a near-empty page): leave it alone
    return float(round(best, 1)) if score(best) > 1.02 * level else 0.0


def deskew(gray: np.ndarray) -> tuple[np.ndarray, float]:
    """Rotate a tilted page level. Returns (image, angle corrected); tilts under 0.3 degree are left."""
    angle = _skew_angle(gray)
    if abs(angle) < 0.3:
        return gray, 0.0
    h, w = gray.shape
    m = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    cos, sin = abs(m[0, 0]), abs(m[0, 1])
    nw, nh = int(h * sin + w * cos), int(h * cos + w * sin)   # grow the canvas so no corner is cut off
    m[0, 2] += nw / 2 - w / 2
    m[1, 2] += nh / 2 - h / 2
    return cv2.warpAffine(gray, m, (nw, nh), flags=cv2.INTER_CUBIC, borderValue=255), angle


def _read(gray: np.ndarray) -> tuple[str, dict, np.ndarray]:
    level, angle = deskew(gray)
    img = clean(level)
    text, stats = filter_noise(_recover_lines(img, _words(img)))
    if angle:
        stats["deskewed"] = angle
    return text, stats, img


def ocr_gray(gray: np.ndarray) -> tuple[str, dict]:
    """OCR one grayscale page image: straightened if tilted, and turned the right way
    up if it was scanned sideways or upside down."""
    text, stats, img = _read(gray)
    _, binv = cv2.threshold(img, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    inked = ((binv > 0).sum(axis=1) > 0.01 * img.shape[1]).mean() > 0.25   # a page of text, not a signature page
    # Garbage read from a sideways page can still be mostly short dictionary words
    # (85% in the self-check), so Tesseract's own confidence counts too.
    reads_badly = inked and (stats["words"] < 20 or stats["mean_conf"] < 60
                             or (stats["vocab_rate"] is not None and stats["vocab_rate"] < 0.6))
    if reads_badly:
        # Physically scanned sideways or upside down: keep whichever orientation reads best.
        for rot in (cv2.ROTATE_90_COUNTERCLOCKWISE, cv2.ROTATE_90_CLOCKWISE, cv2.ROTATE_180):
            t2, s2, _ = _read(cv2.rotate(gray, rot))
            better = (s2["mean_conf"] >= stats["mean_conf"] + 15
                      or (s2["vocab_rate"] or 0) >= (stats["vocab_rate"] or 0) + 0.2)
            if s2["words"] >= 20 and (s2["vocab_rate"] or 0) >= 0.8 and better:
                text, stats = t2, dict(s2, rotated=True)
                break
    return fix_patterns(text), stats


_PAGE_CACHE: "OrderedDict[tuple, tuple[str, dict]]" = OrderedDict()
_PAGE_CACHE_LOCK = threading.Lock()


def ocr_page(page: fitz.Page) -> tuple[str, dict]:
    """OCR one page. Results are cached per file and page in this process: the
    validator OCRs page 1 (and sometimes 2) of an upload, and extraction would
    otherwise OCR the same pages again moments later."""
    key = None
    path = page.parent.name
    if path and os.path.exists(path):
        st = os.stat(path)
        key = (os.path.abspath(path), st.st_size, st.st_mtime_ns, page.number)
        with _PAGE_CACHE_LOCK:
            if key in _PAGE_CACHE:
                _PAGE_CACHE.move_to_end(key)
                return _PAGE_CACHE[key]
    result = ocr_gray(render_gray(page))
    if key:
        with _PAGE_CACHE_LOCK:
            _PAGE_CACHE[key] = result
            while len(_PAGE_CACHE) > 16:
                _PAGE_CACHE.popitem(last=False)
    return result


# ── whole document ──────────────────────────────────────────────────────────

def page_workers() -> int:
    """Pages OCR'd in parallel within one document (Tesseract runs as a subprocess, so threads suffice).
    OCR_PAGE_WORKERS overrides; bulk ingest sets it to 1 because it already runs one process per core."""
    env = os.environ.get("OCR_PAGE_WORKERS")
    if env and env.isdigit():
        return max(1, int(env))
    return max(1, min(4, (os.cpu_count() or 2) // 2))


def page_is_scan(page: fitz.Page) -> bool:
    """True if the page is a scanned image: one picture covering most of it. Its text
    layer, if any, was made by the scanner's own OCR."""
    area = page.rect.width * page.rect.height
    try:
        covered = max((r.width * r.height for img in page.get_images(full=True)
                       for r in page.get_image_rects(img[0])), default=0.0)
    except Exception:  # noqa: BLE001
        return False
    return area > 0 and covered / area >= 0.85


def extract_pages(pdf_path: str, pdf_id: str = "") -> tuple[list[str], dict]:
    """Text of every page of a scanned judgment: OCR for page images, the text layer
    for pages that are typed (so a scan with a few typed pages, or a typed file with
    scanned annexures, both work).

    A page image is OCR'd even when it carries a text layer: that layer is the
    scanner's own OCR, unstraightened and often garbled ("INIJIF SupIZEME COURT
    Or'"), which is why such judgments were refused as not being judgments."""
    os.environ.setdefault("OMP_THREAD_LIMIT", "1")  # one Tesseract thread per page; pages run in parallel
    with fitz.open(pdf_path) as doc:
        n = len(doc)
        layer = [doc[i].get_text("text") or "" for i in range(n)]
        scans = [page_is_scan(doc[i]) for i in range(n)]
    todo = [i for i in range(n) if scans[i] or len(layer[i].strip()) < TEXT_LAYER_MIN_CHARS]

    def work(i):
        with fitz.open(pdf_path) as d:      # fitz documents are not shared across threads
            return i, ocr_page(d[i])

    texts, per_page = list(layer), {}
    if todo:
        with ThreadPoolExecutor(max_workers=min(page_workers(), len(todo))) as ex:
            for i, (t, s) in ex.map(work, todo):
                texts[i], per_page[i + 1] = t, s
    conf = [s["mean_conf"] for s in per_page.values() if s["words"]]
    vocab = [s["vocab_rate"] for s in per_page.values() if s["vocab_rate"] is not None]
    summary = {
        "pages": n,
        "ocr_pages": len(todo),
        "mean_conf": round(sum(conf) / len(conf), 1) if conf else None,
        "vocab_rate": round(sum(vocab) / len(vocab), 3) if vocab else None,
        "low_quality_pages": sorted(p for p, s in per_page.items() if (s["vocab_rate"] or 0) < 0.85 or s["words"] < 20),
        "rotated_pages": sorted(p for p, s in per_page.items() if s.get("rotated")),
        "deskewed_pages": {str(p): s["deskewed"] for p, s in sorted(per_page.items()) if s.get("deskewed")},
    }
    if todo:
        logger.info(f"[{pdf_id}] OCR: {len(todo)}/{n} pages, mean confidence {summary['mean_conf']}, "
                    f"vocabulary rate {summary['vocab_rate']}, low-quality pages {summary['low_quality_pages'] or 'none'}")
    return texts, summary
