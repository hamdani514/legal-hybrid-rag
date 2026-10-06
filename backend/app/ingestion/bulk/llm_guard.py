"""
Bounded, rate-limit-aware LLM parsing for bulk ingestion.

The problem this solves: parse_sections never raises on a rate limit.
`parser.call_gemini` catches every exception, logs "Gemini API error in parser:
429 RESOURCE_EXHAUSTED ..." and returns "", and the hybrid classifier's Groq
call does the same. The parse then silently degrades to the rule-based
fallback and is cached to uploads/{pdf_id}_sections.json. Run 3,000 files
through that at full speed and every file past the quota ceiling gets a worse
parse, permanently, with nothing in the database saying so.

We cannot change the parser (other agents own it), so the guard listens
instead: a loguru sink watches WARNING+ records from app.ingestion.* for
rate-limit / timeout signatures, and attributes each hit to the parse that
emitted it through a ContextVar (each asyncio task carries its own context, so
concurrent parses do not see each other's errors). A parse that saw a hit has
its cached output deleted and is retried with exponential backoff + jitter; a
hit also opens a shared cooldown window so the other in-flight parses stop
hammering the quota too. When the retries run out the document FAILS with the
reason, rather than shipping a degraded parse; `--retry-failed` picks it up.

Concurrency is an asyncio.Semaphore around parse_sections, which makes ~1-2
LLM calls per judgment (one Gemini context call; the Groq boundary call only
when GROQ_API_KEY is set).
"""
from __future__ import annotations

import asyncio
import contextvars
import random
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from loguru import logger

RATE_LIMIT_RE = re.compile(
    r"\b429\b|RESOURCE_EXHAUSTED|rate[ _-]?limit|too many requests|quota"
    r"|\b503\b|UNAVAILABLE|overloaded|timed? ?out|deadline exceeded|ReadTimeout",
    re.IGNORECASE,
)

# A rate limit that will not clear by waiting minutes: the free tier's daily
# request quota (Gemini's quotaId "GenerateRequestsPerDayPerProjectPerModel").
DAILY_QUOTA_RE = re.compile(r"PerDay|per[ _-]?day|daily", re.IGNORECASE)


@dataclass
class _Watch:
    hits: list[str] = field(default_factory=list)


_current_watch: contextvars.ContextVar[_Watch | None] = contextvars.ContextVar(
    "bulk_llm_watch", default=None
)


@dataclass
class LLMStats:
    gemini_calls: int = 0
    groq_calls: int = 0
    rate_limit_hits: int = 0
    retries: int = 0
    parse_seconds_waiting: float = 0.0


