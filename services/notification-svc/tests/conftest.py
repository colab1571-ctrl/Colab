"""
Pytest fixtures for notification-svc tests.

Uses:
- fakeredis for Redis (no real Redis needed)
- moto for SNS/SES mocks
- SQLite in-memory for ORM model tests (Postgres enums stubbed)
"""

from __future__ import annotations

import os
import uuid
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

# Ensure test env before any imports
os.environ.setdefault("ENV", "local")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("JWT_SECRET", "test-secret-key")


@pytest.fixture
def fake_redis():
    """Return a fakeredis instance for testing."""
    try:
        import fakeredis

        r = fakeredis.FakeRedis(decode_responses=True)
        return r
    except ImportError:
        pytest.skip("fakeredis not installed")


@pytest.fixture
def fake_async_redis():
    """Return an async fakeredis instance for testing."""
    try:
        import fakeredis
        import fakeredis.aioredis as faio

        r = faio.FakeRedis(decode_responses=True)
        return r
    except ImportError:
        pytest.skip("fakeredis[aioredis] not installed")


@pytest.fixture
def mock_ses_client():
    """Mock boto3 SES client."""
    mock = MagicMock()
    mock.send_email.return_value = {"MessageId": "test-msg-id-123"}
    return mock


@pytest.fixture
def mock_sns_client():
    """Mock boto3 SNS client."""
    mock = MagicMock()
    mock.create_platform_endpoint.return_value = {"EndpointArn": "arn:aws:sns:us-east-1:123456789:endpoint/APNS/test/abc123"}
    mock.publish.return_value = {"MessageId": "test-sns-msg-id"}
    mock.delete_endpoint.return_value = {}
    return mock


@pytest.fixture
def sample_user_id() -> str:
    return str(uuid.uuid4())


@pytest.fixture
def sample_other_user_id() -> str:
    return str(uuid.uuid4())


@pytest.fixture
def sample_collab_id() -> str:
    return str(uuid.uuid4())


@pytest.fixture
def sample_match_id() -> str:
    return str(uuid.uuid4())
