"""
matching-svc tests — embedding generation idempotency + client wrapper.

Tests:
  - build_profile_text assembles fields correctly
  - is_cold_start detection
  - EmbeddingClient.generate: success, retry on 429, failure after 4 attempts
  - EmbeddingClient.generate_batch: chunks correctly
  - Idempotency: same text → same vector (deterministic from OpenAI's side)
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch, call

import httpx
import pytest
import respx

from app.services.embeddings import (
    EmbeddingClient,
    build_profile_text,
    is_cold_start,
    get_embedding_client,
)


# ---------------------------------------------------------------------------
# Profile text assembly
# ---------------------------------------------------------------------------

class TestBuildProfileText:
    def test_all_fields(self):
        text = build_profile_text(
            bio="Indie filmmaker",
            obsessed_with="Cinematic storytelling",
            vocation_tags=["Filmmaker", "Cinematographer"],
            portfolio_captions=["Festival film 2024", "Music video"],
        )
        assert "Indie filmmaker" in text
        assert "Cinematic storytelling" in text
        assert "Filmmaker, Cinematographer" in text
        assert "Festival film 2024" in text
        assert "\n" in text  # fields joined with newlines

    def test_none_fields_omitted(self):
        text = build_profile_text(bio="Bio only", obsessed_with=None, vocation_tags=None, portfolio_captions=None)
        assert text == "Bio only"

    def test_empty_string_fields_omitted(self):
        text = build_profile_text(bio="   ", obsessed_with="", vocation_tags=[], portfolio_captions=[])
        assert text == ""

    def test_empty_vocation_tags_skipped(self):
        text = build_profile_text(bio="Bio", obsessed_with=None, vocation_tags=["", None], portfolio_captions=None)
        assert "Bio" in text
        # Empty/None tags should not add a line
        assert text.strip() == "Bio"

    def test_portfolio_captions_joined_with_space(self):
        text = build_profile_text(bio=None, obsessed_with=None, vocation_tags=None, portfolio_captions=["Cap1", "Cap2"])
        assert "Cap1 Cap2" in text


class TestIsColdStart:
    def test_empty_string_is_cold_start(self):
        assert is_cold_start("") is True

    def test_whitespace_is_cold_start(self):
        assert is_cold_start("   ") is True

    def test_none_is_cold_start(self):
        assert is_cold_start(None) is True  # type: ignore

    def test_non_empty_not_cold_start(self):
        assert is_cold_start("Hello") is False


# ---------------------------------------------------------------------------
# EmbeddingClient.generate
# ---------------------------------------------------------------------------

FAKE_EMBEDDING = [0.1] * 3072


def _mock_openai_response(embedding: list[float] | None = None) -> dict:
    return {
        "object": "list",
        "data": [{"index": 0, "embedding": embedding or FAKE_EMBEDDING, "object": "embedding"}],
        "model": "text-embedding-3-large",
        "usage": {"prompt_tokens": 10, "total_tokens": 10},
    }


class TestEmbeddingClientGenerate:
    @pytest.mark.asyncio
    async def test_generate_success(self):
        with respx.mock:
            respx.post("https://api.openai.com/v1/embeddings").mock(
                return_value=httpx.Response(200, json=_mock_openai_response())
            )
            client = EmbeddingClient(api_key="test-key", model="text-embedding-3-large", dimensions=3072)
            vector = await client.generate("Test text")

        assert len(vector) == 3072
        assert vector[0] == 0.1

    @pytest.mark.asyncio
    async def test_generate_no_api_key_raises(self):
        client = EmbeddingClient(api_key="", model="text-embedding-3-large", dimensions=3072)
        with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
            await client.generate("test")

    @pytest.mark.asyncio
    async def test_generate_idempotency(self):
        """Same text → same vector (mocked to return identical response)."""
        with respx.mock:
            respx.post("https://api.openai.com/v1/embeddings").mock(
                return_value=httpx.Response(200, json=_mock_openai_response(FAKE_EMBEDDING))
            )
            client = EmbeddingClient(api_key="test-key", model="text-embedding-3-large", dimensions=3072)
            v1 = await client.generate("Cinematic storytelling")

        with respx.mock:
            respx.post("https://api.openai.com/v1/embeddings").mock(
                return_value=httpx.Response(200, json=_mock_openai_response(FAKE_EMBEDDING))
            )
            v2 = await client.generate("Cinematic storytelling")

        assert v1 == v2  # Deterministic from same mock

    @pytest.mark.asyncio
    async def test_generate_retries_on_429(self):
        """429 response triggers retry with retry-after delay."""
        call_count = 0

        def _side_effect(request):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return httpx.Response(429, headers={"retry-after": "0"}, json={"error": "rate_limited"})
            return httpx.Response(200, json=_mock_openai_response())

        with respx.mock:
            respx.post("https://api.openai.com/v1/embeddings").mock(side_effect=_side_effect)
            client = EmbeddingClient(api_key="test-key", model="text-embedding-3-large", dimensions=3072)

            with patch("asyncio.sleep", new_callable=AsyncMock):
                vector = await client.generate("test")

        assert len(vector) == 3072
        assert call_count == 2  # 1 rate-limited + 1 success

    @pytest.mark.asyncio
    async def test_generate_fails_after_4_attempts(self):
        """Persistent failures raise RuntimeError after 4 attempts."""
        with respx.mock:
            respx.post("https://api.openai.com/v1/embeddings").mock(
                return_value=httpx.Response(500, json={"error": "server error"})
            )
            client = EmbeddingClient(api_key="test-key", model="text-embedding-3-large", dimensions=3072)

            with patch("asyncio.sleep", new_callable=AsyncMock):
                with pytest.raises(RuntimeError, match="Embedding generation failed"):
                    await client.generate("test")


# ---------------------------------------------------------------------------
# EmbeddingClient.generate_batch
# ---------------------------------------------------------------------------

class TestEmbeddingClientBatch:
    @pytest.mark.asyncio
    async def test_batch_returns_all_embeddings(self):
        texts = ["text1", "text2", "text3"]
        batch_response = {
            "data": [
                {"index": i, "embedding": [float(i)] * 3072, "object": "embedding"}
                for i in range(len(texts))
            ]
        }

        with respx.mock:
            respx.post("https://api.openai.com/v1/embeddings").mock(
                return_value=httpx.Response(200, json=batch_response)
            )
            client = EmbeddingClient(api_key="test-key", model="text-embedding-3-large", dimensions=3072)
            results = await client.generate_batch(texts)

        assert len(results) == 3
        assert results[0] == [0.0] * 3072
        assert results[1] == [1.0] * 3072

    @pytest.mark.asyncio
    async def test_batch_empty_returns_empty(self):
        client = EmbeddingClient(api_key="test-key", model="text-embedding-3-large", dimensions=3072)
        results = await client.generate_batch([])
        assert results == []


# ---------------------------------------------------------------------------
# Module singleton
# ---------------------------------------------------------------------------

class TestGetEmbeddingClientSingleton:
    def test_singleton_returns_same_instance(self):
        c1 = get_embedding_client()
        c2 = get_embedding_client()
        assert c1 is c2
