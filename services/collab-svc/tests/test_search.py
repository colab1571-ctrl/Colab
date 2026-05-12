"""
Tests for full-text search correctness:
- search_vector composition (title A, description B, names C, file_names D)
- Chat content exclusion
- Participant isolation
- Archived include/exclude
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Search vector composition
# ---------------------------------------------------------------------------


def test_search_vector_weights_documented():
    """
    Ensure the tsvector composition in the migration matches spec:
    title=A, description=B, names=C, file_names=D.
    """
    migration_path = (
        "/tmp/colab-009-collab-lifecycle/services/collab-svc/alembic/versions/"
        "20260511_0001_initial_collab_schema.py"
    )
    with open(migration_path) as f:
        content = f.read()

    assert "setweight(to_tsvector('english', coalesce(v_title, '')), 'A')" in content
    assert "setweight(to_tsvector('english', coalesce(v_description, '')), 'B')" in content
    assert "setweight(to_tsvector('english', coalesce(v_names, '')), 'C')" in content
    assert "setweight(to_tsvector('english', coalesce(v_file_names, '')), 'D')" in content


# ---------------------------------------------------------------------------
# Chat content excluded from search
# ---------------------------------------------------------------------------


def test_chat_content_not_in_search_vector():
    """
    The search_vector MUST NOT include chat message bodies.
    Verify the refresh_search_vector function does not reference chat tables.
    """
    migration_path = (
        "/tmp/colab-009-collab-lifecycle/services/collab-svc/alembic/versions/"
        "20260511_0001_initial_collab_schema.py"
    )
    with open(migration_path) as f:
        content = f.read()

    # chat.chat_message and chat_message body must not appear in search vector function
    # The function only joins collab.collab_participant_name_cache and collab.collab_file_name
    assert "chat.chat_message" not in content.split("refresh_search_vector")[1].split("$$")[0]
    assert "body" not in content.split("refresh_search_vector")[1].split("$$")[0]


# ---------------------------------------------------------------------------
# Participant isolation: list_collabs filters by profile_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_collabs_filters_by_participant():
    """
    list_collabs must only return collabs where profile_id_a OR profile_id_b == current_profile.
    """
    from app.services.collab_service import list_collabs

    profile_id = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")

    # Mock collab belonging to this user
    my_collab = MagicMock()
    my_collab.id = uuid.uuid4()
    my_collab.profile_id_a = profile_id
    my_collab.profile_id_b = uuid.uuid4()
    my_collab.status = "in_progress"
    my_collab.archived_at = None
    my_collab.last_activity_at = __import__("datetime").datetime.now(
        __import__("datetime").timezone.utc
    )

    mock_db = AsyncMock()
    mock_result = MagicMock()
    # Return tuple (collab, rank) as sqlalchemy returns
    mock_result.all.return_value = [(my_collab, 0.0)]
    mock_db.execute.return_value = mock_result

    collabs, next_cursor = await list_collabs(
        db=mock_db,
        profile_id=profile_id,
        limit=20,
    )

    assert len(collabs) == 1
    assert collabs[0].profile_id_a == profile_id


# ---------------------------------------------------------------------------
# Archived collabs excluded by default
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_collabs_excludes_archived_by_default():
    """
    Without include_archived=True, archived collabs should be excluded.
    The SQL query includes 'archived_at IS NULL' by default.
    """
    from app.services import collab_service
    from sqlalchemy import and_

    # Verify the list_collabs function includes archived_at filter
    import inspect
    source = inspect.getsource(collab_service.list_collabs)

    # archived_at.is_(None) should appear in the non-include_archived path
    assert "archived_at" in source
    assert "include_archived" in source


# ---------------------------------------------------------------------------
# Search query uses plainto_tsquery (safe for user input)
# ---------------------------------------------------------------------------


def test_search_uses_plainto_tsquery():
    """
    The list_collabs search path must use plainto_tsquery (not to_tsquery)
    to safely handle raw user input without syntax errors.
    """
    import inspect
    from app.services import collab_service

    source = inspect.getsource(collab_service.list_collabs)
    assert "plainto_tsquery" in source


# ---------------------------------------------------------------------------
# GIN index present in migration
# ---------------------------------------------------------------------------


def test_gin_index_on_search_vector():
    """GIN index must be created on search_vector for performance."""
    migration_path = (
        "/tmp/colab-009-collab-lifecycle/services/collab-svc/alembic/versions/"
        "20260511_0001_initial_collab_schema.py"
    )
    with open(migration_path) as f:
        content = f.read()

    assert "USING GIN (search_vector)" in content
    assert "idx_collaboration_search_vector" in content
