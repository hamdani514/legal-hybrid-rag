"""
One process-wide gate in front of every hosted-LLM call.

Why this exists
---------------
The project runs on Gemini's free tier: 15 requests per minute for the whole
project, not per user. Before this module every caller fired its own request —
one answer per returned judgment, one compare row per judgment, the judge, the
analyzer, the card builder — with no queue and no retry. Past about five
searches a minute Gemini answered 429, ``_complete`` turned that into the error
sentinel, and users saw "Error: Could not generate answer..." rendered as if it
were the analysis.

What it does
------------
* **A sliding 60-second window of at most ``LLM_RPM_LIMIT`` issued calls.** The
  plan calls it a token bucket; it is the strict form of one. A classic bucket
  with a full-size burst lets 2 x RPM calls land inside one sliding minute
  (a full burst, then a full refill), and Gemini's quota is measured over such
  a minute — so the bucket would itself cause the 429s it is meant to prevent.
  The window guarantees "no more than N in any 60 s", which is the property
  that matters and the one the load test asserts.
* **A concurrency cap** (``LLM_MAX_CONCURRENCY``) so a burst of searches cannot
  hold dozens of slow generations open at once.
* **A wait budget** (``LLM_MAX_WAIT_S``). A caller queues at most that long
  (time spent inside the provider call does not count). If the next free slot
  is further away than its remaining budget it is told so *immediately* — a
  structured ``rate_limited`` outcome, not an exception and not a 20-second
  stall that ends in the same answer.
* **429 handling.** When the provider still answers 429 (another process shares
  the key, or the daily quota is gone), the retry delay Gemini puts in its
  RetryInfo detail ("retryDelay": "17s") or message ("Please retry in 17.4s")
  becomes a process-wide cooldown, so every waiting caller backs off together
  instead of each spending a request to discover the same thing. The call is
  retried while the budget allows.

Callers never see provider exceptions: ``run()`` always returns an
:class:`LLMOutcome` whose ``status`` is one of contracts.ANSWER_STATUSES
(``ready`` / ``rate_limited`` / ``error``).

Scope: the window is per process. A bulk card wave run as a separate process
(``case_card --all``) has its own window and shares the provider quota; it
already backs off on 429, and its 429s now also cool this process down.
"""

from __future__ import annotations

import asyncio
import re
import sys
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from loguru import logger

from app.config import settings
from app.retrieval.contracts import ANSWER_ERROR, ANSWER_RATE_LIMITED, ANSWER_READY

WINDOW_SECONDS = 60.0

# A call stays in the window this much longer than the period. Two measured
# reasons: asyncio may wake a sleeper up to one clock tick early (~16 ms on
# Windows), and requests reach the provider with varying network delay, so two
# calls issued exactly 60.0 s apart can land 59.9 s apart in the provider's own
# minute. Without it the fake-LLM load test saw 16 calls in a 60 s window.
WINDOW_MARGIN_S = 0.5

# Used when a 429 carries no retry hint. One window slot at the configured RPM,
# floored so a tiny RPM in a test cannot produce a busy loop.
MIN_BACKOFF_S = 2.0

# Transient provider failures (5xx, timeouts) get one more attempt, if the
# budget allows; anything else is reported as an error straight away.
TRANSIENT_CODES = {500, 502, 503, 504}
MAX_TRANSIENT_RETRIES = 1

_RETRY_IN = re.compile(r"retry in\s+([\d.]+)\s*(ms|s)", re.IGNORECASE)
_DELAY = re.compile(r"^\s*([\d.]+)\s*(ms|s)?\s*$")


@dataclass
class LLMOutcome:
    """What a gated call produced. ``text`` is "" unless ``status`` is ready."""

    status: str
    text: str = ""
    detail: str = ""
    attempts: int = 0
    waited_s: float = 0.0

    @property
    def ok(self) -> bool:
        return self.status == ANSWER_READY


# ── Error classification ────────────────────────────────────────────────────

def _code_of(error: BaseException) -> int | None:
    for attr in ("code", "status_code"):
        value = getattr(error, attr, None)
        if isinstance(value, int):
            return value
    response = getattr(error, "response", None)
    value = getattr(response, "status_code", None)
    return value if isinstance(value, int) else None


def is_rate_limit_error(error: BaseException) -> bool:
    """True for a provider 429 / RESOURCE_EXHAUSTED, whatever SDK raised it."""
    if _code_of(error) == 429:
        return True
    text = str(error)
    return "RESOURCE_EXHAUSTED" in text or text.startswith("429")


def _is_transient(error: BaseException) -> bool:
    if isinstance(error, (asyncio.TimeoutError, TimeoutError, ConnectionError)):
        return True
    if _code_of(error) in TRANSIENT_CODES:
        return True
    name = type(error).__name__.lower()
    return "timeout" in name or "connect" in name


