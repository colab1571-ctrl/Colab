"""identity-svc test configuration."""

from __future__ import annotations

import os
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

os.environ.setdefault("ENV", "test")
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
os.environ.setdefault("PERSONA_API_KEY", "test-persona-key")
os.environ.setdefault("PERSONA_TEMPLATE_ID", "tmpl_test")
os.environ.setdefault("PERSONA_WEBHOOK_SECRET", "test-webhook-secret")

from colab_common.db import Base, get_session
from app.main import app

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"
_engine = create_async_engine(TEST_DB_URL, echo=False)
_session_factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture(scope="session")
async def init_db() -> AsyncGenerator[None, None]:
    async with _engine.begin() as conn:
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
    mock = MagicMock()
    mock.set = AsyncMock(return_value=True)
    mock.get = AsyncMock(return_value=None)
    mock.exists = AsyncMock(return_value=0)
    mock.setex = AsyncMock(return_value=True)
    mock.delete = AsyncMock(return_value=1)
    mock.evalsha = AsyncMock(return_value=[1, 59])
    mock.script_load = AsyncMock(return_value="sha1234")
    return mock


@pytest_asyncio.fixture
async def client(db_session: AsyncSession, mock_redis: MagicMock) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_session] = override_get_session

    with (
        patch("colab_common.rate_limit._get_redis", return_value=mock_redis),
        patch("colab_common.rate_limit._get_script_sha", AsyncMock(return_value="sha1234")),
        patch("colab_common.events._get_redis", return_value=mock_redis),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            yield ac

    app.dependency_overrides.clear()


def make_auth_header(user_id: str = "00000000-0000-0000-0000-000000000001") -> dict[str, str]:
    """Create a mock Bearer token header for testing authenticated endpoints."""
    import time
    import jwt

    now = int(time.time())
    payload = {
        "sub": user_id,
        "iss": "auth.colab",
        "aud": ["api.colab"],
        "jti": "test-jti",
        "iat": now,
        "nbf": now,
        "exp": now + 900,
        "sid": "test-session-id",
        "email_verified": True,
        "identity_verified": False,
        "scope": ["user"],
        "typ": "access",
        "email": "test@example.com",
        "roles": [],
        "tier": "free",
    }
    token = jwt.encode(payload, "test-secret", algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}
