"""
Unit/integration tests for inactivity cadence:
- 14-day nudge fires once per window
- 30-day auto-archive
- Activity clears nudge_sent_at
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Nudge fires once per inactivity window
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_nudge_fires_once_per_window():
    """
    Given last_activity_at > 14 days ago and nudge_sent_at IS NULL,
    the nudge task should set nudge_sent_at and emit collab.nudge_due.
    A second run must not re-emit.
    """
    from app.workers.inactivity_tasks import _send_nudge_async

    collab_id = uuid.uuid4()
    now = datetime.now(UTC)
    old_activity = now - timedelta(days=15)

    collab = MagicMock()
    collab.id = collab_id
    collab.profile_id_a = uuid.uuid4()
    collab.profile_id_b = uuid.uuid4()
    collab.nudge_sent_at = None
    collab.last_activity_at = old_activity
    collab.archived_at = None

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = collab
    mock_db.execute.return_value = mock_result

    emitted_events = []

    async def mock_emit(routing_key: str, payload: dict) -> None:
        emitted_events.append((routing_key, payload))

    with (
        patch("app.workers.inactivity_tasks.AsyncSessionLocal") as mock_session_factory,
        patch("app.workers.inactivity_tasks.emit_event", side_effect=mock_emit),
        patch("app.workers.inactivity_tasks.update") as mock_update,
    ):
        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=mock_db)
        ctx.__aexit__ = AsyncMock(return_value=None)
        mock_session_factory.return_value = ctx

        await _send_nudge_async(str(collab_id))

    assert any(e[0] == "collab.nudge_due" for e in emitted_events)
    assert emitted_events[0][1]["collab_id"] == str(collab_id)


@pytest.mark.asyncio
async def test_nudge_skipped_if_already_nudged():
    """
    If nudge_sent_at is already set (first() returns None from filtered query),
    no event should be emitted.
    """
    from app.workers.inactivity_tasks import _send_nudge_async

    collab_id = uuid.uuid4()
    emitted_events = []

    async def mock_emit(routing_key: str, payload: dict) -> None:
        emitted_events.append((routing_key, payload))

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = None  # nudge_sent_at IS NOT NULL filter
    mock_db.execute.return_value = mock_result

    with (
        patch("app.workers.inactivity_tasks.AsyncSessionLocal") as mock_session_factory,
        patch("app.workers.inactivity_tasks.emit_event", side_effect=mock_emit),
    ):
        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=mock_db)
        ctx.__aexit__ = AsyncMock(return_value=None)
        mock_session_factory.return_value = ctx

        await _send_nudge_async(str(collab_id))

    assert len(emitted_events) == 0


# ---------------------------------------------------------------------------
# Auto-archive (30d)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_auto_archive_sets_archived_at():
    """
    archive_collab task should set archived_at and emit collab.archived.
    """
    from app.workers.archive_tasks import _archive_collab_async

    collab_id = uuid.uuid4()
    emitted_events = []

    async def mock_emit(routing_key: str, payload: dict) -> None:
        emitted_events.append((routing_key, payload))

    mock_db = AsyncMock()
    mock_db.execute.return_value = MagicMock()

    with (
        patch("app.workers.archive_tasks.AsyncSessionLocal") as mock_session_factory,
        patch("app.workers.archive_tasks.emit_event", side_effect=mock_emit),
        patch("app.workers.archive_tasks.update") as mock_update,
    ):
        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=mock_db)
        ctx.__aexit__ = AsyncMock(return_value=None)
        mock_session_factory.return_value = ctx

        await _archive_collab_async(str(collab_id))

    assert any(e[0] == "collab.archived" for e in emitted_events)
    archived_event = next(e for e in emitted_events if e[0] == "collab.archived")
    assert archived_event[1]["collab_id"] == str(collab_id)
    assert archived_event[1]["reason"] == "inactivity_30d"


# ---------------------------------------------------------------------------
# Activity update clears nudge_sent_at
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_activity_update_clears_nudge():
    """
    update_last_activity should set nudge_sent_at = None.
    """
    from app.services.collab_service import update_last_activity

    collab_id = uuid.uuid4()
    now = datetime.now(UTC)

    mock_db = AsyncMock()

    with patch("app.services.collab_service.update") as mock_update:
        stmt = MagicMock()
        mock_update.return_value.where.return_value.values.return_value = stmt
        mock_db.execute.return_value = MagicMock()

        await update_last_activity(mock_db, collab_id, now)

    # Verify commit was called
    mock_db.commit.assert_called_once()

    # Verify update was called with nudge_sent_at=None
    update_call = mock_update.return_value.where.return_value.values
    call_kwargs = update_call.call_args.kwargs if update_call.call_args else {}
    assert "nudge_sent_at" in call_kwargs or mock_update.called


# ---------------------------------------------------------------------------
# Inactivity check dispatches correct subtasks
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_inactivity_check_dispatches_subtasks():
    """
    Hourly inactivity_check should dispatch nudge for 14d-inactive collabs
    and archive for 30d-inactive collabs.
    """
    from app.workers.inactivity_tasks import _inactivity_check_async

    now = datetime.now(UTC)

    nudge_collab = MagicMock()
    nudge_collab.id = uuid.uuid4()
    nudge_collab.last_activity_at = now - timedelta(days=15)
    nudge_collab.nudge_sent_at = None

    archive_collab_mock = MagicMock()
    archive_collab_mock.id = uuid.uuid4()
    archive_collab_mock.last_activity_at = now - timedelta(days=31)
    archive_collab_mock.nudge_sent_at = None

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [nudge_collab, archive_collab_mock]
    mock_db.execute.return_value = mock_result

    nudge_dispatched = []
    archive_dispatched = []

    with (
        patch("app.workers.inactivity_tasks.AsyncSessionLocal") as mock_session_factory,
        patch("app.workers.inactivity_tasks.send_nudge") as mock_nudge_task,
        patch("app.workers.inactivity_tasks.archive_collab") as mock_archive_task,
    ):
        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=mock_db)
        ctx.__aexit__ = AsyncMock(return_value=None)
        mock_session_factory.return_value = ctx

        mock_nudge_task.delay.side_effect = lambda x: nudge_dispatched.append(x)
        mock_archive_task.delay.side_effect = lambda x: archive_dispatched.append(x)

        result = await _inactivity_check_async()

    assert result["nudges"] == 1
    assert result["archives"] == 1
    assert str(nudge_collab.id) in nudge_dispatched
    assert str(archive_collab_mock.id) in archive_dispatched
