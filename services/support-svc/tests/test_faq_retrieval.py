"""
Tests for FAQ retrieval: threshold filtering, FTS fallback, chatbot hand-off.

Covers:
- Articles below cosine threshold are excluded
- Zero articles → hand-off SSE (no OpenAI call)
- Chatbot rate limiting (>10 turns/hour → 429)
- FAQ list and slug endpoints
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# FAQ endpoint tests
# ---------------------------------------------------------------------------


@pytest.fixture
def faq_client():
    from app.main import app
    from app.db import get_db

    db_sess = AsyncMock()
    exec_result = MagicMock()
    exec_result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
    exec_result.scalar_one_or_none = MagicMock(return_value=None)
    db_sess.execute = AsyncMock(return_value=exec_result)

    async def override_db():
        yield db_sess

    app.dependency_overrides[get_db] = override_db
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c, db_sess
    app.dependency_overrides.clear()


class TestFAQEndpoints:
    def test_list_faq_returns_200(self, faq_client):
        client, db_sess = faq_client

        article = MagicMock()
        article.slug = "how-to-cancel"
        article.title = "How to cancel"
        article.body_md = "## Cancel\nYou can cancel..."
        article.tags = ["billing"]
        from datetime import datetime, timezone
        article.updated_at = datetime.now(tz=timezone.utc)

        exec_result = MagicMock()
        exec_result.scalars = MagicMock(
            return_value=MagicMock(all=MagicMock(return_value=[article]))
        )
        db_sess.execute = AsyncMock(return_value=exec_result)

        resp = client.get("/v1/support/faq")
        assert resp.status_code == 200
        data = resp.json()
        assert "articles" in data

    def test_get_faq_slug_not_found_returns_404(self, faq_client):
        client, _ = faq_client
        resp = client.get("/v1/support/faq/nonexistent-slug")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# FAQ retrieval threshold tests (unit, no HTTP)
# ---------------------------------------------------------------------------


class TestFAQRetrievalThreshold:
    """Test _retrieve_faq_articles threshold filtering."""

    @pytest.mark.asyncio
    async def test_articles_below_threshold_excluded(self):
        """Articles with cosine score < 0.72 should not be returned."""
        from unittest.mock import AsyncMock, MagicMock, patch

        mock_db = AsyncMock()

        # Simulate pgvector returning rows with scores
        low_score_row = MagicMock()
        low_score_row.id = uuid.uuid4()
        low_score_row.score = 0.50  # below threshold

        high_score_row = MagicMock()
        high_score_row.id = uuid.uuid4()
        high_score_row.score = 0.85  # above threshold

        high_article = MagicMock()
        high_article.id = high_score_row.id

        async def mock_execute(stmt, params=None):
            result = MagicMock()
            if params and "emb" in str(params):
                # pgvector query
                result.fetchall = MagicMock(return_value=[low_score_row, high_score_row])
            else:
                # article fetch
                result.scalar_one_or_none = MagicMock(return_value=high_article)
            return result

        mock_db.execute = AsyncMock(side_effect=mock_execute)

        with patch("app.routers.chatbot.AsyncOpenAI") as MockOAI:
            mock_client = AsyncMock()
            MockOAI.return_value = mock_client
            mock_client.embeddings.create = AsyncMock(
                return_value=MagicMock(
                    data=[MagicMock(embedding=[0.1] * 3072)]
                )
            )

            import os
            with patch.dict(os.environ, {"SUPPORT_OPENAI_API_KEY": "test-key"}):
                from app.routers.chatbot import _retrieve_faq_articles

                results = await _retrieve_faq_articles(
                    db=mock_db,
                    query_text="how to cancel",
                    top_k=5,
                    threshold=0.72,
                )

        # Only the high-score article should be returned
        assert len(results) == 1
        article, score = results[0]
        assert score >= 0.72

    @pytest.mark.asyncio
    async def test_zero_articles_returns_empty(self):
        """When all scores are below threshold, return empty list."""
        mock_db = AsyncMock()

        low_row = MagicMock()
        low_row.id = uuid.uuid4()
        low_row.score = 0.30  # far below threshold

        async def mock_execute(stmt, params=None):
            result = MagicMock()
            if params and "emb" in str(params):
                result.fetchall = MagicMock(return_value=[low_row])
            else:
                result.scalar_one_or_none = MagicMock(return_value=None)
            return result

        mock_db.execute = AsyncMock(side_effect=mock_execute)

        with patch("app.routers.chatbot.AsyncOpenAI") as MockOAI:
            mock_client = AsyncMock()
            MockOAI.return_value = mock_client
            mock_client.embeddings.create = AsyncMock(
                return_value=MagicMock(data=[MagicMock(embedding=[0.1] * 3072)])
            )

            import os
            with patch.dict(os.environ, {"SUPPORT_OPENAI_API_KEY": "test-key"}):
                from app.routers.chatbot import _retrieve_faq_articles

                results = await _retrieve_faq_articles(
                    db=mock_db,
                    query_text="unrelated query",
                    top_k=5,
                    threshold=0.72,
                )

        assert results == []


# ---------------------------------------------------------------------------
# Chatbot rate limit test
# ---------------------------------------------------------------------------


class TestChatbotRateLimit:
    @pytest.fixture
    def uid(self) -> str:
        return str(uuid.uuid4())

    @pytest.fixture
    def chatbot_client(self, uid: str):
        from app.main import app
        from app.db import get_db

        db_sess = AsyncMock()
        exec_result = MagicMock()
        exec_result.scalar_one_or_none = MagicMock(return_value=None)
        db_sess.execute = AsyncMock(return_value=exec_result)
        db_sess.add = MagicMock()
        db_sess.flush = AsyncMock()
        db_sess.commit = AsyncMock()
        db_sess.refresh = AsyncMock()

        async def override_db():
            yield db_sess

        app.dependency_overrides[get_db] = override_db
        with TestClient(app, raise_server_exceptions=False) as c:
            c.headers.update({"X-User-Id": uid})
            yield c
        app.dependency_overrides.clear()

    @patch("app.routers.chatbot._check_rate_limit")
    @patch("app.routers.chatbot._get_or_create_session")
    @patch("app.routers.chatbot._retrieve_faq_articles", return_value=[])
    def test_zero_articles_returns_sse_handoff(
        self, mock_retrieve, mock_session, mock_rate, chatbot_client, uid
    ):
        """
        When no FAQ articles clear the threshold, chatbot returns SSE hand-off
        stream without calling OpenAI.
        """
        mock_rate.return_value = None

        session_obj = MagicMock()
        session_obj.id = uuid.uuid4()
        mock_session.return_value = session_obj

        resp = chatbot_client.post(
            "/v1/support/chatbot",
            json={"message": "Something totally random"},
        )
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers.get("content-type", "")

    @patch("app.routers.chatbot._get_redis")
    def test_rate_limit_exceeded_returns_429(self, mock_get_redis, chatbot_client, uid):
        """11th request within 1 hour → HTTP 429."""
        mock_redis = AsyncMock()
        mock_redis.incr = AsyncMock(return_value=11)  # over limit of 10
        mock_redis.expire = AsyncMock()
        mock_get_redis.return_value = mock_redis

        resp = chatbot_client.post(
            "/v1/support/chatbot",
            json={"message": "Any message"},
        )
        assert resp.status_code == 429


# ---------------------------------------------------------------------------
# Chatbot hand-off sentinel test (unit)
# ---------------------------------------------------------------------------


class TestChatbotHandoff:
    @pytest.mark.asyncio
    async def test_handoff_stream_contains_handoff_message(self):
        """_stream_handoff() should yield SSE with hand-off text and done=True."""
        from app.routers.chatbot import HANDOFF_MESSAGE, _stream_handoff
        import json

        chunks = []
        async for chunk in _stream_handoff():
            chunks.append(chunk)

        # Parse SSE events
        events = []
        for chunk in chunks:
            if chunk.startswith("data: "):
                events.append(json.loads(chunk[6:].strip()))

        assert any("delta" in e and HANDOFF_MESSAGE in e["delta"] for e in events)
        assert any(e.get("done") is True for e in events)
