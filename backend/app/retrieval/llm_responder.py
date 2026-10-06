"""
Answer generation for the retrieval pipeline.

STEP 9 of retrieval: sends the assembled context (from
app.retrieval.context_assembler) and the user's query to an LLM and returns a
structured legal answer. No ChromaDB, no MongoDB, no JSON reads.

Provider
--------
This project already talks to its LLM through the OpenAI-compatible protocol
(app.ingestion.llm_hybrid_classifier), switching between Groq and a local
Ollama with the LLM_PROVIDER setting. Both expose the same /v1 surface, so the
same AsyncOpenAI client serves either, and this module follows that pattern
rather than introducing a second HTTP style. Pass `provider=` to override the
configured choice for one call.

Shared quota
------------
Every hosted call goes through app.llm.limiter: one process-wide rate window
(LLM_RPM_LIMIT per minute) and concurrency cap, a bounded wait, and 429
retries that honour the provider's retry-after. The free Gemini tier allows 15
requests a minute for the whole project, so without this a handful of
concurrent searches turned into 429s that users saw as the answer text.

``_complete`` still returns a string - the judge, analyzer, comparator, card
builder and the evaluation's LLM guard all compare it with ERROR_RESPONSE -
but the string is an :class:`LLMText`, which also carries ``status`` (one of
contracts.ANSWER_STATUSES) and ``detail``. A rate-limited or failed call is
therefore still ``== ERROR_RESPONSE`` for old callers, while new callers read
``.status`` and never have to sniff error text. The raw provider call is
``_provider_call``: the one seam tests replace with a fake LLM.

The answer prompt
-----------------
Users describe their own situation (facts, each side's claims, what the courts
held, the outcome), and the raw description - not the keyword-cleaned query -
is what the model receives. Retrieval can return a judgment on the same
subject whose facts or outcome differ from the user's in ways that decide the
matter, so the answer ends with [FIT WITH YOUR SITUATION], which says plainly
where the judgment matches and where it differs.
"""

import asyncio
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from loguru import logger
from openai import AsyncOpenAI
from google import genai
from google.genai import types

from app.config import settings
from app.llm.limiter import get_limiter
from app.retrieval.contracts import ANSWER_ERROR, ANSWER_RATE_LIMITED, ANSWER_READY

SYSTEM_PROMPT = """You are a legal research assistant specialising in
Pakistan Supreme Court judgments. You will be given:
1. The user's query - either a legal question, or a description of their own
   case situation in their own words (what happened, what each side claims,
   what the courts held, the outcome)
2. Relevant sections from one court judgment

Your task is to answer using ONLY the provided judgment text.
Structure your answer with these exact headings:
[RELEVANT FACTS]
[LEGAL ISSUE]
[COURT REASONING]
[FINAL DECISION]
[KEY PRINCIPLE]
[FIT WITH YOUR SITUATION]

FIRST, decide whether the judgment text is about the same subject matter as
the query. This is the most important judgement you make.

If it is NOT - if the query asks about a case, a party, a situation or an area
of law the judgment text does not concern - reply with exactly this and
nothing else:

[NO RELEVANT AUTHORITY]
The retrieved judgments do not address this query.

Do not fill any heading in that case. In particular, do not report a
disposition. A disposition belongs to the case that produced it: reporting
"appeal allowed" from an unrelated judgment tells the researcher that their
case was allowed, which is a fabrication even though every word came from the
context.

If the judgment text IS about the same subject matter, fill every heading the
text supports. Report what the judgment actually decided, even where that is
narrower than the question asked: if the Court disposed of the case on a
different ground, state that ground rather than declining to answer.

[FINAL DECISION] states the disposition of the judgment being discussed, and
only where that judgment is genuinely responsive to the query.

[FIT WITH YOUR SITUATION] checks the judgment against what the user described.
Compare the material facts, the statute or forum, the stage of proceedings and
the outcome. Say plainly which of them match and which differ - for example a
different relationship between the parties, a different statute, a High Court
result the Supreme Court reversed, or the opposite outcome. Do not stretch the
judgment to fit: where a difference would decide the matter, begin with
"Distinguishable:" and name the difference. Where the facts and outcome
genuinely correspond, begin with "Closely matches:". If the query is a short
legal question rather than a description of a situation, write
"Not applicable." under this heading.

Reserve "Not found in retrieved judgments." for a heading the judgment text
genuinely does not support. Never state a fact, holding, citation or outcome
that is absent from the context, and never attribute to the user facts they
did not describe.

Be precise and formal."""

