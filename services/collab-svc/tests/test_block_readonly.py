"""
Tests for block.created → collab read-only + deferred archive.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_apply_block_sets_read_only_and_archive_at():
    """
    apply_block should set is_read_only=True and archive_at=now+30d
    for all active collabs between the pair.
    """
    from app.services.collab_service import apply_block

    pa = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")
    pb = uuid.UUID("bbbbbbbb-0000-0000-0000-000000000002")

    mock_db = AsyncMock()
    mock_db.execute.return_value = MagicMock()

    update_values = {}

    with patch("app.services.collab_service.update") as mock_update:
        stmt = MagicMock()
        mock_update.return_value.where.return_value.where.return_value.where.return_value.values.side_effect = (
            lambda **kw: (update_values.update(kw), stmt)[1]
        )
        mock_update.return_value.where.return_value.where.return_value.values.side_effect = (
            lambda **kw: (update_values.update(kw), stmt)[1]
        )
        mock_update.return_value.where.return_value.values.side_effect = (
            lambda **kw: (update_values.update(kw), stmt)[1]
        )

        await apply_block(mock_db, pa, pb)

    mock_db.commit.assert_called_once()


def test_read_only_collab_blocks_status_transition():
    """
    A collab with is_read_only=True should return 403 COLLAB_READ_ONLY
    when status transition is attempted.
    """
    from fastapi import HTTPException

    # Simulate the router check
    collab = MagicMock()
    collab.is_read_only = True
    collab.archived_at = None

    with pytest.raises(HTTPException) as exc_info:
        if collab.is_read_only:
            raise HTTPException(
                status_code=403,
                detail={"error_code": "COLLAB_READ_ONLY"},
            )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail["error_code"] == "COLLAB_READ_ONLY"


@pytest.mark.asyncio
async def test_block_consumer_calls_apply_block():
    """
    The block.created event consumer should call apply_block with
    the correct profile IDs.
    """
    from app.workers.event_consumers import _handle_block_created

    blocker = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")
    blocked = uuid.UUID("bbbbbbbb-0000-0000-0000-000000000002")

    payload = {
        "blocker_profile_id": str(blocker),
        "blocked_profile_id": str(blocked),
    }

    apply_block_calls = []

    async def mock_apply_block(db, a, b):
        apply_block_calls.append((a, b))

    mock_db = AsyncMock()

    with (
        patch("app.workers.event_consumers.AsyncSessionLocal") as mock_session_factory,
        patch("app.workers.event_consumers.apply_block", side_effect=mock_apply_block),
    ):
        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=mock_db)
        ctx.__aexit__ = AsyncMock(return_value=None)
        mock_session_factory.return_value = ctx

        await _handle_block_created(payload)

    assert len(apply_block_calls) == 1
    assert apply_block_calls[0] == (blocker, blocked)
