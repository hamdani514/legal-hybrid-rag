"""Which Gemini model to call, and what to do when that model is overloaded.

Google serves each model from its own capacity pool. When one pool is short it
answers 503 "This model is currently experiencing high demand" for minutes at
a stretch, while another model on the same key answers normally. Waiting on
the busy model is what turned a 2-second parse and a 20-second card into a
5-minute ingestion that ended without a card.

So every Gemini call goes through ``call_with_fallback``: GEMINI_MODEL first,
then each model in GEMINI_FALLBACK_MODELS. A model that reports overload is
skipped for UNHEALTHY_S, so the calls behind it do not each pay for the same
failure before moving on.

Only overload moves a call to the next model. A 429 from GEMINI_MODEL does
not: quota is the limiter's business (app/llm/limiter.py), and silently
spending another model's quota would hide the fact that the first one ran out.

A fallback that cannot serve the call, because the key has no access to it or
its own quota is spent, is skipped for an hour and the ORIGINAL overload is
reported. Quotas are per model (the free tier gives some models 20 requests a
day), and the limiter answers a 429 with a process-wide cooldown: letting a
fallback's 429 through would lock the primary model out for hours over a
quota that is not even its own.
"""
from __future__ import annotations

import asyncio
import time
from typing import Awaitable, Callable, TypeVar

from loguru import logger

from app.config import settings

T = TypeVar("T")

# How long an overloaded model is skipped before it is tried again.
UNHEALTHY_S = 120.0
# A fallback model the key cannot use at all (404): not worth retrying soon.
UNAVAILABLE_S = 3600.0
OVERLOAD_CODES = {500, 502, 503, 504}

_skip_until: dict[str, float] = {}


def configured_models() -> list[str]:
    """GEMINI_MODEL, then the fallbacks, in order and without repeats."""
    primary = (getattr(settings, "GEMINI_MODEL", "") or "gemini-2.5-flash-lite").strip()
    extra = str(getattr(settings, "GEMINI_FALLBACK_MODELS", "") or "").split(",")
    return list(dict.fromkeys([primary, *(m.strip() for m in extra if m.strip())]))


def candidates() -> list[str]:
    """Models to try now: the healthy ones, or all of them if none is."""
    ordered = configured_models()
    now = time.monotonic()
    healthy = [m for m in ordered if _skip_until.get(m, 0.0) <= now]
    return healthy or ordered


def _code_of(error: BaseException) -> int | None:
    for attr in ("code", "status_code"):
        value = getattr(error, attr, None)
        if isinstance(value, int):
            return value
    return None


def is_overload(error: BaseException) -> bool:
    """True when the model itself is busy or down, not when the request is wrong."""
    if isinstance(error, (asyncio.TimeoutError, TimeoutError)):
        return True
    if _code_of(error) in OVERLOAD_CODES:
        return True
    text = str(error)
    return "UNAVAILABLE" in text or "high demand" in text or "overloaded" in text.lower()


def _is_missing(error: BaseException) -> bool:
    return _code_of(error) == 404 or "NOT_FOUND" in str(error)


def _is_quota(error: BaseException) -> bool:
    return _code_of(error) == 429 or "RESOURCE_EXHAUSTED" in str(error)


async def call_with_fallback(make_call: Callable[[str], Awaitable[T]]) -> T:
    """Run ``make_call(model)`` on the first model that is not overloaded.

    Raises what the last model raised. If a fallback model does not exist for
    this key, the overload error from the model before it is raised instead:
    that is the failure worth reporting.
    """
    models = candidates()
    overload: BaseException | None = None
    for position, model in enumerate(models):
        last = position == len(models) - 1
        try:
            return await make_call(model)
        except Exception as error:  # noqa: BLE001 - classified below, re-raised unless a fallback remains
            if overload is not None and (_is_missing(error) or _is_quota(error)):
                _skip_until[model] = time.monotonic() + UNAVAILABLE_S
                why = "has no quota left" if _is_quota(error) else "is not available to this key"
                logger.info(f"Gemini fallback model {model} {why}; ignoring it for an hour")
                if last:
                    raise overload from error
                continue
            if not is_overload(error):
                raise
            overload = error
            _skip_until[model] = time.monotonic() + UNHEALTHY_S
            if last:
                raise
            # INFO on purpose. As a warning this line was picked up as the reason a
            # card failed, so the admin page blamed the model switch itself.
            logger.info(f"Gemini model {model} is busy; using {models[position + 1]} "
                        f"for the next {UNHEALTHY_S:.0f}s")
    raise RuntimeError("no Gemini model is configured")  # unreachable: configured_models() is never empty