# What the model emits when the context does not concern the query, and what
# the pipeline turns that into.
NO_AUTHORITY_MARKER = "[NO RELEVANT AUTHORITY]"

SUMMARY_SYSTEM_PROMPT = """You are a legal research assistant specialising in
Pakistan Supreme Court judgments. Summarise this judgment in one paragraph
covering: case type, parties, core legal issue, court decision, and key
principle. Use formal legal English. Use only the provided judgment text."""

# Low but non-zero: factual legal answers, not creative ones.
TEMPERATURE = 0.1

# Enough for the five-heading answer without letting a local model ramble.
MAX_ANSWER_TOKENS = 1200
MAX_SUMMARY_TOKENS = 400

# Local models are considerably slower than a hosted endpoint.
REQUEST_TIMEOUT = 180

ERROR_RESPONSE = "Error: Could not generate answer. Please try again."

NO_AUTHORITY_ANSWER = (
    "[NO RELEVANT AUTHORITY]" + chr(10) +
    "The retrieved judgments do not address this query."
)

NOT_FOUND_PHRASE = "not found in retrieved judgments"

# The headings that carry substance. If all of them came back empty, the
# judgment is not about the query and nothing may be reported from it.
SUBSTANTIVE_HEADINGS = ("[RELEVANT FACTS]", "[LEGAL ISSUE]", "[COURT REASONING]")
FIT_HEADING = "[FIT WITH YOUR SITUATION]"
ALL_HEADINGS = SUBSTANTIVE_HEADINGS + ("[FINAL DECISION]", "[KEY PRINCIPLE]", FIT_HEADING)

# What a summary shows instead when the shared quota is spent or generation
# failed. Never the provider's error text.
BUSY_MESSAGE = "The service is busy right now. Please try again in a minute."
FAILED_MESSAGE = "The summary could not be generated. Please try again."


class LLMText(str):
    """A completion's text that also says how it came about.

    Equal to the generated text when ``status`` is ready, and to
    ERROR_RESPONSE otherwise, so existing ``== ERROR_RESPONSE`` checks keep
    working. ``status`` is one of contracts.ANSWER_STATUSES.
    """

    status: str
    detail: str

    def __new__(cls, text: str, status: str = ANSWER_READY, detail: str = ""):
        obj = super().__new__(cls, text)
        obj.status = status
        obj.detail = detail
        return obj


def status_of(response: str | None) -> str:
    """The ANSWER_STATUSES value for anything _complete (or a wrapper of it) returned.

    A plain string - e.g. the evaluation guard's sentinel - is classified by
    content: the error sentinel or nothing is an error, anything else is ready.
    """
    status = getattr(response, "status", None)
    if status:
        return status
    if not response or response == ERROR_RESPONSE:
        return ANSWER_ERROR
    return ANSWER_READY


def _section_of(answer: str, heading: str) -> str:
    """Return the text under one heading, or "" if the heading is absent."""
    if heading not in answer:
        return ""
    after = answer.split(heading, 1)[1]
    for other in ALL_HEADINGS:
        if other in after:
            after = after.split(other, 1)[0]
    return after.strip()


