"""pytest fixtures for meeting-svc tests."""

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


@pytest.fixture
def meeting_id() -> uuid.UUID:
    return uuid.UUID("dddddddd-0000-0000-0000-000000000004")


@pytest.fixture
def future_dt() -> datetime:
    return datetime.now(UTC) + timedelta(days=7)


def make_meeting(
    id: uuid.UUID | None = None,
    collab_id: uuid.UUID | None = None,
    organizer_profile_id: uuid.UUID | None = None,
    scheduled_at: datetime | None = None,
    duration_min: int = 60,
    join_url: str = "https://meet.google.com/abc-defg-hij",
    gcal_event_id: str = "gcal_event_123",
    gcal_request_id: uuid.UUID | None = None,
    status: str = "scheduled",
    bot_enabled: bool = False,
    bot_status: str = "none",
    recall_bot_id: str | None = None,
    consents: list | None = None,
    artifacts: list | None = None,
) -> MagicMock:
    m = MagicMock()
    m.id = id or uuid.uuid4()
    m.collab_id = collab_id or uuid.UUID("cccccccc-0000-0000-0000-000000000003")
    m.organizer_profile_id = organizer_profile_id or uuid.UUID(
        "aaaaaaaa-0000-0000-0000-000000000001"
    )
    m.scheduled_at = scheduled_at or (datetime.now(UTC) + timedelta(days=7))
    m.duration_min = duration_min
    m.join_url = join_url
    m.gcal_event_id = gcal_event_id
    m.gcal_request_id = gcal_request_id or uuid.uuid4()
    m.status = status
    m.bot_enabled = bot_enabled
    m.bot_status = bot_status
    m.recall_bot_id = recall_bot_id
    m.ics_s3_key = None
    m.cancelled_at = None
    m.created_at = datetime.now(UTC)
    m.updated_at = datetime.now(UTC)
    m.consents = consents or []
    m.artifacts = artifacts or []
    return m