def _parse_delay(value) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, dict):  # protobuf JSON Duration {"seconds": 17, "nanos": ...}
        seconds = float(value.get("seconds", 0) or 0) + float(value.get("nanos", 0) or 0) / 1e9
        return seconds or None
    if isinstance(value, str):
        match = _DELAY.match(value)
        if match:
            number = float(match.group(1))
            return number / 1000 if match.group(2) == "ms" else number
    return None


def retry_after_seconds(error: BaseException) -> float | None:
    """The provider's own retry hint, in seconds, or None when it gave none.

    Looks, in order, at Gemini's google.rpc.RetryInfo detail, an HTTP
    Retry-After header (OpenAI-compatible providers), and the "Please retry in
    17.4s" sentence Gemini puts in its message.
    """
    details = getattr(error, "details", None)
    if isinstance(details, dict):
        items = (details.get("error") or details).get("details") or []
        for item in items if isinstance(items, list) else []:
            if isinstance(item, dict) and "retryDelay" in item:
                parsed = _parse_delay(item["retryDelay"])
                if parsed is not None:
                    return parsed

    response = getattr(error, "response", None)
    headers = getattr(response, "headers", None)
    if headers is not None:
        try:
            header = headers.get("retry-after")
        except Exception:
            header = None
        parsed = _parse_delay(header) if header else None
        if parsed is not None:
            return parsed

    match = _RETRY_IN.search(str(error))
    if match:
        number = float(match.group(1))
        return number / 1000 if match.group(2).lower() == "ms" else number
    return None


# ── The limiter ─────────────────────────────────────────────────────────────

class _Window:
    """Timestamps of issued calls in the last ``period`` seconds, plus a cooldown.

    Plain data, no asyncio objects, so it survives across event loops (tests
    run several ``asyncio.run`` calls in one process; the quota does not reset
    between them).
    """

    def __init__(self, rpm: int, period: float, margin: float = 0.0):
        self.rpm = max(1, int(rpm))
        self.period = float(period) + float(margin)
        self.issued: deque[float] = deque()
        self.blocked_until = 0.0

    def _prune(self, now: float) -> None:
        while self.issued and self.issued[0] <= now - self.period:
            self.issued.popleft()

    def wait_needed(self, now: float) -> float:
        self._prune(now)
        window_wait = 0.0
        if len(self.issued) >= self.rpm:
            window_wait = self.issued[0] + self.period - now
        return max(0.0, window_wait, self.blocked_until - now)

    def take(self, now: float) -> None:
        self.issued.append(now)

    def in_window(self, now: float) -> int:
        self._prune(now)
        return len(self.issued)