def _is_unsupported(answer: str) -> bool:
    """True when every substantive heading is empty but a disposition remains.

    This is the exact shape of the failure being guarded against: facts, issue
    and reasoning all "not found", yet [FINAL DECISION] confidently reporting
    that an appeal was allowed.
    """
    if NO_AUTHORITY_MARKER in answer:
        return False

    filled = [
        h for h in SUBSTANTIVE_HEADINGS
        if (text := _section_of(answer, h)) and NOT_FOUND_PHRASE not in text.lower()
    ]
    if filled:
        return False

    decision = _section_of(answer, "[FINAL DECISION]")
    return bool(decision) and NOT_FOUND_PHRASE not in decision.lower()

_clients: dict[str, AsyncOpenAI] = {}
_gemini_client: genai.Client | None = None


def _get_gemini_client() -> genai.Client:
    """Return cached Gemini client instance."""
    global _gemini_client
    if _gemini_client is None:
        api_key = getattr(settings, "GEMINI_API_KEY", "") or ""
        _gemini_client = genai.Client(api_key=api_key) if api_key else genai.Client()
    return _gemini_client


def _resolve_provider(provider: str | None) -> str:
    """Return the provider to use for a call, defaulting to the configured one."""
    return (provider or settings.LLM_PROVIDER or "gemini").strip().lower()


def _client_for(provider: str) -> tuple[AsyncOpenAI, str]:
    """Return a cached client and model name for `provider`."""
    if provider == "ollama":
        base_url = settings.OLLAMA_BASE_URL
        model = settings.OLLAMA_MODEL
        # Ollama ignores the key, but the OpenAI client requires a non-empty one.
        api_key = "ollama"
    else:
        # =====================================================================
        # Groq Setup (Commented out as requested - Switched to Google Gemini)
        # =====================================================================
        # base_url = settings.GROQ_BASE_URL
        # model = settings.GROQ_MODEL
        # api_key = settings.GROQ_API_KEY
        # if "groq" not in _clients:
        #     _clients["groq"] = AsyncOpenAI(base_url=base_url, api_key=api_key, max_retries=3)
        base_url = settings.GROQ_BASE_URL
        model = settings.GROQ_MODEL
        api_key = settings.GROQ_API_KEY

    if provider not in _clients:
        _clients[provider] = AsyncOpenAI(
            base_url=base_url,
            api_key=api_key,
            # The limiter owns retrying (with the shared budget and the
            # provider's retry-after); SDK retries would spend quota blindly.
            max_retries=0,
        )
    return _clients[provider], model


def build_user_prompt(query: str, context: str) -> str:
    """Frame the query and retrieved context as the user turn."""
    return (
        f"---\n"
        f"USER'S QUERY OR SITUATION (as the user wrote it):\n{query}\n\n"
        f"JUDGMENT CONTEXT:\n{context}\n"
        f"---\n"
        f"Answer using only the judgment context above, and check it against "
        f"the user's situation under [FIT WITH YOUR SITUATION]."
    )


async def _provider_call(
    system_prompt: str,
    user_prompt: str,
    max_tokens: int,
    provider: str | None = None,
) -> str:
    """One raw completion. Raises on any provider failure (429s included).

    No retry, no swallowing: the limiter classifies the exception. This is the
    single seam a test replaces with a fake LLM.
    """
    resolved = _resolve_provider(provider)

    if resolved == "gemini":
        model = settings.GEMINI_MODEL or "gemini-2.5-flash-lite"
        client = _get_gemini_client()
        # Bounded: a hung request would otherwise hold one of the limiter's
        # few concurrency slots for good. A timeout counts as transient.
        response = await asyncio.wait_for(
            client.aio.models.generate_content(
                model=model,
                contents=user_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    temperature=TEMPERATURE,
                    max_output_tokens=max_tokens,
                ),
            ),
            timeout=float(getattr(settings, "LLM_REQUEST_TIMEOUT_S", 60.0) or 60.0),
        )
        return (response.text or "").strip()

    # OpenAI-compatible (Ollama / Groq when passed explicitly). The client's own
    # retries are off: the limiter owns retrying, with the shared budget.
    client, model = _client_for(resolved)
    response = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=TEMPERATURE,
        max_tokens=max_tokens,
        timeout=REQUEST_TIMEOUT,
    )
    return (response.choices[0].message.content or "").strip()


