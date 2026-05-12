"""pytest fixtures for collab-svc tests."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def profile_a() -> uuid.UUID:
    return uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")


@pytest.fixture
def profile_b() -> uuid.UUID:
    return uuid.UUID("bbbbbbbb-0000-0000-0000-000000000002")


@pytest.fixture
def collab_id() -> uuid.UUID:
    return uuid.UUID("cccccccc-0000-0000-0000-000000000003")


def make_collab(
    id: uuid.UUID | None = None,
    profile_id_a: uuid.UUID | None = None,
    profile_id_b: uuid.UUID | None = None,
    status: str = "still_deciding",
    is_read_only: bool = False,
    archived_at: datetime | None = None,
    last_activity_at: datetime | None = None,
    nudge_sent_at: datetime | None = None,
) -> MagicMock:
    """Create a mock Collaboration object."""
    c = MagicMock()
    c.id = id or uuid.uuid4()
    c.profile_id_a = profile_id_a or uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")
    c.profile_id_b = profile_id_b or uuid.UUID("bbbbbbbb-0000-0000-0000-000000000002")
    c.status = status
    c.is_read_only = is_read_only
    c.archived_at = archived_at
    c.last_activity_at = last_activity_at or datetime.now(UTC)
    c.nudge_sent_at = nudge_sent_at
    c.title = None
    c.description = None
    c.completed_at = None
    c.archive_at = None
    c.nudge_sent_at = nudge_sent_at
    c.updated_at = datetime.now(UTC)
    return c
