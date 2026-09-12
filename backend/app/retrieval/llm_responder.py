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
"""

import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from loguru import logger
from openai import AsyncOpenAI
from google import genai
from google.genai import types

from app.config import settings

SYSTEM_PROMPT = """You are a legal research assistant specialising in
Pakistan Supreme Court judgments. You will be given:
1. A legal query from a researcher
2. Relevant sections from one or more court judgments

Your task is to answer the query using ONLY the provided judgment text.
Structure your answer with these exact headings:
[RELEVANT FACTS]
[LEGAL ISSUE]
[COURT REASONING]
[FINAL DECISION]
[KEY PRINCIPLE]

Fill every heading from the judgment text wherever the text supports it.
Report what the judgment actually decided, even where that is narrower than
the question asked: if the Court disposed of the case on a different ground,
state that ground rather than declining to answer.

[FINAL DECISION] must state the disposition whenever the context records one
- "appeal allowed", "appeal dismissed", "matter remanded", and so on - including
when that disposition does not address the query directly.

Reserve "Not found in retrieved judgments." for a heading the judgment text
genuinely does not support. Never state a fact, holding, citation or outcome
that is absent from the context.

Be precise and formal."""

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
            max_retries=3,
        )
    return _clients[provider], model


def build_user_prompt(query: str, context: str) -> str:
    """Frame the query and retrieved context as the user turn."""
    return (
        f"---\n"
        f"LEGAL QUERY:\n{query}\n\n"
        f"JUDGMENT CONTEXT:\n{context}\n"
        f"---\n"
        f"Answer the legal query using only the judgment context above."
    )


async def _complete(
    system_prompt: str,
    user_prompt: str,
    max_tokens: int,
    provider: str | None = None,
) -> str:
    """Run one chat completion, returning the error sentinel on any failure."""
    resolved = _resolve_provider(provider)

    # 1. Primary: Google Gemini 2.5 Flash-Lite Provider
    if resolved == "gemini":
        model = settings.GEMINI_MODEL or "gemini-2.5-flash-lite"
        try:
            client = _get_gemini_client()
            response = await client.aio.models.generate_content(
                model=model,
                contents=user_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    temperature=TEMPERATURE,
                    max_output_tokens=max_tokens,
                ),
            )
            content = (response.text or "").strip()
            if not content:
                logger.error(f"Gemini returned an empty response via {model}")
                return ERROR_RESPONSE
            return content
        except Exception as e:
            logger.error(f"Gemini API call failed via {model}: {e}")
            return ERROR_RESPONSE

    # 2. Fallback / Secondary: OpenAI-compatible (Ollama / Groq if passed)
    client, model = _client_for(resolved)

    try:
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
        content = (response.choices[0].message.content or "").strip()
    except Exception as e:
        # A generation failure must not take down the request; the pipeline
        # still has its retrieved context to return.
        logger.error(f"LLM call failed via {resolved}/{model}: {e}")
        return ERROR_RESPONSE

    if not content:
        logger.error(f"LLM returned an empty response via {resolved}/{model}")
        return ERROR_RESPONSE

    return content


async def generate_answer(query: str, context: str, provider: str | None = None) -> str:
    """Answer a legal query from the retrieved judgment context.

    Args:
        query: The researcher's question, as typed.
        context: The assembled judgment context.
        provider: Override for LLM_PROVIDER ("groq" or "ollama").

    Returns:
        The structured answer, or an error sentinel if generation failed.
    """
    response = await _complete(
        SYSTEM_PROMPT,
        build_user_prompt(query, context),
        MAX_ANSWER_TOKENS,
        provider,
    )
    logger.info(f"LLM answer generated. Length: {len(response)} chars")
    return response


async def generate_summary(context: str, provider: str | None = None) -> str:
    """Summarise a judgment in a single formal paragraph.

    Args:
        context: The assembled judgment context.
        provider: Override for LLM_PROVIDER ("groq" or "ollama").

    Returns:
        The summary, or an error sentinel if generation failed.
    """
    response = await _complete(
        SUMMARY_SYSTEM_PROMPT,
        f"JUDGMENT CONTEXT:\n{context}",
        MAX_SUMMARY_TOKENS,
        provider,
    )
    logger.info(f"LLM summary generated. Length: {len(response)} chars")
    return response


if __name__ == "__main__":
    import asyncio

    fake_context = """
=== FACTS ===
The accused was arrested for murder in 2019.

=== ANALYSIS RATIO ===
The court found the evidence to be insufficient.

=== FINAL ORDER ===
Bail was granted.
"""

    async def main() -> None:
        answer = await generate_answer("Why was bail granted?", fake_context)
        print(answer)

        assert answer != ERROR_RESPONSE, "generation failed"
        for heading in ("[RELEVANT FACTS]", "[LEGAL ISSUE]", "[COURT REASONING]",
                        "[FINAL DECISION]", "[KEY PRINCIPLE]"):
            assert heading in answer, f"missing heading: {heading}"

        summary = await generate_summary(fake_context)
        print(f"\n--- SUMMARY ---\n{summary}")
        assert summary != ERROR_RESPONSE, "summary failed"

        print("\nOK: answer generation verified.")

    asyncio.run(main())