async def _complete(
    system_prompt: str,
    user_prompt: str,
    max_tokens: int,
    provider: str | None = None,
    *,
    max_wait: float | None = None,
    label: str = "llm",
) -> LLMText:
    """Run one completion through the shared limiter.

    Returns an :class:`LLMText`: the generated text with status "ready", or
    ERROR_RESPONSE with status "rate_limited" / "error" and a ``detail``.
    Never raises for provider failures.
    """
    resolved = _resolve_provider(provider)

    async def call() -> str:
        # Looked up at call time so a test's replacement takes effect.
        return await _provider_call(system_prompt, user_prompt, max_tokens, resolved)

    outcome = await get_limiter().run(call, max_wait=max_wait, label=f"{label}/{resolved}")
    if outcome.ok:
        return LLMText(outcome.text, ANSWER_READY)
    return LLMText(ERROR_RESPONSE, outcome.status, outcome.detail)


async def generate_answer(query: str, context: str, provider: str | None = None) -> LLMText:
    """Answer a legal query, or analyse a described situation, from one judgment.

    Args:
        query: The user's query or situation description, as typed (raw, not
            the keyword-cleaned form: the fit check needs the user's facts).
        context: The assembled judgment context.
        provider: Override for LLM_PROVIDER ("groq" or "ollama").

    Returns:
        An :class:`LLMText`. ``status`` is "ready" with the structured answer,
        or "rate_limited" / "error" with the text equal to ERROR_RESPONSE.
    """
    response = await _complete(
        SYSTEM_PROMPT,
        build_user_prompt(query, context),
        MAX_ANSWER_TOKENS,
        provider,
        label="answer",
    )
    status = status_of(response)
    if status != ANSWER_READY:
        return response if isinstance(response, LLMText) else LLMText(ERROR_RESPONSE, status)

    # Guard the case the prompt is meant to prevent. If the model reported
    # nothing under every substantive heading but still produced a disposition,
    # that disposition came from an unrelated judgment and must not be shown.
    if _is_unsupported(response):
        logger.warning(
            "Answer found nothing under every heading but still reported a "
            "disposition; suppressing it as unattributable."
        )
        return LLMText(NO_AUTHORITY_ANSWER, ANSWER_READY)

    logger.info(f"LLM answer generated. Length: {len(response)} chars")
    return response if isinstance(response, LLMText) else LLMText(response, ANSWER_READY)


async def generate_summary(context: str, provider: str | None = None) -> LLMText:
    """Summarise a judgment in a single formal paragraph.

    Args:
        context: The assembled judgment context.
        provider: Override for LLM_PROVIDER ("groq" or "ollama").

    Returns:
        An :class:`LLMText`: the summary with status "ready", or a plain-English
        busy / failed message (never provider error text) with that status.
    """
    response = await _complete(
        SUMMARY_SYSTEM_PROMPT,
        f"JUDGMENT CONTEXT:\n{context}",
        MAX_SUMMARY_TOKENS,
        provider,
        label="summary",
    )
    status = status_of(response)
    if status == ANSWER_RATE_LIMITED:
        return LLMText(BUSY_MESSAGE, status, getattr(response, "detail", ""))
    if status != ANSWER_READY:
        return LLMText(FAILED_MESSAGE, status, getattr(response, "detail", ""))
    logger.info(f"LLM summary generated. Length: {len(response)} chars")
    return response if isinstance(response, LLMText) else LLMText(response, ANSWER_READY)


