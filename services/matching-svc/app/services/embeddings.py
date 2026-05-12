"""
matching-svc — OpenAI text-embedding-3-large client wrapper.

Generates 3072-dimensional embeddings from concatenated profile text fields:
  {bio}\n{obsessed_with}\n{vocation_tags_joined}\n{portfolio_captions_joined}

Per plan §2.4:
  - Model: text-embedding-3-large (3072 dims, full fidelity)
  - Cost: ~$0.13/1M tokens; ~300 tokens/profile → negligible
  - Incremental: re-embed only when profile text changes (event-driven)
  - Version column on profile_embeddings for upgrade path

Idempotency: calling generate_embedding() with the same text returns the same
vector (deterministic from OpenAI's side per same input + model version).
The caller is responsible for deduplication against stored embedding.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)
_settings = get_settings()

# ---------------------------------------------------------------------------
# Profile text assembly
# ---------------------------------------------------------------------------

def build_profile_text(
    bio: str | None,
    obsessed_with: str | None,
    vocation_tags: list[str] | None,
    portfolio_captions: list[str] | None,
) -> str:
    """
    Concatenate profile text fields into the input string for embedding.

    Empty / None fields are omitted so the embedding is not diluted by
    blank-string noise. At least one field should be non-empty; callers
    should detect zero-content profiles and skip embedding generation.
    """
    parts: list[str] = []
    if bio and bio.strip():
        parts.append(bio.strip())
    if obsessed_with and obsessed_with.strip():
        parts.append(obsessed_with.strip())
    if vocation_tags:
        joined = ", ".join(t for t in vocation_tags if t)
        if joined:
            parts.append(joined)
    if portfolio_captions:
        joined = " ".join(c for c in portfolio_captions if c and c.strip())
        if joined.strip():
            parts.append(joined.strip())
    return "\n".join(parts)


def is_cold_start(text: str) -> bool:
    """Return True if the profile has no meaningful text for embedding."""
    return not text or not text.strip()


# ---------------------------------------------------------------------------
# OpenAI client
# ---------------------------------------------------------------------------

class EmbeddingClient:
    """
    Thin async wrapper around the OpenAI Embeddings API.

    Uses httpx directly (no openai SDK import in hot path) to avoid the
    extra SDK overhead; retries on transient 429 / 5xx with exponential
    backoff (3 attempts, 1s/2s/4s delays).
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        dimensions: int | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._api_key = api_key or _settings.openai_api_key
        self._model = model or _settings.openai_embedding_model
        self._dimensions = dimensions or _settings.openai_embedding_dimensions
        self._timeout = timeout
        self._base_url = "https://api.openai.com/v1"

    async def generate(self, text: str) -> list[float]:
        """
        Generate an embedding vector for the given text.

        Returns a list of floats (length = self._dimensions).
        Raises RuntimeError on persistent API failure.

        Idempotency note: the same (text, model, dimensions) triple always
        yields the same vector from OpenAI's API — no client-side caching
        needed. Callers should check DB for stored vector before calling.
        """
        if not self._api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is not configured; cannot generate embeddings"
            )

        payload: dict[str, Any] = {
            "model": self._model,
            "input": text,
            "dimensions": self._dimensions,
            "encoding_format": "float",
        }

        last_error: Exception | None = None
        for attempt, delay in enumerate([0, 1, 2, 4]):
            if attempt > 0:
                import asyncio
                await asyncio.sleep(delay)
            try:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    response = await client.post(
                        f"{self._base_url}/embeddings",
                        json=payload,
                        headers={
                            "Authorization": f"Bearer {self._api_key}",
                            "Content-Type": "application/json",
                        },
                    )
                    if response.status_code == 429:
                        retry_after = int(response.headers.get("retry-after", delay + 1))
                        import asyncio
                        await asyncio.sleep(retry_after)
                        last_error = RuntimeError(f"rate limited (attempt {attempt})")
                        continue
                    response.raise_for_status()
                    data = response.json()
                    vector: list[float] = data["data"][0]["embedding"]
                    logger.debug(
                        "embedding generated: model=%s dims=%d text_len=%d",
                        self._model, len(vector), len(text),
                    )
                    return vector
            except (httpx.HTTPStatusError, httpx.RequestError) as exc:
                last_error = exc
                logger.warning("embedding attempt %d failed: %s", attempt + 1, exc)
                if attempt == 3:
                    break

        raise RuntimeError(
            f"Embedding generation failed after 4 attempts: {last_error}"
        )

    async def generate_batch(self, texts: list[str]) -> list[list[float]]:
        """
        Generate embeddings for a batch of texts.

        OpenAI accepts up to 2048 input strings per request. We chunk at
        100 to stay well within token limits and avoid rate-limit spikes.
        """
        CHUNK = 100
        results: list[list[float]] = []
        for i in range(0, len(texts), CHUNK):
            batch = texts[i : i + CHUNK]
            payload: dict[str, Any] = {
                "model": self._model,
                "input": batch,
                "dimensions": self._dimensions,
                "encoding_format": "float",
            }
            last_error: Exception | None = None
            for attempt, delay in enumerate([0, 1, 2, 4]):
                if attempt > 0:
                    import asyncio
                    await asyncio.sleep(delay)
                try:
                    async with httpx.AsyncClient(timeout=self._timeout) as client:
                        response = await client.post(
                            f"{self._base_url}/embeddings",
                            json=payload,
                            headers={
                                "Authorization": f"Bearer {self._api_key}",
                                "Content-Type": "application/json",
                            },
                        )
                        if response.status_code == 429:
                            retry_after = int(response.headers.get("retry-after", delay + 1))
                            import asyncio as _asyncio
                            await _asyncio.sleep(retry_after)
                            last_error = RuntimeError("rate limited")
                            continue
                        response.raise_for_status()
                        data = response.json()
                        batch_vectors = [item["embedding"] for item in sorted(data["data"], key=lambda x: x["index"])]
                        results.extend(batch_vectors)
                        break
                except (httpx.HTTPStatusError, httpx.RequestError) as exc:
                    last_error = exc
                    if attempt == 3:
                        raise RuntimeError(
                            f"Batch embedding failed after 4 attempts: {last_error}"
                        )
        return results


# Module-level singleton (lazy init)
_client: EmbeddingClient | None = None


def get_embedding_client() -> EmbeddingClient:
    global _client
    if _client is None:
        _client = EmbeddingClient()
    return _client
