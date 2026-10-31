"""
GET /api/stats — public figures about the archive, counted live.

The "How it works" page shows these instead of accuracy percentages: a count
of what is in the archive can be checked by anyone, while an accuracy figure
needs a frozen, reproducible test behind it before it is published.

    judgments            documents that search can find (status searchable or complete)
    scanned_judgments    of those, how many were scanned PDFs read by OCR
    sections             judgment sections marked by the parser (the `nodes` tree)
    passages             passages indexed for search (vectors in the live collection)
    first_year/last_year range of decision dates on the case cards
    updated_at           when these counts were taken

Counts are cached for CACHE_SECONDS: they change only when judgments are
ingested, and a busy landing page should not count the archive on every view.
Public by design (no auth dependency): nothing here identifies a user or a
document.
"""

import asyncio
import re
import time
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from loguru import logger

from app.database import db

router = APIRouter(prefix="/api", tags=["stats"])

CACHE_SECONDS = 300
SEARCHABLE = {"status": {"$in": ["searchable", "complete"]}}
_YEAR = re.compile(r"(1[89]\d\d|20\d\d)")

_cache: dict = {"at": 0.0, "value": None}
_lock = asyncio.Lock()


def _passage_count() -> int | None:
    try:
        from app.retrieval.chroma_client import collection
        return int(collection.count())
    except Exception as e:  # the vector store is optional for this figure
        logger.warning(f"stats: passage count unavailable: {e}")
        return None


_FILED = re.compile(r"\bof\s+(1[89]\d\d|20\d\d)\b", re.I)


async def _year_range() -> tuple[int | None, int | None]:
    """Earliest and latest decision year on the case cards.

    A card's date is read from the judgment by extraction and is sometimes
    misread (31.03.2041; a 2010 appeal "decided" in 1990). A year in the
    future, or before the year in the case's own number ("... of 2010"),
    cannot be a decision date, so it is left out of the range.
    """
    this_year = datetime.now(timezone.utc).year
    years = []
    async for card in db.database.case_cards.find(
        {"decision_date": {"$nin": [None, ""]}}, {"_id": 0, "decision_date": 1, "case_display": 1}
    ):
        match = _YEAR.findall(str(card.get("decision_date") or ""))
        if not match:
            continue
        year = int(match[-1])   # dd.mm.yyyy: the year is last
        filed = _FILED.search(str(card.get("case_display") or ""))
        if year > this_year or (filed and year < int(filed.group(1))):
            continue
        years.append(year)
    return (min(years), max(years)) if years else (None, None)


async def _count() -> dict:
    d = db.database
    judgments, scanned, sections, (first_year, last_year), passages = await asyncio.gather(
        d.documents.count_documents(SEARCHABLE),
        d.documents.count_documents({**SEARCHABLE, "ocr.ocr_pages": {"$gt": 0}}),
        d.nodes.count_documents({}),
        _year_range(),
        asyncio.to_thread(_passage_count),
    )
    return {
        "judgments": judgments,
        "scanned_judgments": scanned,
        "sections": sections,
        "passages": passages,
        "first_year": first_year,
        "last_year": last_year,
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


@router.get("/stats")
async def archive_stats() -> dict:
    if db.database is None:
        raise HTTPException(status_code=503, detail="Database is not connected.")
    async with _lock:
        if _cache["value"] is None or time.monotonic() - _cache["at"] > CACHE_SECONDS:
            _cache["value"] = await _count()
            _cache["at"] = time.monotonic()
        return _cache["value"]
