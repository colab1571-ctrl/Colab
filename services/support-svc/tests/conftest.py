"""
Shared pytest fixtures for support-svc tests.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Generator
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def user_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def agent_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def mock_db_session() -> AsyncMock:
    """AsyncMock for the DB session dependency."""
    sess = AsyncMock()
    execute_result = MagicMock()
    execute_result.scalar_one_or_none = MagicMock(return_value=None)
    execute_result.scalar_one = MagicMock(return_value=0)
    execute_result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
    execute_result.fetchall = MagicMock(return_value=[])
    sess.execute = AsyncMock(return_value=execute_result)
    sess.add = MagicMock()
    sess.flush = AsyncMock()
    sess.commit = AsyncMock()
    sess.refresh = AsyncMock()
    return sess


@pytest.fixture
def app_client(mock_db_session: AsyncMock, user_id: uuid.UUID) -> Generator:
    """TestClient with DB dependency overridden and auth header pre-set."""
    from app.main import app
    from app.db import get_db

    async def override_db():
        yield mock_db_session

    app.dependency_overrides[get_db] = override_db

    with TestClient(app, raise_server_exceptions=False) as client:
        client.headers.update({"X-User-Id": str(user_id)})
        yield client

    app.dependency_overrides.clear()
