"""
How many searches run at once.

A search is CPU-bound (embedding, two vector searches, the cross-encoder) and
holds a few hundred MB while it runs. Measured on a 16-core machine: one search
alone ~6 s; 25 at once all slowed to 47 s typical / 63 s worst and memory rose
from 1.6 to 2.7 GB. Past ~60 s many proxies drop the request, so a crowd made
every search fail together, and memory could run out first.

So only a few run at a time and the rest wait in line. A request that would
wait longer than SEARCH_QUEUE_WAIT_S, or arrives when the line is already
full, is told at once that the service is busy (503 with Retry-After) instead
of hanging until a proxy cuts it off. Those served stay fast; memory stays
near the "a few at once" level.

One process holds all the slots, matching the single-worker deployment (the
per-minute limits and the search index files are also per process).
"""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import HTTPException
from loguru import logger

from app.config import settings

BUSY_MESSAGE = "Many people are searching right now. Please try again in a few seconds."


def _slots() -> int:
    configured = int(getattr(settings, "MAX_CONCURRENT_SEARCHES", 0) or 0)
    if configured > 0:
        return configured
    # Searches use several cores each; half the cores, between 2 and 4.
    return max(2, min(4, (os.cpu_count() or 2) // 2))


class SearchSlots:
    def __init__(self, slots: int, wait_s: float, max_waiting: int):
        self.slots = slots
        self.wait_s = wait_s
        self.max_waiting = max_waiting
        self.running = 0
        self.waiting = 0
        self._sem = asyncio.Semaphore(slots)

    def busy(self, retry_after: int) -> HTTPException:
        return HTTPException(status_code=503, detail=BUSY_MESSAGE, headers={"Retry-After": str(retry_after)})

    @asynccontextmanager
    async def slot(self):
        if self.running >= self.slots and self.waiting >= self.max_waiting:
            logger.warning(f"Search refused: {self.running} running, {self.waiting} waiting (line full)")
            raise self.busy(5)
        self.waiting += 1
        try:
            await asyncio.wait_for(self._sem.acquire(), timeout=self.wait_s)
        except asyncio.TimeoutError:
            logger.warning(f"Search refused: waited {self.wait_s:.0f}s for a slot ({self.running} running)")
            raise self.busy(10) from None
        finally:
            self.waiting -= 1
        self.running += 1
        try:
            yield
        finally:
            self.running -= 1
            self._sem.release()


_instance: SearchSlots | None = None


def search_slots() -> SearchSlots:
    global _instance
    if _instance is None:
        slots = _slots()
        _instance = SearchSlots(
            slots=slots,
            wait_s=float(getattr(settings, "SEARCH_QUEUE_WAIT_S", 20) or 20),
            max_waiting=int(getattr(settings, "SEARCH_MAX_WAITING", 0) or slots * 4),
        )
        logger.info(f"Searches: {slots} at a time, up to {_instance.max_waiting} waiting "
                    f"at most {_instance.wait_s:.0f}s each")
    return _instance
