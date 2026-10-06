"""
Deterministic case metadata for one judgment — the non-LLM half of a CaseCard.

Why this exists
---------------
Exact-match retrieval, the compare table and the contextual chunk headers all
need the facts a lawyer reads off the first page of a judgment: the case number,
the bench, the parties, the court below, the dates, the counsel, plus what the
judgment cites and how it ends. Supreme Court captions are highly regular, so
regular expressions get these right and cost nothing; an LLM would only add
cost, latency and the chance of a hallucinated case number.

Where the caption comes from (learned from a real failure)
----------------------------------------------------------
The ingestion classifier sometimes cuts HEADER_CORAM short. In
fa86ba1f-… (judgement_C_A_6_2016.pdf) it ends after the first judge, and the
second judge, the case number, the parties and the counsel all spilled into the
FACTS node. So the primary source for caption fields is the head of the raw
extracted text, backend/uploads/{pdf_id}.txt, up to the "JUDGMENT"/"ORDER"
heading; HEADER_CORAM + the start of FACTS is only the fallback when the file
is missing.

Normalisers are shared contracts, never re-implemented here
-----------------------------------------------------------
Case numbers go through app.retrieval.case_keys.parse_case_numbers and statutes
through app.retrieval.statutes.parse_statutes, so the query side produces the
same strings. The only thing borrowed beyond the public API is case_keys'
compiled `_CASE_RE`, used purely to find WHERE a case number sits in the caption
(so the lower-court reference that follows it can be told apart); the key
itself always comes from parse_case_numbers.

Rules that must be re-validated on a 100-judgment sample once the full corpus is
ingested are marked "REVALIDATE" below.

Run:
    python -m app.ingestion.metadata_extractor --all --report   # coverage table, writes nothing
    python -m app.ingestion.metadata_extractor --show <judgment_id>
"""

import argparse
import asyncio
import json
import os
import re
from datetime import datetime

from loguru import logger

from app.retrieval.case_keys import _CASE_RE, parse_case_numbers
from app.retrieval.statutes import parse_statutes

METADATA_VERSION = 1

UPLOADS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "uploads")

# How much of the raw text can hold the caption. The heading "JUDGMENT"/"ORDER"
# normally ends it well before this; multi-case captions (13 appellants, one per
# line) run past 2,500 characters, so the hard cap is generous.
CAPTION_MAX_CHARS = 6000
CAPTION_FALLBACK_CHARS = 2500

# ── Text normalisation ───────────────────────────────────────────────────────

_PAGE_MARK = re.compile(r"-{2,}\s*PAGE\s+\d+\s*-{2,}", re.IGNORECASE)
# PDF extraction renders the caption's ellipses/dashes as U+FFFD or U+2026.
_JUNK = re.compile(r"[�…“”‘’]")


def _clean(text: str) -> str:
    """Strip page markers and extraction junk, keep line structure."""
    text = _PAGE_MARK.sub("\n", text or "")
    text = _JUNK.sub(" ", text)
    text = text.replace("\r", "")
    return "\n".join(line.strip() for line in text.split("\n"))


def _flat(text: str) -> str:
    """Collapse all whitespace to single spaces."""
    return re.sub(r"\s+", " ", text or "").strip()


# ── Source loading ───────────────────────────────────────────────────────────

def _read_raw(judgment_id: str) -> str | None:
    path = os.path.join(UPLOADS_DIR, f"{judgment_id}.txt")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8", errors="ignore") as fh:
        return fh.read()


async def load_sources(judgment_id: str) -> dict:
    """Raw text (or None) and the judgment's nodes keyed by section_type."""
    from app.database import connect_db, db

    if not db.is_connected:
        await connect_db()
    sections: dict[str, str] = {}
    filename = ""
    if db.is_connected:
        async for node in db.nodes.find({"pdf_id": judgment_id}, {"section_type": 1, "text": 1}):
            st = (node.get("section_type") or "").upper()
            if st:
                sections[st] = node.get("text") or ""
        doc = await db.documents.find_one({"pdf_id": judgment_id}, {"filename": 1})
        filename = (doc or {}).get("filename", "")
    return {"raw": _read_raw(judgment_id), "sections": sections, "filename": filename}


