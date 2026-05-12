"""
OpenAI client wrapper with retry logic and structured error logging.

Handles: /summarize-chat, /brainstorm, /palette text commands.
Retry: 2 retries with 2s / 4s exponential backoff.
Timeout: 30s.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

import openai
from openai import AsyncOpenAI

from app.config import get_ai_settings

logger = logging.getLogger(__name__)

_client: AsyncOpenAI | None = None


def get_openai_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        settings = get_ai_settings()
        _client = AsyncOpenAI(
            api_key=settings.openai_api_key,
            timeout=settings.openai_timeout_seconds,
            max_retries=0,  # We handle retries manually for better logging
        )
    return _client


async def chat_complete(
    messages: list[dict[str, str]],
    model: str | None = None,
    max_tokens: int = 1000,
) -> tuple[str, int, int]:
    """
    Call OpenAI chat completions with manual retry (2 retries, 2s/4s backoff).

    Returns: (content, input_tokens, output_tokens)
    Raises: openai.APIError after exhausting retries.
    """
    settings = get_ai_settings()
    client = get_openai_client()
    effective_model = model or settings.openai_model_text

    last_exc: Exception | None = None
    for attempt in range(settings.openai_max_retries + 1):
        try:
            response = await client.chat.completions.create(
                model=effective_model,
                messages=messages,  # type: ignore[arg-type]
                max_tokens=max_tokens,
                temperature=0.7,
            )
            content = response.choices[0].message.content or ""
            input_tokens = response.usage.prompt_tokens if response.usage else 0
            output_tokens = response.usage.completion_tokens if response.usage else 0
            return content, input_tokens, output_tokens
        except (openai.RateLimitError, openai.APIStatusError, openai.APIConnectionError) as exc:
            last_exc = exc
            if attempt < settings.openai_max_retries:
                wait = 2 ** attempt * 2  # 2s, 4s
                logger.warning("OpenAI attempt %d failed (%s), retrying in %ds", attempt + 1, exc, wait)
                await asyncio.sleep(wait)
            else:
                logger.error("OpenAI exhausted retries: %s", exc)

    raise last_exc or RuntimeError("OpenAI call failed after retries")


async def moderate_text(text: str) -> float:
    """Run OpenAI moderation on text. Returns max score across categories."""
    client = get_openai_client()
    try:
        resp = await client.moderations.create(input=text)
        result = resp.results[0]
        scores = result.category_scores.model_dump()
        return max(scores.values()) if scores else 0.0
    except Exception as exc:
        logger.warning("Moderation check failed: %s — passing through", exc)
        return 0.0
