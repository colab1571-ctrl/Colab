"""ai-orchestrator-svc test fixtures."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def user_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def collab_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def room_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def asset_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def interaction_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def reservation_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.add = MagicMock()
    db.get = AsyncMock(return_value=None)
    return db


@pytest.fixture
def mock_redis():
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.setex = AsyncMock()
    redis.incr = AsyncMock(return_value=1)
    redis.expire = AsyncMock()
    redis.pipeline = MagicMock(return_value=AsyncMock(
        __aenter__=AsyncMock(return_value=AsyncMock(
            incr=AsyncMock(),
            expire=AsyncMock(),
            execute=AsyncMock(return_value=[1, True]),
        )),
        __aexit__=AsyncMock(),
        execute=AsyncMock(return_value=[1, True]),
    ))
    return redis


@pytest.fixture
def mock_http():
    return AsyncMock()


@pytest.fixture
def premium_entitlement():
    return {"tier": "premium", "ai_credits_per_month": 100}


@pytest.fixture
def pro_entitlement():
    return {"tier": "pro", "ai_credits_per_month": 500}