_HEADING_RE = re.compile(r"^(?:JUDGMENT|JUDGEMENT|ORDER|SHORT ORDER)\s*$", re.MULTILINE)


def caption_text(raw: str | None, sections: dict[str, str]) -> tuple[str, str]:
    """The caption block and where it came from ("raw" or "nodes")."""
    if raw:
        text = _clean(raw)[:CAPTION_MAX_CHARS]
        present = re.search(r"\bPRESENT\b", text, re.IGNORECASE)
        start = present.end() if present else 0
        heading = _HEADING_RE.search(text, start)
        end = heading.start() if heading else CAPTION_FALLBACK_CHARS
        return text[:end], "raw"
    # Fallback: the classifier may have cut the header short, so FACTS' start too.
    text = _clean((sections.get("HEADER_CORAM") or "") + "\n" + (sections.get("FACTS") or "")[:2000])
    heading = _HEADING_RE.search(text)
    return (text[: heading.start()] if heading else text[:CAPTION_FALLBACK_CHARS]), "nodes"


# ── Bench ────────────────────────────────────────────────────────────────────

_JUSTICE_RE = re.compile(r"\b(?:MR|MRS|MS|MISS)\.?\s+JUSTICE\s+", re.IGNORECASE)
_CJ_RE = re.compile(r",?\s*\b(HCJ|ACJ|CJ)\b\.?\s*$", re.IGNORECASE)


def _name_case(name: str) -> str:
    """"SH. AZMAT SAEED" -> "Sh. Azmat Saeed"; mixed-case names kept as written."""
    if name.isupper():
        return " ".join(w.capitalize() if not re.fullmatch(r"[A-Z]\.?", w) else w for w in name.split())
    return name


def extract_bench(caption: str) -> list[str]:
    present = re.search(r"\bPRESENT\s*:?", caption, re.IGNORECASE)
    if not present:
        return []
    block = caption[present.end():]
    case = _CASE_RE.search(block)
    block = block[: case.start()] if case else block[:600]
    block = _flat(block)
    parts = _JUSTICE_RE.split(block)[1:]
    bench = []
    for part in parts:
        part = part.strip(" ,;")
        marker = _CJ_RE.search(part)
        name = _CJ_RE.sub("", part).strip(" ,;")
        if not name or len(name) > 60:
            continue
        label = f"Justice {_name_case(name)}"
        if marker:
            label += f", {marker.group(1).upper()}"
        bench.append(label)
    return bench


# ── Lower-court reference spans ──────────────────────────────────────────────
# "(On appeal against the judgment dated … passed by X in Y)", "[Against
# judgment dated …]", or unbracketed "Against the judgment dated …" running to
# the next blank line. Nested parentheses ("Appeal No.842(R)CS") are common, so
# bracketed spans are found by depth-counting rather than by [^)]*.
# REVALIDATE: the unbracketed form and its blank-line terminator.

_LOWER_START = re.compile(r"[(\[]\s*(?:on\s+appeal|against|appeal\s+against)\b|(?<![A-Za-z])against\s+the\s+(?:judgment|order)", re.IGNORECASE)


def lower_court_spans(text: str) -> list[tuple[int, int]]:
    spans = []
    pos = 0
    while True:
        m = _LOWER_START.search(text, pos)
        if not m:
            break
        start = m.start()
        if text[start] in "([":
            open_c, close_c = text[start], ")" if text[start] == "(" else "]"
            depth, i = 0, start
            while i < len(text):
                if text[i] == open_c:
                    depth += 1
                elif text[i] == close_c:
                    depth -= 1
                    if depth == 0:
                        break
                i += 1
            end = min(i + 1, len(text))
        else:
            blank = re.search(r"\n\s*\n", text[start:])
            end = start + blank.start() if blank else len(text)
        spans.append((start, end))
        pos = end
    return spans


_DATE = r"\d{1,2}\s*[./-]\s*\d{1,2}\s*[./-]\s*\d{2,4}"
_LOWER_COURT_RE = re.compile(
    rf"(?:passed\s+by|(?:judgment|order)s?(?:/order)?\s+of|dated\s+{_DATE}\s+(?:of|by))\s+(?:the\s+)?(?:learned\s+)?"
    r"([A-Z][^\n]*?)(?=\s+(?:in|dated|passed|vide|whereby)\b|$)"
)


