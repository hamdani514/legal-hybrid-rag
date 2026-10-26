"""
Self-check for OCR of scanned judgments (app.ingestion.ocr).

    cd backend && venv/Scripts/python.exe -m app.ingestion.ocr_selfcheck

No database, network or Gemini quota is touched. It needs Tesseract installed;
backend/tessdata/eng.traineddata (tessdata_best) is used when present.

* The pattern fixes repair what they should and leave ambiguous numbers alone.
* clean() keeps a bold, underlined heading at the top of the page. An earlier
  version treated any ink-heavy row near the edge as a scanner border and
  wiped the court heading from 19 of the 260 scanned judgments.
* A typed page renders to an image, the image is made to look photocopied, and
  OCR of it matches the page's own text layer.
* extract_pages() keeps a typed page's text layer and OCRs only image pages, so
  a scan with typed pages (or the reverse) is handled page by page.
* A scanned page stored mirrored-and-flipped, with the PDF transform undoing
  it, is read the right way round (rendering applies the transform).
* A page scanned at a tilt (3 and -6 degrees) is straightened and read; one
  scanned sideways is turned upright.
* A scan carrying a garbled text layer (the scanner's own OCR) is detected as
  scanned, passes validation, and is OCR'd rather than read from that layer.
"""

import difflib
import os
import re
import tempfile

import cv2
import fitz
import numpy as np

from app.ingestion import ocr

FAIL: list = []


def check(cond: bool, msg: str) -> None:
    print(("ok   " if cond else "FAIL ") + msg)
    if not cond:
        FAIL.append(msg)


