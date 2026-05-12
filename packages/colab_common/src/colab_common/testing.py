"""
colab_common.testing — Pytest fixtures for all Colab services.

Usage in a service's conftest.py:
    from colab_common.testing import *  # noqa: F403

Or import individually:
    from colab_common.testing import pg_url, redis_url, client, auth_user
"""

from __future__ import annotations

import time
from collections.abc import AsyncGenerator, Generator
from typing import Any

import jwt
import pytest
import pytest_asyncio


# ---------------------------------------------------------------------------
# Database fixtures (testcontainers-postgres)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def pg_url() -> Generator[str, None, None]:
    """
    Start a throw-away Postgres container. Yields the connection URL.
    Requires testcontainers[postgres] to be installed.
    """
    try:
        from testcontainers.postgres import PostgresContainer
    except ImportError:
        pytest.skip("testcontainers[postgres] not installed")

    with PostgresContainer("postgres:16-alpine") as pg:
        url = pg.get_connection_url().replace("psycopg2", "asyncpg")
        yield url


@pytest.fixture(scope="session")
def redis_url() -> Generator[str, None, None]:
    """
    Start a throw-away Redis container. Yields the connection URL.
    Requires testcontainers[redis] to be installed.
    """
    try:
        from testcontainers.redis import RedisContainer
    except ImportError:
        pytest.skip("testcontainers[redis] not installed")

    with RedisContainer("redis:7-alpine") as r:
        yield f"redis://{r.get_container_host_ip()}:{r.get_exposed_port(6379)}/0"


@pytest.fixture(scope="session")
def rabbitmq_url() -> Generator[str, None, None]:
    """
    Start a throw-away RabbitMQ container. Yields the connection URL.
    Requires testcontainers (with Docker) to be available.
    """
    try:
        from testcontainers.rabbitmq import RabbitMqContainer
    except ImportError:
        pytest.skip("testcontainers[rabbitmq] not installed")

    with RabbitMqContainer("rabbitmq:3.13-alpine") as rmq:
        yield rmq.get_connection_url()


# ---------------------------------------------------------------------------
# HTTP client fixture (ASGI in-process)
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def client(app: Any) -> AsyncGenerator[Any, None]:  # type: ignore[override]
    """
    Async HTTP client against a FastAPI ASGI app.
    The `app` fixture must be defined in the service's conftest.py.

    Usage:
        @pytest.fixture
        def app():
            from myservice.main import create_app
            return create_app()
    """
    import httpx
    from httpx import ASGITransport

    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ---------------------------------------------------------------------------
# Auth fixtures
# ---------------------------------------------------------------------------


def mint_jwt(
    user_id: str = "test-user-001",
    email: str = "test@colab.test",
    roles: list[str] | None = None,
    tier: str = "free",
    secret: str = "test-secret",
    ttl_seconds: int = 3600,
) -> str:
    """Mint a test JWT signed with HS256."""
    now = int(time.time())
    payload = {
        "sub": user_id,
        "email": email,
        "roles": roles or ["user"],
        "tier": tier,
        "iat": now,
        "exp": now + ttl_seconds,
    }
    return jwt.encode(payload, secret, algorithm="HS256")


class AuthUserFactory:
    """Factory for creating test JWTs with different roles/tiers."""

    def __init__(self, secret: str = "test-secret") -> None:
        self.secret = secret

    def __call__(
        self,
        role: str = "user",
        tier: str = "free",
        user_id: str = "test-user-001",
    ) -> str:
        roles = [role]
        if role == "admin":
            roles = ["admin", "moderator", "user"]
        elif role == "moderator":
            roles = ["moderator", "user"]
        return mint_jwt(
            user_id=user_id,
            roles=roles,
            tier=tier,
            secret=self.secret,
        )


@pytest.fixture
def auth_user() -> AuthUserFactory:
    """
    Fixture that returns a factory for minting test JWTs.

    Usage:
        def test_protected(client, auth_user):
            token = auth_user(role="admin")
            resp = client.get("/admin/users", headers={"Authorization": f"Bearer {token}"})
    """
    return AuthUserFactory(secret="test-secret")


# ---------------------------------------------------------------------------
# Time freeze
# ---------------------------------------------------------------------------


@pytest.fixture
def freeze_time() -> Generator[Any, None, None]:
    """Simple time freeze via freezegun. Yields the freeze object."""
    try:
        from freezegun import freeze_time as _freeze
    except ImportError:
        pytest.skip("freezegun not installed")

    with _freeze("2026-01-01 00:00:00") as frozen:
        yield frozen