def _norm_date(value: str) -> str:
    d, m, y = re.split(r"\s*[./-]\s*", value.strip())
    if len(y) == 2:
        y = ("20" if int(y) < 50 else "19") + y
    return f"{int(d):02d}.{int(m):02d}.{y}"


def extract_lower_court(caption: str) -> tuple[str, str]:
    for start, end in lower_court_spans(caption):
        span = _flat(caption[start:end]).strip("()[] ")
        date = re.search(rf"dated\s+({_DATE})", span)
        court = _LOWER_COURT_RE.search(span)
        lower = court.group(1).strip(" ,.;") if court else ""
        lower = re.sub(r"\s*\bdated\b.*$", "", lower)
        return lower, (_norm_date(date.group(1)) if date else "")
    return "", ""


# ── Parties ──────────────────────────────────────────────────────────────────
# The role label sits on its own line after an ellipsis that extraction turned
# into junk: "� Appellant", "...Appellant(s)", "…Appellant(s)/Petitioner(s)".
# Matching a WHOLE line keeps "respondent No. 2" inside a party line from
# being mistaken for the label.

_ROLE_LINE = r"^[\s.\-–—:]*(?:{0})s?\s*(?:\(\s*s\s*\))?(?:\s*/\s*(?:{1})s?\s*(?:\(\s*s\s*\))?)?[\s.]*$"
_APP_LINE = re.compile(_ROLE_LINE.format("appellant|petitioner", "appellant|petitioner"), re.IGNORECASE | re.MULTILINE)
_RESP_LINE = re.compile(_ROLE_LINE.format("respondent", "respondent"), re.IGNORECASE | re.MULTILINE)
_VERSUS_LINE = re.compile(r"^\s*(?:versus|vs\.?|v\.)\s*$", re.IGNORECASE | re.MULTILINE)
_COUNSEL_START = re.compile(r"^\s*(?:For\b|On\s+Court|Respondent\s*(?:No|\()|Other\s+Respondent)", re.IGNORECASE | re.MULTILINE)

_ANNOTATION = re.compile(r"\((?:in|for)\s[^)]*\)", re.IGNORECASE)
_INLINE_ANNOTATION = re.compile(r"\s(?:In|in)\s+(?:C|Crl|H|Const)\.?[A-Za-z.]*\s*\d.*$")
_OTHERS = re.compile(r"\b(?:and|&)\s+(?:others|another)\b|\betc\.", re.IGNORECASE)


def _first_party(block: str) -> str:
    """The lead party of a party block, without "(In CA …)" annotations."""
    lines = [l for l in block.split("\n") if l.strip()]
    # Numbered multi-case lists: "1." / "Pakistan Medical … " / "In C.As.3 & 4/2018" / "2." …
    if lines and re.fullmatch(r"\d+\.?", lines[0].strip()):
        item = []
        for line in lines[1:]:
            if re.fullmatch(r"\d+\.?", line.strip()):
                break
            item.append(line)
        lines = item
    text = _flat(" ".join(lines))
    ann = _ANNOTATION.search(text)
    if ann:
        text = text[: ann.start()]
    text = _INLINE_ANNOTATION.sub("", text)
    others = _OTHERS.search(text)
    if others:
        text = text[: others.end()]
    return text.strip(" ,;:-")


def extract_parties(caption: str) -> tuple[str, str]:
    app = _APP_LINE.search(caption)
    versus = _VERSUS_LINE.search(caption)
    resp = _RESP_LINE.search(caption, versus.end() if versus else 0)

    appellant = respondent = ""
    app_end = app.start() if app else (versus.start() if versus else None)
    if app_end is not None:
        # The party block starts after the last case number or lower-court span.
        boundary = 0
        for m in _CASE_RE.finditer(caption[:app_end]):
            # "(In CA 42-K/2016)" annotations sit inside the party block.
            if re.search(r"\(\s*in\s*$", caption[max(0, m.start() - 6):m.start()], re.IGNORECASE):
                continue
            boundary = max(boundary, m.end())
        for start, end in lower_court_spans(caption[:app_end]):
            boundary = max(boundary, end)
        block = caption[boundary:app_end]
        # Stray lines between the case number and the parties, e.g.
        # "CMAs.7436 & 3498/2021 IN CPLAs No.NILL/2021 (Permission to file and argue)".
        block = re.sub(r"^.*\bIN\s+CPLAs?\b.*$|^\s*\((?:Permission|Application)[^)]*\)\s*$", "", block,
                       flags=re.IGNORECASE | re.MULTILINE)
        appellant = _first_party(block)

    if versus:
        resp_end = resp.start() if resp else None
        if resp_end is None:
            counsel = _COUNSEL_START.search(caption, versus.end())
            resp_end = counsel.start() if counsel else min(len(caption), versus.end() + 300)
        respondent = _first_party(caption[versus.end():resp_end])
    return appellant, respondent


