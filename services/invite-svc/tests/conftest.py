"""
invite-svc test fixtures.

Uses:
  - fakeredis for Redis quota/idempotency testing
  - SQLite in-memory (via aiosqlite) for DB tests where needed
  - respx for mocking moderation-svc + billing-svc HTTP calls
  - TestClient (httpx) for endpoint tests
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import fakeredis.aioredis
import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app
from app.services.quota import _PREMIUM_LIMIT


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def fake_redis():
    """In-memory fakeredis instance."""
    r = fakeredis.aioredis.FakeRedis(decode_responses=False)
    return r


@pytest.fixture
def mock_channel():
    """Mock aio_pika channel that records published events."""
    channel = AsyncMock()
    published: list[tuple[str, dict]] = []

    async def fake_publish(message, routing_key=None):
        import json
        published.append((routing_key, json.loads(message.body)))

    exchange = AsyncMock()
    exchange.publish = fake_publish
    channel.declare_exchange = AsyncMock(return_value=exchange)
    channel._published = published
    return channel


@pytest.fixture
def client(fake_redis, mock_channel):
    """Test client with mocked Redis + RabbitMQ channel."""
    app.state.redis = fake_redis
    app.state.amqp_channel = mock_channel

    # Mock auth middleware: inject profile_id into request state
    user_a_id = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")

    from fastapi import Request

    original_build_middleware_stack = app.build_middleware_stack

    def _mock_state(request: Request):
        request.state.profile_id = str(user_a_id)

    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


@pytest.fixture
def user_a():
    return uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")


@pytest.fixture
def user_b():
    return uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")


@pytest.fixture
def user_c():
    return uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")


def mock_free_entitlement(monkeypatch):
    """Patch billing-svc to return free tier (5 invites/week)."""
    settings = get_settings()
    monkeypatch.setattr(
        "app.services.quota._get_invite_limit",
        AsyncMock(return_value=5),
    )


def mock_premium_entitlement(monkeypatch):
    """Patch billing-svc to return premium (unlimited)."""
    monkeypatch.setattr(
        "app.services.quota._get_invite_limit",
        AsyncMock(return_value=_PREMIUM_LIMIT),
    )


def mock_moderation_clean(monkeypatch):
    """Patch moderation to return clean (score=0.0)."""
    monkeypatch.setattr(
        "app.routers.invites.scan_synopsis",
        AsyncMock(return_value=None),
    )


def mock_moderation_flagged(monkeypatch, reason="harassment"):
    """Patch moderation to raise SynopsisFlagged."""
    from app.services.moderation import SynopsisFlagged

    monkeypatch.setattr(
        "app.routers.invites.scan_synopsis",
        AsyncMock(side_effect=SynopsisFlagged(reason=reason)),
    )
