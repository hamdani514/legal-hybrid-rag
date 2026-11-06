"""
Password hashing and checking, off the event loop and in a bounded line.

bcrypt is slow on purpose (~200 ms per check at 12 rounds) so stolen hashes are
expensive to crack. It used to run directly in the request handlers, on the
server's single event loop: while one password was checked nothing else was
served. Measured: 200 people signing in at once all waited ~41 s, and anyone
opening any page waited as long; 1,000 at once all timed out and the site
stopped answering for minutes.

Now every bcrypt call runs on a small thread pool (bcrypt releases the GIL, so
the threads really run in parallel) while the event loop keeps serving pages.
At most PASSWORD_WORKERS run at once; others wait in line up to
PASSWORD_QUEUE_WAIT_S. When the line is full, or the wait would be longer, the
person is told at once that sign-in is busy (503, Retry-After) instead of
hanging. Only sign-in work queues here: pages, chats and searches never do.
"""

from __future__ import annotations

import asyncio
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, Tuple

from fastapi import HTTPException
from loguru import logger

from app.api import security
from app.config import settings

BUSY_MESSAGE = "Many people are signing in right now. Please try again in a few seconds."

_executor: Optional[ThreadPoolExecutor] = None
_state: dict = {"loop": None, "sem": None}
waiting = 0
running = 0


def workers() -> int:
    configured = int(getattr(settings, "PASSWORD_WORKERS", 0) or 0)
    return configured if configured > 0 else max(2, min(8, (os.cpu_count() or 2) // 2))


def _gate() -> asyncio.Semaphore:
    global _executor
    loop = asyncio.get_running_loop()
    if _state["loop"] is not loop:
        _state.update(loop=loop, sem=asyncio.Semaphore(workers()))
    if _executor is None:
        _executor = ThreadPoolExecutor(max_workers=workers(), thread_name_prefix="bcrypt")
    return _state["sem"]


async def _run(fn, *args):
    global waiting, running
    sem = _gate()
    max_waiting = int(getattr(settings, "PASSWORD_MAX_WAITING", 0) or workers() * 50)
    wait_s = float(getattr(settings, "PASSWORD_QUEUE_WAIT_S", 20) or 20)
    # Counted here, not read from the semaphore: in a burst that arrives in one
    # tick nobody has taken a slot yet, so "is it full?" would still say no.
    if running + waiting >= workers() + max_waiting:
        raise HTTPException(status_code=503, detail=BUSY_MESSAGE, headers={"Retry-After": "5"})
    waiting += 1
    try:
        await asyncio.wait_for(sem.acquire(), timeout=wait_s)
    except asyncio.TimeoutError:
        logger.warning(f"Sign-in refused: waited {wait_s:.0f}s for a password slot ({running} running)")
        raise HTTPException(status_code=503, detail=BUSY_MESSAGE, headers={"Retry-After": "10"}) from None
    finally:
        waiting -= 1
    running += 1
    try:
        return await asyncio.get_running_loop().run_in_executor(_executor, fn, *args)
    finally:
        running -= 1
        sem.release()


async def verify(plain: str, stored: Optional[str]) -> Tuple[bool, bool]:
    """security.verify_password, off the event loop. (matches, needs_upgrade)"""
    return await _run(security.verify_password, plain, stored)


async def hash(plain: str) -> str:  # noqa: A001 - mirrors security.hash_password
    """security.hash_password, off the event loop. Raises ValueError like it."""
    return await _run(security.hash_password, plain)


async def burn(plain: str) -> None:
    """Spend the time of one password check, so an unknown account answers as
    slowly as a wrong password (no telling which emails are registered)."""
    await _run(security.burn_password_check, plain or "")


def shutdown() -> None:
    global _executor
    if _executor is not None:
        _executor.shutdown(wait=False, cancel_futures=True)
        _executor = None