class LLMLimiter:
    """Rate window + concurrency cap + wait budget around an async call.

    Args:
        rpm: Calls allowed in any ``period``-second window.
        concurrency: Calls allowed in flight at once.
        max_wait: Default queueing budget in seconds.
        period: Window length; 60 in production, shortened by tests.
    """

    def __init__(self, rpm: int, concurrency: int, max_wait: float, period: float = WINDOW_SECONDS):
        # The safety margin scales with the period so shortened test windows
        # keep their proportions.
        self.window = _Window(rpm, period, margin=WINDOW_MARGIN_S * period / WINDOW_SECONDS)
        self.concurrency = max(1, int(concurrency))
        self.max_wait = float(max_wait)
        self._loop: asyncio.AbstractEventLoop | None = None
        self._sem: asyncio.Semaphore | None = None
        self._order: asyncio.Lock | None = None
        self.stats = {"issued": 0, ANSWER_READY: 0, ANSWER_RATE_LIMITED: 0, ANSWER_ERROR: 0,
                      "provider_429": 0}

    def _primitives(self) -> tuple[asyncio.Semaphore, asyncio.Lock]:
        loop = asyncio.get_running_loop()
        if self._loop is not loop:
            self._loop = loop
            self._sem = asyncio.Semaphore(self.concurrency)
            self._order = asyncio.Lock()
        return self._sem, self._order  # type: ignore[return-value]

    def cooldown(self, seconds: float) -> None:
        """Pause every caller for ``seconds`` (a provider told us to back off)."""
        until = time.monotonic() + max(0.0, seconds)
        self.window.blocked_until = max(self.window.blocked_until, until)

    def snapshot(self) -> dict:
        now = time.monotonic()
        return {**self.stats, "in_window": self.window.in_window(now), "rpm": self.window.rpm,
                "cooldown_s": round(max(0.0, self.window.blocked_until - now), 1)}

    def _finish(self, outcome: LLMOutcome, label: str) -> LLMOutcome:
        self.stats[outcome.status] = self.stats.get(outcome.status, 0) + 1
        if outcome.status == ANSWER_READY:
            logger.debug(f"LLM[{label}] ready after {outcome.waited_s:.1f}s queued, "
                         f"{outcome.attempts} attempt(s)")
        else:
            logger.warning(f"LLM[{label}] {outcome.status}: {outcome.detail} "
                           f"(queued {outcome.waited_s:.1f}s, {outcome.attempts} attempt(s))")
        return outcome

    async def run(
        self,
        call: Callable[[], Awaitable[str]],
        *,
        max_wait: float | None = None,
        label: str = "llm",
    ) -> LLMOutcome:
        """Issue ``call()`` when the window and the concurrency cap allow it.

        ``call`` must raise on failure (provider exceptions, timeouts) and
        return the generated text on success; it may be invoked more than once
        (429 and transient retries), so it must be a factory, not a coroutine.
        """
        budget = self.max_wait if max_wait is None else float(max_wait)
        started = time.monotonic()
        deadline = started + budget
        in_calls = 0.0
        attempts = 0
        transient_retries = 0
        sem, order = self._primitives()

        def waited() -> float:
            return max(0.0, time.monotonic() - started - in_calls)

        while True:
            # 1. A concurrency slot, within the budget.
            remaining = deadline - time.monotonic()
            try:
                if sem.locked():
                    if remaining <= 0:
                        raise TimeoutError
                    async with asyncio.timeout(remaining):
                        await sem.acquire()
                else:
                    await sem.acquire()
            except TimeoutError:
                return self._finish(LLMOutcome(
                    ANSWER_RATE_LIMITED, detail="all LLM slots busy for the whole wait budget",
                    attempts=attempts, waited_s=waited()), label)

            try:
                # 2. A slot in the rate window. The lock serves waiters in
                # arrival order; whoever holds it sleeps until its slot opens.
                remaining = deadline - time.monotonic()
                try:
                    if order.locked():
                        if remaining <= 0:
                            raise TimeoutError
                        async with asyncio.timeout(remaining):
                            await order.acquire()
                    else:
                        await order.acquire()
                except TimeoutError:
                    return self._finish(LLMOutcome(
                        ANSWER_RATE_LIMITED, detail="rate window queue longer than the wait budget",
                        attempts=attempts, waited_s=waited()), label)
                try:
                    now = time.monotonic()
                    need = self.window.wait_needed(now)
                    if need > deadline - now:
                        return self._finish(LLMOutcome(
                            ANSWER_RATE_LIMITED,
                            detail=f"next LLM slot in {need:.1f}s exceeds the remaining "
                                   f"{max(0.0, deadline - now):.1f}s budget",
                            attempts=attempts, waited_s=waited()), label)
                    while need > 0:  # re-checked: sleep may wake a tick early
                        await asyncio.sleep(need + 0.005)
                        need = self.window.wait_needed(time.monotonic())
                    self.window.take(time.monotonic())
                    self.stats["issued"] += 1
                finally:
                    order.release()

                # 3. The call itself; its duration does not count against the budget.
                attempts += 1
                call_started = time.monotonic()
                try:
                    text = await call()
                    error: BaseException | None = None
                except asyncio.CancelledError:
                    raise
                except Exception as e:  # provider errors of every SDK
                    text, error = "", e
                spent = time.monotonic() - call_started
                in_calls += spent
                deadline += spent
            finally:
                sem.release()

            if error is None:
                if not (text or "").strip():
                    return self._finish(LLMOutcome(
                        ANSWER_ERROR, detail="provider returned an empty response",
                        attempts=attempts, waited_s=waited()), label)
                return self._finish(LLMOutcome(
                    ANSWER_READY, text=text.strip(), attempts=attempts, waited_s=waited()), label)

            if is_rate_limit_error(error):
                self.stats["provider_429"] += 1
                hint = retry_after_seconds(error)
                delay = hint if hint is not None else max(MIN_BACKOFF_S, self.window.period / self.window.rpm)
                self.cooldown(delay)
                logger.warning(f"LLM[{label}] provider 429; cooling down {delay:.1f}s "
                               f"({'retry-after' if hint is not None else 'default'})")
                if time.monotonic() + delay > deadline:
                    return self._finish(LLMOutcome(
                        ANSWER_RATE_LIMITED, detail=f"provider rate limit; retry in {delay:.0f}s",
                        attempts=attempts, waited_s=waited()), label)
                continue  # step 2 waits out the cooldown

            if _is_transient(error) and transient_retries < MAX_TRANSIENT_RETRIES \
                    and deadline - time.monotonic() > 1.0:
                transient_retries += 1
                logger.warning(f"LLM[{label}] transient failure, retrying once: {error}")
                await asyncio.sleep(1.0)
                continue

            return self._finish(LLMOutcome(
                ANSWER_ERROR, detail=f"{type(error).__name__}: {str(error)[:300]}",
                attempts=attempts, waited_s=waited()), label)