if __name__ == "__main__":
    class _Err(Exception):
        def __init__(self, code: int, text: str):
            super().__init__(text)
            self.code = code

    async def selfcheck() -> None:
        saved = (getattr(settings, "GEMINI_MODEL", ""), getattr(settings, "GEMINI_FALLBACK_MODELS", ""))
        object.__setattr__(settings, "GEMINI_MODEL", "lite")
        object.__setattr__(settings, "GEMINI_FALLBACK_MODELS", "flash, lite, big")
        try:
            assert configured_models() == ["lite", "flash", "big"], configured_models()

            calls: list[str] = []

            async def busy_lite(model: str) -> str:
                calls.append(model)
                if model == "lite":
                    raise _Err(503, "503 UNAVAILABLE. This model is currently experiencing high demand.")
                return f"answer from {model}"

            _skip_until.clear()
            assert await call_with_fallback(busy_lite) == "answer from flash" and calls == ["lite", "flash"]
            # The busy model is skipped for the calls behind it.
            calls.clear()
            assert await call_with_fallback(busy_lite) == "answer from flash" and calls == ["flash"], calls

            # A quota error is not overload: it is raised, no other model is tried.
            _skip_until.clear()
            calls.clear()

            async def quota(model: str) -> str:
                calls.append(model)
                raise _Err(429, "429 RESOURCE_EXHAUSTED")

            try:
                await call_with_fallback(quota)
                raise AssertionError("a 429 must be raised")
            except _Err as e:
                assert e.code == 429 and calls == ["lite"], calls

            # A fallback the key cannot use is skipped; the next one answers.
            _skip_until.clear()
            calls.clear()

            async def flash_missing(model: str) -> str:
                calls.append(model)
                if model == "lite":
                    raise _Err(503, "503 UNAVAILABLE")
                if model == "flash":
                    raise _Err(404, "404 NOT_FOUND")
                return "answer from big"

            assert await call_with_fallback(flash_missing) == "answer from big" and calls == ["lite", "flash", "big"]

            # A fallback whose own quota is spent must not surface its 429: the
            # limiter would then lock every model out. The overload is reported.
            _skip_until.clear()
            calls.clear()

            async def fallback_out_of_quota(model: str) -> str:
                calls.append(model)
                if model == "lite":
                    raise _Err(503, "503 UNAVAILABLE")
                raise _Err(429, "429 RESOURCE_EXHAUSTED PerDay limit 20")

            try:
                await call_with_fallback(fallback_out_of_quota)
                raise AssertionError("must raise")
            except _Err as e:
                assert e.code == 503, f"a fallback's 429 leaked: {e.code}"
            assert calls == ["lite", "flash", "big"], calls

            # Every model busy: the overload is raised, and all are tried again next time.
            _skip_until.clear()

            async def all_busy(model: str) -> str:
                raise _Err(503, "503 UNAVAILABLE")

            try:
                await call_with_fallback(all_busy)
                raise AssertionError("overload on every model must be raised")
            except _Err as e:
                assert e.code == 503
            assert candidates() == ["lite", "flash", "big"], "all sick: try them all"
            assert is_overload(asyncio.TimeoutError()) and not is_overload(_Err(400, "400 INVALID_ARGUMENT"))
        finally:
            object.__setattr__(settings, "GEMINI_MODEL", saved[0])
            object.__setattr__(settings, "GEMINI_FALLBACK_MODELS", saved[1])
            _skip_until.clear()
        print("OK: Gemini model fallback verified (overload, skip window, primary 429 raised, fallback 429 or 404 skipped, all busy).")

    asyncio.run(selfcheck())
