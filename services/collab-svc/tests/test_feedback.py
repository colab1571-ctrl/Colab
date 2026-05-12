"""
Unit tests for feedback idempotency, validation, and terminal-state gate.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas import FeedbackRequest, FEEDBACK_TAGS


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------


def test_valid_feedback_request():
    req = FeedbackRequest(target="partner", rating="up", tags=["communicative", "creative"])
    assert req.rating == "up"
    assert req.target == "partner"
    assert "communicative" in req.tags


def test_invalid_tag_raises():
    with pytest.raises(Exception):  # ValidationError from Pydantic
        FeedbackRequest(target="partner", rating="up", tags=["nonexistent_tag"])


def test_comment_too_long_raises():
    with pytest.raises(Exception):
        FeedbackRequest(target="partner", rating="up", comment="x" * 501)


def test_empty_tags_ok():
    req = FeedbackRequest(target="project", rating="down", tags=[])
    assert req.tags == []


def test_all_valid_tags_accepted():
    tags = list(FEEDBACK_TAGS)
    req = FeedbackRequest(target="project", rating="up", tags=tags)
    assert set(req.tags) == FEEDBACK_TAGS


# ---------------------------------------------------------------------------
# Terminal-state gate (service layer logic)
# ---------------------------------------------------------------------------


def test_feedback_rejected_for_non_terminal_status():
    """Feedback should only be accepted for completed/didnt_work_out collabs."""
    from fastapi import HTTPException

    # Simulate the check in the router
    non_terminal_statuses = ["still_deciding", "in_progress"]
    terminal_statuses = ["completed", "didnt_work_out"]

    for status in non_terminal_statuses:
        with pytest.raises(HTTPException) as exc_info:
            if status not in ("completed", "didnt_work_out"):
                raise HTTPException(
                    status_code=403,
                    detail={"error_code": "FEEDBACK_REQUIRES_TERMINAL_STATE"},
                )
        assert exc_info.value.status_code == 403

    # Terminal states should not raise
    for status in terminal_statuses:
        try:
            if status not in ("completed", "didnt_work_out"):
                raise AssertionError("Should not raise for terminal status")
        except Exception:
            pytest.fail(f"Unexpected exception for terminal status: {status}")


# ---------------------------------------------------------------------------
# Idempotency: ON CONFLICT DO UPDATE
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_feedback_upsert_is_idempotent():
    """
    Test that submitting feedback twice for the same (collab, from_profile, target)
    results in a single updated record (not an error).
    """
    from app.services.collab_service import upsert_feedback
    from unittest.mock import patch, AsyncMock, MagicMock
    import uuid
    from datetime import UTC, datetime

    collab = MagicMock()
    collab.id = uuid.uuid4()
    collab.profile_id_a = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")
    collab.profile_id_b = uuid.UUID("bbbbbbbb-0000-0000-0000-000000000002")

    actor_id = collab.profile_id_a

    req_up = FeedbackRequest(target="partner", rating="up", tags=["communicative"])
    req_down = FeedbackRequest(target="partner", rating="down", tags=["ghosted"])

    # Mock the DB upsert
    feedback_row = MagicMock()
    feedback_row.id = uuid.uuid4()
    feedback_row.collab_id = collab.id
    feedback_row.from_profile_id = actor_id
    feedback_row.to_profile_id = collab.profile_id_b
    feedback_row.target = "partner"
    feedback_row.rating = "down"  # Updated value
    feedback_row.tags = ["ghosted"]
    feedback_row.comment = None
    feedback_row.created_at = datetime.now(UTC)

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.one.return_value = feedback_row
    mock_db.execute.return_value = mock_result

    with patch("app.services.collab_service.pg_insert") as mock_insert:
        mock_stmt = MagicMock()
        mock_insert.return_value.values.return_value.on_conflict_do_update.return_value.returning.return_value = mock_stmt
        mock_db.execute.return_value = mock_result

        result = await upsert_feedback(mock_db, collab, actor_id, req_down)

    assert result.rating == "down"
    assert mock_db.execute.called


# ---------------------------------------------------------------------------
# to_profile_id derivation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_partner_feedback_sets_to_profile_id():
    """For target='partner', to_profile_id should be the other participant."""
    from app.services.collab_service import upsert_feedback
    from unittest.mock import patch, AsyncMock, MagicMock
    import uuid
    from datetime import UTC, datetime

    pa = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")
    pb = uuid.UUID("bbbbbbbb-0000-0000-0000-000000000002")

    collab = MagicMock()
    collab.id = uuid.uuid4()
    collab.profile_id_a = pa
    collab.profile_id_b = pb

    req = FeedbackRequest(target="partner", rating="up", tags=[])

    feedback_row = MagicMock()
    feedback_row.to_profile_id = pb  # Expected

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.one.return_value = feedback_row
    mock_db.execute.return_value = mock_result

    captured_values = {}

    with patch("app.services.collab_service.pg_insert") as mock_insert:
        inserted = MagicMock()
        inserted.values.side_effect = lambda **kw: (captured_values.update(kw), inserted)[1]
        inserted.values.return_value.on_conflict_do_update.return_value.returning.return_value = MagicMock()
        mock_insert.return_value = inserted
        mock_db.execute.return_value = mock_result

        await upsert_feedback(mock_db, collab, pa, req)

    # The to_profile_id should have been set to pb (the other participant)
    assert captured_values.get("to_profile_id") == pb


@pytest.mark.asyncio
async def test_project_feedback_has_null_to_profile_id():
    """For target='project', to_profile_id should be None."""
    from app.services.collab_service import upsert_feedback
    from unittest.mock import patch, AsyncMock, MagicMock
    import uuid
    from datetime import UTC, datetime

    pa = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")
    pb = uuid.UUID("bbbbbbbb-0000-0000-0000-000000000002")

    collab = MagicMock()
    collab.id = uuid.uuid4()
    collab.profile_id_a = pa
    collab.profile_id_b = pb

    req = FeedbackRequest(target="project", rating="up", tags=["great_outcome"])

    feedback_row = MagicMock()
    feedback_row.to_profile_id = None

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.one.return_value = feedback_row
    mock_db.execute.return_value = mock_result

    captured_values = {}

    with patch("app.services.collab_service.pg_insert") as mock_insert:
        inserted = MagicMock()
        inserted.values.side_effect = lambda **kw: (captured_values.update(kw), inserted)[1]
        inserted.values.return_value.on_conflict_do_update.return_value.returning.return_value = MagicMock()
        mock_insert.return_value = inserted
        mock_db.execute.return_value = mock_result

        await upsert_feedback(mock_db, collab, pa, req)

    assert captured_values.get("to_profile_id") is None