_limiter: LLMLimiter | None = None


def get_limiter() -> LLMLimiter:
    """The process-wide limiter, built from settings on first use."""
    global _limiter
    if _limiter is None:
        _limiter = LLMLimiter(
            rpm=int(getattr(settings, "LLM_RPM_LIMIT", 14) or 14),
            concurrency=int(getattr(settings, "LLM_MAX_CONCURRENCY", 3) or 3),
            max_wait=float(getattr(settings, "LLM_MAX_WAIT_S", 20.0) or 20.0),
        )
        logger.info(f"LLM limiter: {_limiter.window.rpm}/min, {_limiter.concurrency} concurrent, "
                    f"{_limiter.max_wait:.0f}s wait budget")
    return _limiter


if __name__ == "__main__":
    # Self-check with fake calls on a 1-second window, so it runs in seconds and
    # spends nothing.

    class Fake429(Exception):
        code = 429

        def __init__(self, delay: str):
            self.details = {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED", "details": [
                {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": delay}]}}
            super().__init__(f"429 RESOURCE_EXHAUSTED. Please retry in {delay}.")

    async def main() -> None:
        # Retry hints.
        assert retry_after_seconds(Fake429("17s")) == 17.0
        assert retry_after_seconds(Exception("Quota exceeded. Please retry in 4.5s.")) == 4.5
        assert retry_after_seconds(Exception("nothing here")) is None
        assert is_rate_limit_error(Fake429("1s")) and not is_rate_limit_error(ValueError("x"))

        # 1. Window: 30 callers, 5 per 1 s window, 3 concurrent, 1.5 s budget.
        lim = LLMLimiter(rpm=5, concurrency=3, max_wait=1.5, period=1.0)
        issued: list[float] = []
        in_flight = {"now": 0, "max": 0}

        async def fake() -> str:
            issued.append(time.monotonic())
            in_flight["now"] += 1
            in_flight["max"] = max(in_flight["max"], in_flight["now"])
            await asyncio.sleep(0.05)
            in_flight["now"] -= 1
            return "ok"

        outcomes = await asyncio.gather(*(lim.run(fake) for _ in range(30)))
        statuses = [o.status for o in outcomes]
        for t in issued:
            in_window = sum(1 for u in issued if t <= u < t + 1.0)
            assert in_window <= 5, f"{in_window} calls inside one window"
        assert in_flight["max"] <= 3, in_flight
        assert set(statuses) <= {ANSWER_READY, ANSWER_RATE_LIMITED}, statuses
        assert statuses.count(ANSWER_READY) == len(issued) >= 5
        assert statuses.count(ANSWER_RATE_LIMITED) > 0, "nothing was refused under overload"
        assert all(o.waited_s <= 1.5 + 0.2 for o in outcomes), max(o.waited_s for o in outcomes)
        print(f"window: {statuses.count(ANSWER_READY)} ready, "
              f"{statuses.count(ANSWER_RATE_LIMITED)} rate_limited, max in flight {in_flight['max']}")

        # 2. A provider 429 with a retry hint is waited out and retried.
        lim = LLMLimiter(rpm=100, concurrency=3, max_wait=3.0, period=1.0)
        tries = {"n": 0}

        async def flaky() -> str:
            tries["n"] += 1
            if tries["n"] == 1:
                raise Fake429("0.4s")
            return "second time lucky"

        t0 = time.monotonic()
        out = await lim.run(flaky)
        assert out.ok and out.text == "second time lucky" and out.attempts == 2, out
        assert time.monotonic() - t0 >= 0.4, "retry did not honour retry-after"

        # 3. A 429 whose delay exceeds the budget comes back rate_limited at once.
        async def exhausted() -> str:
            raise Fake429("120s")

        t0 = time.monotonic()
        out = await lim.run(exhausted)
        assert out.status == ANSWER_RATE_LIMITED and out.attempts == 1, out
        assert time.monotonic() - t0 < 0.5, "waited although the delay exceeded the budget"
        lim.window.blocked_until = 0.0

        # 4. Any other failure is an error outcome, never an exception; empty text too.
        async def broken() -> str:
            raise ValueError("bad request")

        async def empty() -> str:
            return "  "

        assert (await lim.run(broken)).status == ANSWER_ERROR
        assert (await lim.run(empty)).status == ANSWER_ERROR
        print("OK: limiter verified (window, concurrency, budget, 429 retry-after, errors).")

    asyncio.run(main())