def words(t: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", t.lower())


def word_match(truth: str, got: str) -> float:
    g, h = words(truth), words(got)
    sm = difflib.SequenceMatcher(None, g, h, autojunk=False)
    return sum(b.size for b in sm.get_matching_blocks()) / max(len(g), 1)


SAMPLE = """IN THE SUPREME COURT OF PAKISTAN
(Appellate Jurisdiction)
PRESENT: Mr. Justice Umar Ata Bandial
Civil Appeal No.1009 of 2010
(On appeal from the judgment dated 11.10.2010 passed by the Lahore High Court)
Yar Muhammad and another ... Appellants
Versus
Mst. Sameena Tayab and others ... Respondents
Date of Hearing: 07.12.2017
JUDGMENT
Through the listed appeals, the appellants have questioned the same judgment
of the Lahore High Court whereby the writ petition filed by the respondent
was allowed and the order of the Member (Colonies), Board of Revenue, Punjab
was set aside. Since common questions of law and facts are involved, both the
appeals will be decided through this single judgment under Section 4 of the
Colonization of Government Lands Act, 1912."""


def typed_page(doc: fitz.Document, heading_bold=True) -> fitz.Page:
    page = doc.new_page(width=612, height=1008)
    y = 60
    for i, line in enumerate(SAMPLE.splitlines()):
        font = "tibo" if (i == 0 and heading_bold) else "tiro"
        size = 14 if i == 0 else 12
        x = 150 if i == 0 else 60
        page.insert_text((x, y), line, fontname=font, fontsize=size)
        if i == 0:
            page.draw_line((x, y + 3), (x + 290, y + 3), width=1.2)  # underlined heading
        y += 26
    return page


def photocopy(gray: np.ndarray, seed=1) -> np.ndarray:
    rng = np.random.default_rng(seed)
    a = gray.astype(np.float32) * 0.92 + 14
    a[:, :60] *= np.linspace(0.3, 1, 60)[None, :]          # binding shadow
    a += rng.normal(0, 8, a.shape)
    a = cv2.GaussianBlur(np.clip(a, 0, 255).astype(np.uint8), (3, 3), 0.7)
    m = cv2.getRotationMatrix2D((a.shape[1] / 2, a.shape[0] / 2), 0.6, 1.0)
    return cv2.warpAffine(a, m, (a.shape[1], a.shape[0]), borderValue=235)


def main() -> None:
    # 1. pattern fixes
    cases = {
        "Date of Hearing: 7.122017": "Date of Hearing: 7.12.2017",
        "dated 712.2017": "dated 7.12.2017",
        "Nos.1009/2010 and 933-1/2013": "Nos.1009/2010 and 933-L/2013",
        "Petition No0.2697-L/2016": "Petition No.2697-L/2016",
        "paid 312.2019": "paid 312.2019",            # 3.12 or 31.2: ambiguous, untouched
        "Section 3.1 of 1990": "Section 3.1 of 1990",
        "Rs.1.152019": "Rs.1.152019",                 # month 15 is not a date
    }
    for src, want in cases.items():
        check(ocr.fix_patterns(src) == want, f"fix_patterns({src!r}) -> {ocr.fix_patterns(src)!r}")

    # 2-3. a typed page, rendered, photocopied, OCR'd
    doc = fitz.open()
    page = typed_page(doc)
    gray = ocr.render_gray(page)
    cleaned = ocr.clean(gray)
    top = cleaned[: gray.shape[0] // 8]
    check((top < 128).sum() > 0.5 * (gray[: gray.shape[0] // 8] < 128).sum(),
          "clean() keeps the bold underlined heading at the top of the page")
    text, stats = ocr.ocr_gray(photocopy(gray))
    wm = word_match(page.get_text(), text)
    check(wm >= 0.95, f"OCR of a photocopied typed page matches its text layer ({wm:.1%} of words)")
    check("SUPREME" in text and "PAKISTAN" in text, "court heading read")
    check("07.12.2017" in text and "1009" in text, "date and case number read")
    check(stats["vocab_rate"] is None or stats["vocab_rate"] >= 0.9, f"vocabulary rate {stats['vocab_rate']}")

    # 4. mixed document: typed page kept, image page OCR'd
    # 5. an image stored mirrored and upside down, placed with a transform that undoes it
    tmp = tempfile.mkdtemp()
    img_path = os.path.join(tmp, "page.png")
    flipped = cv2.flip(photocopy(gray), -1)                 # rotated 180 degrees in storage
    cv2.imwrite(img_path, flipped)
    mixed = fitz.open()
    typed_page(mixed)
    p2 = mixed.new_page(width=612, height=1008)
    p2.insert_image(p2.rect, filename=img_path, rotate=180)  # the PDF turns it back upright
    pdf = os.path.join(tmp, "mixed.pdf")
    mixed.save(pdf)
    pages, summary = ocr.extract_pages(pdf, "selfcheck")
    check(summary["pages"] == 2 and summary["ocr_pages"] == 1, f"only the image page OCR'd ({summary})")
    check(pages[0].strip() == mixed[0].get_text().strip(), "typed page kept its text layer")
    wm2 = word_match(mixed[0].get_text(), pages[1])
    check(wm2 >= 0.95, f"image page stored upside down read upright ({wm2:.1%} of words)")

    # 6. tilted and sideways scans
    for tilt in (3.0, -6.0):
        h, w = gray.shape
        m = cv2.getRotationMatrix2D((w / 2, h / 2), tilt, 1.0)
        tilted = cv2.warpAffine(photocopy(gray, seed=2), m, (w, h), borderValue=235)
        text, st = ocr.ocr_gray(tilted)
        wm = word_match(page.get_text(), text)
        want = -(tilt + 0.6)               # photocopy() itself adds a 0.6 degree tilt
        check(wm >= 0.95 and abs(st.get("deskewed", 0) - want) <= 0.3,
              f"page tilted {tilt:+.0f} deg straightened by {st.get('deskewed')} (expected {want:+.1f}) and read ({wm:.1%} of words)")
    text, st = ocr.ocr_gray(cv2.rotate(photocopy(gray, seed=3), cv2.ROTATE_90_CLOCKWISE))
    wm = word_match(page.get_text(), text)
    check(wm >= 0.95 and st.get("rotated"), f"page scanned sideways turned upright and read ({wm:.1%} of words)")

    # 7. a scan whose text layer is the scanner's garbled OCR
    from app.ingestion.detector import detect_pdf_type
    from app.ingestion.validator import validate_judgment
    cv2.imwrite(os.path.join(tmp, "upright.png"), photocopy(gray, seed=4))
    junk = fitz.open()
    for _ in range(2):
        jp = junk.new_page(width=612, height=1008)
        jp.insert_image(jp.rect, filename=os.path.join(tmp, "upright.png"))
        # invisible text, as a scanner's OCR layer is
        jp.insert_text((60, 60), "INIJIF SupIZEME COURT Or' (Appellate Juris lction) " * 3, fontsize=4, render_mode=3)
    jpath = os.path.join(tmp, "junk_layer.pdf")
    junk.save(jpath)
    check(ocr.page_is_scan(junk[0]), "full-page image recognised as a scan")
    check(detect_pdf_type(jpath) == "scanned", "scan with a garbled text layer detected as scanned")
    check(validate_judgment(jpath)[0], "scan with a garbled text layer passes validation (OCR'd)")
    jpages, js = ocr.extract_pages(jpath, "selfcheck-junk")
    check(js["ocr_pages"] == 2 and "SUPREME COURT OF PAKISTAN" in jpages[0], "its pages are OCR'd, not read from the layer")

    print()
    print("ALL OK" if not FAIL else f"{len(FAIL)} FAILED")
    raise SystemExit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