# ── Counsel ──────────────────────────────────────────────────────────────────

_HONORIFIC = re.compile(
    r"^(?:Mr|Mrs|Ms|Miss|Syed|Hafiz|Raja|Sardar|Ch|Barrister|Dr|Sh|Mian|Malik|Rana|Khawaja|Sahibzada|Pir)\.?\s+\S",
)
_NO_COUNSEL = re.compile(r"^(?:ex-?parte|nemo|in\s*person|n\.?\s*r\.?)\.?$", re.IGNORECASE)


def extract_counsel(caption: str) -> list[str]:
    """ "Mr. Kamran Murtaza, Sr. ASC (for the Appellant)" — best effort."""
    start = _COUNSEL_START.search(caption)
    if not start:
        return []
    block = caption[start.start():]
    stop = re.search(r"^\s*Date\s+of\s+(?:hearing|decision)", block, re.IGNORECASE | re.MULTILINE)
    block = block[: stop.start()] if stop else block

    counsel: list[str] = []
    role = ""
    current: list[str] = []

    def flush() -> None:
        if current:
            name = _flat(re.sub(r"\([^)]*\)", "", " ".join(current))).strip(" ,;:")
            if name and not _NO_COUNSEL.match(name) and len(name) > 3:
                counsel.append(f"{name} ({role})" if role else name)
        current.clear()

    for line in block.split("\n"):
        line = line.strip()
        if not line:
            continue
        role_m = re.match(r"^((?:For\b|On\s+Court|Respondent\s*(?:No|\()|Other\s+Respondent)[^:]*?)\s*:?\s*$", line, re.IGNORECASE) \
            or re.match(r"^((?:For\b|On\s+Court|Respondent\s*(?:No|\()|Other\s+Respondent)[^:]*):\s*(.*)$", line, re.IGNORECASE)
        if role_m and (line.lower().startswith(("for", "on court", "respondent", "other")) and
                       (":" in line or len(line) < 60)):
            flush()
            role = _flat(role_m.group(1)).rstrip(" :").lower()
            rest = role_m.group(2) if role_m.lastindex and role_m.lastindex >= 2 else ""
            if rest:
                current.append(rest)
            continue
        line = line.lstrip(": ").strip()
        if not line:
            continue
        if _HONORIFIC.match(line) or _NO_COUNSEL.match(line):
            flush()
        current.append(line)
    flush()
    return counsel


# ── Dates ────────────────────────────────────────────────────────────────────

_MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august",
     "september", "october", "november", "december"], start=1)}
_LONG_DATE = re.compile(
    r"(\d{1,2})\s*(?:st|nd|rd|th)?\s*(?:of\s*)?(" + "|".join(_MONTHS) + r")\s*,?\s*((?:19|20)\d{2})",
    re.IGNORECASE,
)
_SHORT_DATE = re.compile(rf"(?<![\d.])({_DATE})(?![\d])")


def _first_date(text: str) -> str:
    candidates = []
    for m in _SHORT_DATE.finditer(text):
        try:
            candidates.append((m.start(), _norm_date(m.group(1))))
        except ValueError:
            pass
    for m in _LONG_DATE.finditer(text):
        candidates.append((m.start(), f"{int(m.group(1)):02d}.{_MONTHS[m.group(2).lower()]:02d}.{m.group(3)}"))
    candidates = [c for c in candidates if 1 <= int(c[1][:2]) <= 31 and 1 <= int(c[1][3:5]) <= 12]
    return min(candidates)[1] if candidates else ""