class LLMGuard:
    def __init__(self, concurrency: int = 3, max_attempts: int = 5,
                 base_delay: float = 5.0, max_delay: float = 120.0,
                 parse_timeout: float = 600.0, uploads_dir: Path | None = None,
                 allow_cleanup: bool = True):
        self.sem = asyncio.Semaphore(max(1, concurrency))
        self.max_attempts = max(1, max_attempts)
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.parse_timeout = parse_timeout
        self.uploads_dir = uploads_dir or Path(__file__).resolve().parents[3] / "uploads"
        self.stats = LLMStats()
        # False on the production DB without --allow-main-db: the degraded
        # cache is then left alone and the parse fails at once (a retry would
        # only re-read the same cached degraded result).
        self.allow_cleanup = allow_cleanup
        # Optional ProcessPoolExecutor, set by the pipeline. None = in-loop.
        self.pool = None
        self._cooldown_until = 0.0
        self._sink_id: int | None = None
        self._orig_call = None

    # ── instrumentation ────────────────────────────────────────────────
    def install(self) -> None:
        def _sink(message) -> None:
            rec = message.record
            text = rec["message"]
            if text.startswith("Calling Groq") or "Calling Groq (" in text:
                self.stats.groq_calls += 1
                return
            if rec["level"].no < 30:  # below WARNING
                return
            if not RATE_LIMIT_RE.search(text):
                return
            watch = _current_watch.get()
            if watch is not None:
                watch.hits.append(text[:300])

        self._sink_id = logger.add(
            _sink, level="INFO",
            filter=lambda r: (r["name"] or "").startswith("app.ingestion")
            and not (r["name"] or "").startswith("app.ingestion.bulk"),
        )

        # Count Gemini calls. parser.py looks `call_ollama` up as a module
        # global at call time, so wrapping the attribute is enough.
        from app.ingestion import parser

        orig = parser.call_ollama
        self._orig_call = orig
        stats = self.stats

        async def _counted(prompt, system):
            stats.gemini_calls += 1
            # In ingest.log even if the run is killed before the report.
            logger.debug(f"bulk: gemini call #{stats.gemini_calls}")
            return await orig(prompt, system)

        parser.call_ollama = _counted

    def uninstall(self) -> None:
        if self._sink_id is not None:
            logger.remove(self._sink_id)
            self._sink_id = None
        if self._orig_call is not None:
            from app.ingestion import parser

            parser.call_ollama = self._orig_call
            self._orig_call = None

    # ── backoff ────────────────────────────────────────────────────────
    def backoff_delay(self, attempt: int) -> float:
        """Exponential with full jitter on top: base*2^attempt + U(0, base)."""
        d = min(self.max_delay, self.base_delay * (2 ** attempt))
        return d + random.uniform(0, self.base_delay)

    async def _wait_cooldown(self) -> None:
        now = time.monotonic()
        if self._cooldown_until > now:
            wait = self._cooldown_until - now
            self.stats.parse_seconds_waiting += wait
            await asyncio.sleep(wait)

    # Public face of the semaphore + shared cooldown, for LLM work other than
    # parsing (the case-card wave in app.ingestion.case_card reuses them).
    async def wait_cooldown(self) -> None:
        await self._wait_cooldown()

    def open_cooldown(self, delay: float) -> None:
        """Every caller sharing this guard pauses for `delay` seconds."""
        self._cooldown_until = max(self._cooldown_until, time.monotonic() + delay)
        self.stats.rate_limit_hits += 1

    async def _parse_in_loop(self, pdf_id: str, text: str):
        """In-process parse (used by the self-check and when pool is None)."""
        from app.ingestion.parser import parse_sections

        watch = _Watch()
        token = _current_watch.set(watch)
        try:
            final = await asyncio.wait_for(parse_sections(pdf_id=pdf_id, extracted_text=text),
                                           timeout=self.parse_timeout)
            return final, watch.hits, False
        except asyncio.TimeoutError:
            return None, watch.hits, True
        finally:
            _current_watch.reset(token)

    async def _parse_in_pool(self, pdf_id: str, text: str):
        """Parse in an LLM worker process (see workers.parse_one for why)."""
        from app.ingestion.bulk.workers import parse_one

        loop = asyncio.get_running_loop()
        res = await loop.run_in_executor(self.pool, parse_one, pdf_id, text, self.parse_timeout)
        self.stats.gemini_calls += res["gemini_calls"]
        self.stats.groq_calls += res["groq_calls"]
        logger.debug(f"bulk: [{pdf_id}] worker made {res['gemini_calls']} gemini call(s); "
                     f"total {self.stats.gemini_calls}")
        if res["error"]:
            raise RuntimeError(res["error"])
        return res["final"], res["hits"], res["timed_out"]

    def _clear_parse_cache(self, pdf_id: str) -> None:
        for suffix in ("_sections.json", "_summary.md"):
            f = self.uploads_dir / f"{pdf_id}{suffix}"
            if f.exists():
                f.unlink()

    async def parse(self, pdf_id: str, text: str) -> tuple[dict, dict]:
        """Run parse_sections under the semaphore with retry.

        Returns (final, info). Raises RuntimeError with a reason when the
        rate limit outlasts max_attempts, asyncio.TimeoutError likewise.
        """
        info = {"attempts": 0, "rate_limit_hits": [], "llm_seconds": 0.0}
        last_reason = ""
        for attempt in range(self.max_attempts):
            info["attempts"] = attempt + 1
            await self._wait_cooldown()
            async with self.sem:
                t0 = time.perf_counter()
                if self.pool is not None:
                    final, hits, timed_out = await self._parse_in_pool(pdf_id, text)
                else:
                    final, hits, timed_out = await self._parse_in_loop(pdf_id, text)
                info["llm_seconds"] += time.perf_counter() - t0

            if not hits and not timed_out:
                return final, info
            watch = _Watch(hits=hits)

            # Degraded or timed out: throw the cached parse away and back off.
            if not self.allow_cleanup:
                raise RuntimeError("LLM rate-limited/transient error and cache cleanup is "
                                   "disabled on the protected database: "
                                   + (watch.hits[-1] if watch.hits else "timeout"))
            self._clear_parse_cache(pdf_id)
            self.stats.rate_limit_hits += len(watch.hits)
            info["rate_limit_hits"].extend(watch.hits)
            last_reason = (f"parse timed out after {self.parse_timeout:.0f}s"
                           if timed_out else f"LLM rate-limited/transient error: {watch.hits[-1]}")
            if attempt + 1 >= self.max_attempts:
                break
            delay = self.backoff_delay(attempt)
            self._cooldown_until = max(self._cooldown_until, time.monotonic() + delay)
            self.stats.retries += 1
            logger.warning(f"[{pdf_id}] {last_reason[:160]} - retry {attempt + 2}/"
                           f"{self.max_attempts} in {delay:.1f}s")
            await asyncio.sleep(delay)

        raise RuntimeError(f"gave up after {info['attempts']} attempts: {last_reason}")


