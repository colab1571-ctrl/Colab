"""
auth-svc test configuration.

Uses in-memory SQLite (via aiosqlite) and a mocked Redis client.
No network calls. No real SNS/SES.
"""

from __future__ import annotations

import asyncio
import os
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Stub env before imports that read secrets
os.environ.setdefault("ENV", "test")
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
os.environ.setdefault("SNS_ENABLED", "false")
os.environ.setdefault("SES_ENABLED", "false")
os.environ.setdefault("APPLE_SIGN_IN_CLIENT_ID", "test.client.id")
os.environ.setdefault("GOOGLE_CLIENT_ID_IOS", "google-ios.apps.googleusercontent.com")

from colab_common.db import Base, get_session
from app.main import app

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"

_engine = create_async_engine(TEST_DB_URL, echo=False)
_session_factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture(scope="session")
async def init_db() -> AsyncGenerator[None, None]:
    async with _engine.begin() as conn:
        # SQLite doesn't support all PG types; we use a simplified approach
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def db_session(init_db: None) -> AsyncGenerator[AsyncSession, None]:
    async with _session_factory() as session:
        async with session.begin():
            yield session
            await session.rollback()


@pytest.fixture
def mock_redis() -> MagicMock:
    """Mock Redis to avoid real network calls."""
    mock = MagicMock()
    mock.set = AsyncMock(return_value=True)
    mock.get = AsyncMock(return_value=None)
    mock.exists = AsyncMock(return_value=0)
    mock.setex = AsyncMock(return_value=True)
    mock.delete = AsyncMock(return_value=1)
    mock.hset = AsyncMock(return_value=1)
    mock.hget = AsyncMock(return_value=None)
    mock.expire = AsyncMock(return_value=True)
    mock.incr = AsyncMock(return_value=1)
    mock.ttl = AsyncMock(return_value=900)
    mock.pipeline = MagicMock(return_value=mock)
    mock.execute = AsyncMock(return_value=[1, True])
    mock.evalsha = AsyncMock(return_value=[1, 59])
    mock.script_load = AsyncMock(return_value="sha1234")
    return mock


@pytest_asyncio.fixture
async def client(db_session: AsyncSession, mock_redis: MagicMock) -> AsyncGenerator[AsyncClient, None]:
    """HTTP client with DB and Redis mocked."""

    async def override_get_session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_session] = override_get_session

    with (
        patch("colab_common.rate_limit._get_redis", return_value=mock_redis),
        patch("colab_common.rate_limit._get_script_sha", AsyncMock(return_value="sha1234")),
        patch("app.services.brute_force._get_redis", return_value=mock_redis),
        patch("app.services.otp._get_redis", return_value=mock_redis),
        patch("app.services.tokens._get_redis", return_value=mock_redis),
        patch("colab_common.events._get_redis", return_value=mock_redis),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            yield ac

    app.dependency_overrides.clear()