def extract_decision_date(caption: str, raw: str | None) -> tuple[str, str]:
    """(date, source). Explicit decision/announcement > signature date > date of hearing.

    REVALIDATE: the signature-block window (last 700 chars) and the city list.
    """
    m = re.search(r"Date\s+of\s+(?:decision|judgment|announcement)\s*:?\s*(.{0,40})", caption, re.IGNORECASE | re.DOTALL)
    if m and _first_date(m.group(1)):
        return _first_date(m.group(1)), "caption_decision"
    if raw:
        tail = _clean(raw)[-700:]
        ann = re.search(r"Announced\b(.{0,80})", tail, re.IGNORECASE | re.DOTALL)
        if ann and _first_date(ann.group(1)):
            return _first_date(ann.group(1)), "announced"
        sig = re.search(r"\b(?:Islamabad|Karachi|Lahore|Peshawar|Quetta)\b[\s,]*(?:the)?(.{0,60})", tail,
                        re.IGNORECASE | re.DOTALL)
        if sig and _first_date(sig.group(1)):
            return _first_date(sig.group(1)), "signature"
    m = re.search(r"Date\s+of\s+hearing\s*:?\s*(.{0,40})", caption, re.IGNORECASE | re.DOTALL)
    if m and _first_date(m.group(1)):
        return _first_date(m.group(1)), "hearing"
    return "", ""


# ── Citations ────────────────────────────────────────────────────────────────
# REVALIDATE: journal list and PLD court names on the full corpus.

_YEAR_FIRST = re.compile(
    r"\b((?:19|20)\d{2})\s+(SCMR|CLC|YLR|MLD|CLD|PTD|SCP|P\.?\s?L\.?\s?C\.?(?:\s*\(\s*C\.?\s*S\.?\s*\))?"
    r"|P\.?\s?Cr\.?\s?\.?L\.?\s?J\.?)\s+(\d{1,5})\b",
)
_PLD = re.compile(
    r"\bPLD\s+((?:19|20)\d{2})\s+(SC(?:\s*\(\s*AJ\s*&\s*K\s*\))?|FSC|Supreme\s+Court|Lahore|Lah\.?|Karachi|Kar\.?"
    r"|Peshawar|Pesh\.?|Quetta|Islamabad|Isl\.?|Sindh|Balochistan|Federal\s+Shariat\s+Court|Journal)\s+(\d{1,5})\b",
    re.IGNORECASE,
)


def _journal(value: str) -> str:
    compact = re.sub(r"[\s.]", "", value).upper()
    if compact.startswith("PCR"):
        return "PCrLJ"
    if compact.startswith("PLC"):
        return "PLC (CS)" if "CS" in compact else "PLC"
    return compact


def extract_citations(text: str) -> list[str]:
    found: list[tuple[int, str]] = []
    seen: set[str] = set()
    flat = _flat(text)
    for m in _YEAR_FIRST.finditer(flat):
        c = f"{m.group(1)} {_journal(m.group(2))} {int(m.group(3))}"
        if c not in seen:
            seen.add(c)
            found.append((m.start(), c))
    for m in _PLD.finditer(flat):
        court = _flat(m.group(2)).rstrip(".")
        court = {"Supreme Court": "SC", "Lah": "Lahore", "Kar": "Karachi", "Pesh": "Peshawar",
                 "Isl": "Islamabad"}.get(court, court)
        c = f"PLD {m.group(1)} {court} {int(m.group(3))}"
        if c not in seen:
            seen.add(c)
            found.append((m.start(), c))
    return [c for _, c in sorted(found)]


# ── Outcome ──────────────────────────────────────────────────────────────────
# FINAL_ORDER is sometimes only the signature block, or a misclassified passage
# (footnotes, a quoted earlier order). Only operative verbs whose subject is the
# appeal/petition itself count; anything conflicting or absent is "unknown".
# REVALIDATE: on criminal judgments ("conviction set aside", "acquitted").