if __name__ == "__main__":
    # Self-check without any real LLM call: fake a parser that logs a 429 the
    # first time and succeeds the second, and check the guard retries once,
    # attributes the hit to the right task only, and counts calls.
    import tempfile

    from app.ingestion import parser

    tmp = Path(tempfile.mkdtemp())
    calls = {"a": 0, "b": 0}

    async def fake_parse_sections(pdf_id, extracted_text):
        calls[pdf_id] += 1
        await parser.call_ollama("p", "s")
        if pdf_id == "a" and calls["a"] == 1:
            logger.bind().patch(lambda r: r.update(name="app.ingestion.parser")).error(
                "Gemini API error in parser: 429 RESOURCE_EXHAUSTED")
            (tmp / "a_sections.json").write_text("{}")
        await asyncio.sleep(0.05)
        return {"pdf_id": pdf_id, "parse_mode": "hybrid_llm_ner"}

    async def fake_call(prompt, system):
        return "{}"

    real_ps, real_call = parser.parse_sections, parser.call_ollama
    parser.parse_sections, parser.call_ollama = fake_parse_sections, fake_call

    async def main():
        g = LLMGuard(concurrency=2, base_delay=0.1, max_delay=0.2, uploads_dir=tmp)
        g.install()
        try:
            (ra, ia), (rb, ib) = await asyncio.gather(g.parse("a", "x"), g.parse("b", "y"))
        finally:
            g.uninstall()
        assert ia["attempts"] == 2 and len(ia["rate_limit_hits"]) == 1, ia
        assert ib["attempts"] == 1 and not ib["rate_limit_hits"], ib
        assert not (tmp / "a_sections.json").exists(), "degraded cache not cleared"
        assert g.stats.gemini_calls == 3 and g.stats.retries == 1, g.stats
        assert parser.call_ollama is fake_call, "uninstall did not restore"

        g2 = LLMGuard(max_attempts=2, base_delay=0.01, max_delay=0.02, uploads_dir=tmp)
        g2.install()
        calls["a"] = 0

        async def always_429(pdf_id, extracted_text):
            logger.patch(lambda r: r.update(name="app.ingestion.parser")).error("429 quota")
            return {}

        parser.parse_sections = always_429
        try:
            await g2.parse("a", "x")
            raise AssertionError("expected give-up")
        except RuntimeError as e:
            assert "gave up after 2 attempts" in str(e)
        finally:
            g2.uninstall()

    try:
        asyncio.run(main())
    finally:
        parser.parse_sections, parser.call_ollama = real_ps, real_call
    print("llm_guard self-check OK")
