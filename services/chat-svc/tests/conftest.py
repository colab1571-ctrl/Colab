"""
chat-svc test fixtures.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def mock_db():
    """Mock async SQLAlchemy session."""
    db = AsyncMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.add = MagicMock()
    return db


@pytest.fixture
def mock_presence():
    """Mock AsyncPresenceManager."""
    presence = AsyncMock()
    presence.set_online = AsyncMock()
    presence.set_typing = AsyncMock()
    presence.refresh_ttl = AsyncMock()
    presence.publish = AsyncMock()
    presence.subscribe = AsyncMock()
    presence.unsubscribe = AsyncMock()
    return presence


@pytest.fixture
def mock_conn_mgr():
    """Mock AsyncConnectionManager."""
    mgr = AsyncMock()
    mgr.add = MagicMock()
    mgr.remove = MagicMock()
    mgr.send_to = AsyncMock()
    mgr.local_broadcast = AsyncMock()
    return mgr


@pytest.fixture
def sample_room_id():
    return uuid.uuid4()


@pytest.fixture
def sample_profile_id():
    return uuid.uuid4()


@pytest.fixture
def sample_other_profile_id():
    return uuid.uuid4()