_SUBJ = r"(?:appeals?|petitions?|c\.?\s?as?\.?|c\.?\s?ps?\.?)"
_OUTCOME_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("partly_allowed", re.compile(r"\b(?:partly|partially)\s+(?:allowed|accepted)|allowed\s+(?:in\s+part|partly|partially)", re.I)),
    ("remanded", re.compile(r"\bremand(?:ed)?\b|\bsent\s+back\b|\bremitted\b", re.I)),
    ("allowed", re.compile(rf"\b{_SUBJ}\b[^.;]{{0,60}}?\b(?:allowed|accepted)\b|\ballow(?:ing|ed)?\s+(?:this|the|these|both)\s+{_SUBJ}"
                           r"|leave\s+(?:to\s+appeal\s+)?(?:is\s+)?granted", re.I)),
    ("dismissed", re.compile(rf"\b{_SUBJ}\b[^.;]{{0,60}}?\bdismissed\b|\bdismiss(?:ing|ed)?\s+(?:this|the|these|both)\s+{_SUBJ}"
                             r"|leave\s+(?:to\s+appeal\s+)?(?:is\s+)?refused", re.I)),
    ("disposed", re.compile(r"\bdisposed\s+of\b", re.I)),
]


def _outcome_of(text: str) -> str | None:
    flat = _flat(text)
    hits = {label for label, pat in _OUTCOME_PATTERNS if pat.search(flat)}
    if not hits:
        return None
    for label in ("partly_allowed", "remanded"):
        if label in hits:
            return label
    if "allowed" in hits and "dismissed" in hits:
        logger.debug("outcome: both allowed and dismissed found; returning unknown")
        return "unknown"
    for label in ("allowed", "dismissed", "disposed"):
        if label in hits:
            return label
    return None


def extract_outcome(final_order: str, raw: str | None) -> tuple[str, str]:
    """(outcome, source). FINAL_ORDER first; if it has no operative verb (a
    signature block), the closing paragraph of the raw text."""
    got = _outcome_of(final_order or "")
    if got:
        return got, "final_order"
    if raw:
        tail = _clean(raw)[-1500:]
        got = _outcome_of(tail)
        if got:
            return got, "raw_tail"
    return "unknown", ""


def _clean_statutes(found: list[str]) -> list[str]:
    """Drop parse_statutes fragments cut mid-name, e.g. "Transfer) Rules 1974"
    from "(Appointment, Promotion and Transfer) Rules". A filter, not a second
    normaliser: kept strings are exactly what statutes.py produced."""
    return [s for s in found if not (")" in s and ("(" not in s or s.index(")") < s.index("(")))]


# ── Public API ───────────────────────────────────────────────────────────────

def extract_from_sources(judgment_id: str, raw: str | None, sections: dict[str, str]) -> dict:
    """Pure function over already-loaded text; extract_metadata wraps it."""
    caption, caption_source = caption_text(raw, sections)
    refs_region = caption
    # Case numbers come from before the first party: blank out lower-court
    # references so "Civil Revision No. 699-P/2013" never becomes a key.
    app = _APP_LINE.search(caption) or _VERSUS_LINE.search(caption)
    if app:
        refs_region = caption[: app.start()]
    for start, end in reversed(lower_court_spans(refs_region)):
        refs_region = refs_region[:start] + " " + refs_region[end:]
    case_refs = parse_case_numbers(_flat(refs_region))

    appellant, respondent = extract_parties(caption)
    lower_court, impugned_date = extract_lower_court(caption)
    decision_date, decision_source = extract_decision_date(caption, raw)
    full_text = raw or "\n".join(sections.values())
    outcome, outcome_source = extract_outcome(sections.get("FINAL_ORDER", ""), raw)

    display = case_refs[0]["display"] if case_refs else ""
    if len(case_refs) > 1:
        display += f" (+{len(case_refs) - 1} connected)"

    return {
        "judgment_id": judgment_id,
        "case_refs": case_refs,
        "case_keys": [r["key"] for r in case_refs],
        "case_display": display,
        "bench": extract_bench(caption),
        "appellant": appellant,
        "respondent": respondent,
        "lower_court": lower_court,
        "impugned_date": impugned_date,
        "decision_date": decision_date,
        "counsel": extract_counsel(caption),
        # Note: Qanun-e-Shahadat provisions are also "Article N", so in
        # evidence-heavy judgments some "Article" hits are QSO, not constitutional.
        "statutes": _clean_statutes(parse_statutes(_flat(full_text))),
        "citations": extract_citations(full_text),
        "outcome": outcome,
        # provenance (extra fields; CaseCard is total=False)
        "caption_source": caption_source,
        "decision_date_source": decision_source,
        "outcome_source": outcome_source,
        "metadata_version": METADATA_VERSION,
    }