if __name__ == "__main__":
    # Offline by default: the provider seam is replaced with fakes, so this
    # spends no quota. `--live` adds one real answer and one real summary.
    import asyncio

    from app.llm import limiter as limiter_module

    _REAL_PROVIDER_CALL = _provider_call

    fake_context = """
=== FACTS ===
The accused was arrested for murder in 2019.

=== ANALYSIS RATIO ===
The court found the evidence to be insufficient.

=== FINAL ORDER ===
Bail was granted.
"""
    GOOD = ("[RELEVANT FACTS]\nArrested 2019.\n[LEGAL ISSUE]\nBail.\n[COURT REASONING]\nWeak evidence.\n"
            "[FINAL DECISION]\nBail granted.\n[KEY PRINCIPLE]\nDoubt favours the accused.\n"
            "[FIT WITH YOUR SITUATION]\nDistinguishable: the user was not arrested.")
    UNSUPPORTED = ("[RELEVANT FACTS]\nNot found in retrieved judgments.\n[LEGAL ISSUE]\nNot found in retrieved "
                   "judgments.\n[COURT REASONING]\nNot found in retrieved judgments.\n"
                   "[FINAL DECISION]\nAppeal allowed.")

    class Fake429(Exception):
        code = 429

    async def offline() -> None:
        global _provider_call
        seen: dict = {}

        async def fake(system_prompt, user_prompt, max_tokens, provider=None):
            seen["system"], seen["user"] = system_prompt, user_prompt
            return seen.get("reply", GOOD)

        _provider_call = fake
        limiter_module._limiter = limiter_module.LLMLimiter(rpm=100, concurrency=3, max_wait=0.5, period=1.0)

        raw = "My client was refused bail although the only witness retracted. The High Court said..."
        answer = await generate_answer(raw, fake_context)
        assert answer.status == ANSWER_READY and answer == GOOD, answer
        assert raw in seen["user"], "the raw description must reach the model"
        assert FIT_HEADING in SYSTEM_PROMPT and NO_AUTHORITY_MARKER in SYSTEM_PROMPT
        assert "Distinguishable:" in SYSTEM_PROMPT
        assert _section_of(answer, "[KEY PRINCIPLE]") == "Doubt favours the accused.", \
            "the fit heading leaked into the previous section"

        seen["reply"] = UNSUPPORTED
        guarded = await generate_answer(raw, fake_context)
        assert guarded == NO_AUTHORITY_ANSWER and guarded.status == ANSWER_READY, guarded

        async def limited(*_a, **_k):
            raise Fake429("429 RESOURCE_EXHAUSTED. Please retry in 30s.")

        _provider_call = limited
        busy = await generate_answer(raw, fake_context)
        assert busy.status == ANSWER_RATE_LIMITED and busy == ERROR_RESPONSE, (busy.status, busy)
        summary = await generate_summary(fake_context)
        assert summary.status == ANSWER_RATE_LIMITED and summary == BUSY_MESSAGE, summary
        limiter_module._limiter.window.blocked_until = 0.0

        async def broken(*_a, **_k):
            raise ValueError("400 INVALID_ARGUMENT")

        _provider_call = broken
        failed = await generate_answer(raw, fake_context)
        assert failed.status == ANSWER_ERROR and failed == ERROR_RESPONSE
        assert status_of("plain text answer") == ANSWER_READY and status_of(ERROR_RESPONSE) == ANSWER_ERROR
        print("OK: answer generation verified offline (prompt, guard, rate_limited, error).")

    async def live() -> None:
        answer = await generate_answer("Why was bail granted?", fake_context)
        print(answer)
        assert answer.status == ANSWER_READY, (answer.status, answer.detail)
        for heading in ALL_HEADINGS[:5]:
            assert heading in answer, f"missing heading: {heading}"
        summary = await generate_summary(fake_context)
        print(f"\n--- SUMMARY ---\n{summary}")
        assert summary.status == ANSWER_READY, summary.detail
        print("\nOK: live answer generation verified.")

    asyncio.run(offline())
    if "--live" in sys.argv:
        limiter_module._limiter = None
        globals()["_provider_call"] = _REAL_PROVIDER_CALL
        asyncio.run(live())