async def extract_metadata(judgment_id: str) -> dict:
    """Deterministic partial CaseCard for one judgment. No LLM, writes nothing."""
    src = await load_sources(judgment_id)
    if not src["raw"]:
        logger.warning(f"{judgment_id}: no uploads/{judgment_id}.txt, falling back to HEADER_CORAM + FACTS")
    meta = extract_from_sources(judgment_id, src["raw"], src["sections"])
    meta["_filename"] = src["filename"]
    return meta


# ── CLI ──────────────────────────────────────────────────────────────────────

def key_from_filename(filename: str) -> str | None:
    """judgement_C_A_5-Q_2014.pdf -> CA-5-Q-2014; judgement_C_P_L_A_34-Q_2019.pdf -> CP-34-Q-2019."""
    m = re.match(r"judge?ment_([A-Za-z_]+?)_(\d+)(?:-([A-Za-z]))?_(\d{4})", filename or "", re.IGNORECASE)
    if not m:
        return None
    letters = m.group(1).replace("_", "").upper()
    code = {"CA": "CA", "CPLA": "CP", "CP": "CP", "CRLA": "CRA", "CRA": "CRA", "CRLP": "CRP", "CRP": "CRP"}.get(letters, letters)
    parts = [code, str(int(m.group(2)))]
    if m.group(3):
        parts.append(m.group(3).upper())
    parts.append(m.group(4))
    return "-".join(parts)


async def _all_ids() -> list[str]:
    from app.database import connect_db, db

    await connect_db()
    assert db.is_connected, "MongoDB not connected (MONGO_URL)"
    return sorted(await db.documents.distinct("pdf_id"))


def _report(rows: list[dict]) -> dict:
    n = len(rows)
    key_ok = sum(1 for r in rows if key_from_filename(r["_filename"]) in r["case_keys"]
                 and r["case_keys"] and r["case_keys"][0] == key_from_filename(r["_filename"]))
    fields = ["bench", "appellant", "respondent", "lower_court", "impugned_date", "decision_date",
              "counsel", "statutes", "citations"]
    print(f"\n{'file':<34} {'key':<14} {'ok':<3} {'bench':>5} {'app':>4} {'resp':>4} {'lower':>5} "
          f"{'imp':>4} {'dec':>4} {'cnsl':>4} {'stat':>4} {'cite':>4} outcome")
    for r in rows:
        exp = key_from_filename(r["_filename"])
        got = r["case_keys"][0] if r["case_keys"] else "-"
        print(f"{r['_filename'][:34]:<34} {got:<14} {'Y' if got == exp else 'N':<3} "
              f"{len(r['bench']):>5} {'Y' if r['appellant'] else '-':>4} {'Y' if r['respondent'] else '-':>4} "
              f"{'Y' if r['lower_court'] else '-':>5} {'Y' if r['impugned_date'] else '-':>4} "
              f"{'Y' if r['decision_date'] else '-':>4} {len(r['counsel']):>4} {len(r['statutes']):>4} "
              f"{len(r['citations']):>4} {r['outcome']} ({r['outcome_source'] or '-'})")
    print("\ncoverage:")
    print(f"  case key == filename key (first key)  {key_ok}/{n}")
    cov = {}
    for f in fields:
        cov[f] = sum(1 for r in rows if r[f])
        print(f"  {f:<36} {cov[f]}/{n}")
    dist: dict[str, int] = {}
    for r in rows:
        dist[r["outcome"]] = dist.get(r["outcome"], 0) + 1
    print(f"  outcome distribution                  {dist}")
    return {"n": n, "key_ok": key_ok, "coverage": cov, "outcomes": dist}


def _selftest() -> None:
    """Unit checks on the hard caption cases, independent of the database."""
    caption = (
        "PRESENT:\nMR. JUSTICE MIAN SAQIB NISAR, HCJ\nMR. JUSTICE UMAR ATA BANDIAL\n\n"
        "CIVIL APPEAL NO. 23-P OF 2017\n(On appeal against the judgment dated\n12.05.2017 passed by the "
        "Peshawar High\nCourt, Peshawar in Civil Revision No. 699-\nP/2013)\n\nPirzada Noor-ul-Basar\n\n"
        "  Appellant\nVersus\nMst. Pakistan Bibi and others\n\n Respondent(s)\n\nFor the Appellant:\n"
        "Mr. Javed Iqbal Gulbela, ASC\n(Through video link from Peshawar)\n\nDate of Hearing:\n29.03.2023\n"
    )
    meta = extract_from_sources("selftest", caption + "\nJUDGMENT\n...appeal is dismissed.\nIslamabad, the\n"
                                "29th of March, 2023\n", {})
    assert meta["case_keys"] == ["CA-23-P-2017"], meta["case_keys"]
    assert meta["bench"] == ["Justice Mian Saqib Nisar, HCJ", "Justice Umar Ata Bandial"], meta["bench"]
    assert meta["appellant"] == "Pirzada Noor-ul-Basar", meta["appellant"]
    assert meta["respondent"] == "Mst. Pakistan Bibi and others", meta["respondent"]
    assert meta["lower_court"] == "Peshawar High Court, Peshawar", meta["lower_court"]
    assert meta["impugned_date"] == "12.05.2017", meta["impugned_date"]
    assert meta["decision_date"] == "29.03.2023", meta["decision_date"]
    assert meta["counsel"] == ["Mr. Javed Iqbal Gulbela, ASC (for the appellant)"], meta["counsel"]
    assert meta["outcome"] == "dismissed", meta["outcome"]
    assert extract_citations("see 2000 SCMR 1046 and PLD 2019 SC 123 and 2014 PLC (C.S.) 55") == \
        ["2000 SCMR 1046", "PLD 2019 SC 123", "2014 PLC (CS) 55"]
    assert _outcome_of("JUDGE\n\nIslamabad, the 29th of March, 2023 Approved For Reporting") is None
    assert _outcome_of("the appeal is allowed and the matter is remanded") == "remanded"
    assert _clean_statutes(["Article 199", "Transfer) Rules 1974", "Article 185(3)"]) == ["Article 199", "Article 185(3)"]
    lc = extract_lower_court("(On appeal from the judgment dated\n14.05.2018 of the High Court of Sindh, Karachi\n"
                             "passed in Misc. Appeal No. 317 of 2003)")
    assert lc == ("High Court of Sindh, Karachi", "14.05.2018"), lc
    a, _ = extract_parties("CIVIL APPEAL NO. 42-K OF 2016 &\n(On appeal against x)\n\nManzoor Hussain and another\n"
                           "(In CA 42-K/2016)\nApplication for early hearing\n(In HRC 36629-S/18)\n  Appellants\nVERSUS\n"
                           "Khalid Aziz and others\n(In CA 42-K/2016)\n  Respondents\n")
    assert a == "Manzoor Hussain and another", a
    assert key_from_filename("judgement_C_P_L_A_34-Q_2019.pdf") == "CP-34-Q-2019"
    assert key_from_filename("judgement_C_A_6_2016.pdf") == "CA-6-2016"
    print("selftest OK")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Deterministic judgment metadata (no LLM, writes nothing).")
    parser.add_argument("--all", action="store_true", help="every judgment in `documents`")
    parser.add_argument("--report", action="store_true", help="print the coverage table")
    parser.add_argument("--show", metavar="JUDGMENT_ID")
    args = parser.parse_args()

    _selftest()

    async def main() -> None:
        if args.show:
            meta = await extract_metadata(args.show)
            print(json.dumps(meta, indent=2, ensure_ascii=False, default=str))
            return
        if args.all:
            ids = await _all_ids()
            rows = [await extract_metadata(i) for i in ids]
            if args.report:
                summary = _report(rows)
                n = summary["n"]
                assert n > 0, "no judgments found"
                assert summary["key_ok"] == n, f"case key mismatch: {summary['key_ok']}/{n}"
                for f in ("bench", "appellant", "respondent"):
                    assert summary["coverage"][f] >= n - 1, f"{f} coverage {summary['coverage'][f]}/{n}"
                print("\nOK: metadata acceptance checks passed.")
            else:
                for r in rows:
                    print(r["judgment_id"], r["case_keys"], r["outcome"])

    asyncio.run(main())
