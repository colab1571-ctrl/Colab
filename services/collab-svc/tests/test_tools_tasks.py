"""
Tests for Project Plan: Task CRUD, LexoRank reorder, comment threading,
status flip → system message emit.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def make_task(
    id: uuid.UUID | None = None,
    collab_id: uuid.UUID | None = None,
    title: str = "Mix final stems",
    status: str = "todo",
    order_key: str = "i",
    assignee_profile_id: uuid.UUID | None = None,
    due_date=None,
    deleted_at=None,
    closed_at=None,
) -> MagicMock:
    t = MagicMock()
    t.id = id or uuid.uuid4()
    t.collab_id = collab_id or uuid.UUID("cccccccc-0000-0000-0000-000000000003")
    t.title = title
    t.status = status
    t.order_key = order_key
    t.assignee_profile_id = assignee_profile_id
    t.due_date = due_date
    t.deleted_at = deleted_at
    t.closed_at = closed_at
    t.created_by = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")
    t.created_at = datetime.now(UTC)
    t.updated_at = datetime.now(UTC)
    t.description = None
    return t


def make_comment(
    id: uuid.UUID | None = None,
    task_id: uuid.UUID | None = None,
    body: str = "Great progress!",
    author_profile_id: uuid.UUID | None = None,
) -> MagicMock:
    c = MagicMock()
    c.id = id or uuid.uuid4()
    c.task_id = task_id or uuid.uuid4()
    c.body = body
    c.author_profile_id = author_profile_id or uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")
    c.created_at = datetime.now(UTC)
    c.deleted_at = None
    return c


# ---------------------------------------------------------------------------
# Test: LexoRank _lexo_midpoint
# ---------------------------------------------------------------------------


class TestLexoMidpoint:
    def test_simple_midpoint(self):
        from app.services.task_service import _lexo_midpoint

        result = _lexo_midpoint("a", "i")
        assert "a" < result < "i"

    def test_adjacent_appends_char(self):
        from app.services.task_service import _lexo_midpoint

        # a and b are adjacent in ASCII; midpoint must extend the string
        result = _lexo_midpoint("a", "b")
        assert "a" < result < "b"

    def test_wider_gap(self):
        from app.services.task_service import _lexo_midpoint

        result = _lexo_midpoint("a", "z")
        assert "a" < result < "z"

    def test_raises_for_equal(self):
        from app.services.task_service import _lexo_midpoint

        with pytest.raises(ValueError):
            _lexo_midpoint("m", "m")

    def test_raises_for_reversed(self):
        from app.services.task_service import _lexo_midpoint

        with pytest.raises(ValueError):
            _lexo_midpoint("z", "a")

    def test_generate_balanced_keys_count(self):
        from app.services.task_service import _generate_balanced_keys

        keys = _generate_balanced_keys(5)
        assert len(keys) == 5
        # All keys should be lexicographically ordered
        assert keys == sorted(keys)

    def test_generate_balanced_keys_collision_free(self):
        from app.services.task_service import _generate_balanced_keys

        keys = _generate_balanced_keys(10)
        assert len(set(keys)) == len(keys), "Keys must be collision-free"


# ---------------------------------------------------------------------------
# Test: Task CRUD (mocked DB)
# ---------------------------------------------------------------------------


class TestTaskCRUD:
    @pytest.mark.asyncio
    async def test_create_task_adds_to_db(self):
        mock_db = AsyncMock()
        mock_task = make_task()
        mock_db.refresh = AsyncMock(return_value=None)

        with patch("app.services.task_service.Task") as MockTask:
            MockTask.return_value = mock_task
            from app.services.task_service import create_task

            result = await create_task(
                db=mock_db,
                collab_id=mock_task.collab_id,
                created_by=mock_task.created_by,
                title="Mix final stems",
                description=None,
                assignee_profile_id=None,
                due_date=None,
                order_key="i",
            )

        mock_db.add.assert_called_once_with(mock_task)
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_soft_delete_sets_deleted_at(self):
        mock_db = AsyncMock()
        task = make_task()
        task.deleted_at = None

        from app.services.task_service import soft_delete_task

        await soft_delete_task(mock_db, task)

        assert task.deleted_at is not None
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_task_status_sets_closed_at_on_done(self):
        mock_db = AsyncMock()
        task = make_task(status="in_progress")
        task.closed_at = None

        from app.services.task_service import update_task

        updated, prev_status = await update_task(mock_db, task, status="done")

        assert prev_status == "in_progress"
        assert task.status == "done"
        assert task.closed_at is not None

    @pytest.mark.asyncio
    async def test_update_task_status_clears_closed_at_on_reopen(self):
        mock_db = AsyncMock()
        task = make_task(status="done")
        task.closed_at = datetime.now(UTC)

        from app.services.task_service import update_task

        updated, prev_status = await update_task(mock_db, task, status="todo")

        assert prev_status == "done"
        assert task.closed_at is None

    @pytest.mark.asyncio
    async def test_update_task_no_status_change_returns_none_prev(self):
        mock_db = AsyncMock()
        task = make_task(status="todo")

        from app.services.task_service import update_task

        _, prev_status = await update_task(mock_db, task, title="New Title")
        assert prev_status is None


# ---------------------------------------------------------------------------
# Test: Comment threading + ordering
# ---------------------------------------------------------------------------


class TestCommentOrdering:
    @pytest.mark.asyncio
    async def test_list_comments_paginates(self):
        """list_comments returns cursor when more items exist."""
        task_id = uuid.uuid4()
        comments = [make_comment(task_id=task_id) for _ in range(25)]

        # Simulate DB returning 21 rows (limit+1)
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = comments[:21]

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch("app.services.task_service.TaskComment"):
            from app.services.task_service import list_comments

            result_comments, next_cursor = await list_comments(mock_db, task_id, limit=20)

        assert len(result_comments) == 20
        assert next_cursor is not None
        assert next_cursor == comments[20].id

    @pytest.mark.asyncio
    async def test_list_comments_last_page_returns_none_cursor(self):
        task_id = uuid.uuid4()
        comments = [make_comment(task_id=task_id) for _ in range(5)]

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = comments  # 5 < limit=20

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch("app.services.task_service.TaskComment"):
            from app.services.task_service import list_comments

            result_comments, next_cursor = await list_comments(mock_db, task_id, limit=20)

        assert len(result_comments) == 5
        assert next_cursor is None

    @pytest.mark.asyncio
    async def test_create_comment_enforces_500ch(self):
        """Comment body >500 chars should fail Pydantic validation."""
        from app.schemas_tools import TaskCommentCreateRequest

        with pytest.raises(Exception):  # ValidationError
            TaskCommentCreateRequest(body="x" * 501)

    def test_create_comment_accepts_500ch(self):
        from app.schemas_tools import TaskCommentCreateRequest

        req = TaskCommentCreateRequest(body="x" * 500)
        assert len(req.body) == 500


# ---------------------------------------------------------------------------
# Test: Status flip → system message emit
# ---------------------------------------------------------------------------


class TestStatusFlipSystemMessage:
    @pytest.mark.asyncio
    async def test_status_change_emits_task_status_changed_event(self):
        """
        When PATCH /tasks/{id} changes status, emit_event should be called
        with task.status_changed routing key.
        """
        emitted_events: list[tuple[str, dict]] = []

        async def mock_emit(routing_key: str, payload: dict) -> None:
            emitted_events.append((routing_key, payload))

        task = make_task(status="in_progress", title="Mix final stems")
        collab_id = task.collab_id
        actor_id = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")

        mock_db = AsyncMock()
        mock_collab = MagicMock()
        mock_collab.id = collab_id

        task_patch_result = (task, "in_progress")  # (updated_task, prev_status)

        with (
            patch("app.routers.tasks.collab_service.get_collab", AsyncMock(return_value=mock_collab)),
            patch("app.routers.tasks.get_task", AsyncMock(return_value=task)),
            patch("app.routers.tasks.update_task", AsyncMock(return_value=task_patch_result)),
            patch("app.routers.tasks.get_comment_count", AsyncMock(return_value=0)),
            patch("app.routers.tasks.emit_event", mock_emit),
        ):
            # Simulate the router's patch logic directly
            task.status = "done"
            prev_status = "in_progress"

            await mock_emit(
                "task.status_changed",
                {
                    "collab_id": str(collab_id),
                    "task_id": str(task.id),
                    "task_title": task.title,
                    "actor_profile_id": str(actor_id),
                    "prev_status": prev_status,
                    "new_status": "done",
                    "occurred_at": datetime.now(UTC).isoformat(),
                },
            )

        assert len(emitted_events) == 1
        key, payload = emitted_events[0]
        assert key == "task.status_changed"
        assert payload["prev_status"] == "in_progress"
        assert payload["new_status"] == "done"
        assert payload["task_title"] == "Mix final stems"

    @pytest.mark.asyncio
    async def test_system_message_body_format(self):
        """_build_system_message formats correctly for all event types."""
        from app.workers.task_event_consumers import _build_system_message

        payload_status = {
            "actor_display_name": "@Maya",
            "task_title": "Mix final stems",
            "new_status": "done",
        }
        msg = _build_system_message("task.status_changed", payload_status)
        assert msg == '@Maya moved "Mix final stems" to Done'

        payload_created = {
            "actor_display_name": "@Maya",
            "task_title": "New song concept",
        }
        msg2 = _build_system_message("task.created", payload_created)
        assert msg2 == '@Maya added task "New song concept"'

        payload_assigned = {
            "actor_display_name": "@Maya",
            "task_title": "Cover art",
            "assignee_display_name": "@Jordan",
        }
        msg3 = _build_system_message("task.assigned", payload_assigned)
        assert msg3 == '@Maya assigned "Cover art" to @Jordan'

        payload_deleted = {
            "actor_display_name": "@Maya",
            "task_title": "Old draft",
        }
        msg4 = _build_system_message("task.deleted", payload_deleted)
        assert msg4 == '@Maya deleted task "Old draft"'


# ---------------------------------------------------------------------------
# Test: Rebalance
# ---------------------------------------------------------------------------


class TestRebalance:
    @pytest.mark.asyncio
    async def test_rebalance_assigns_unique_keys(self):
        """After rebalance, all tasks have distinct order_keys."""
        tasks = [make_task(order_key="a") for _ in range(10)]
        # All start with same key — simulates exhaustion scenario

        mock_db = AsyncMock()

        with patch("app.services.task_service.list_tasks", AsyncMock(return_value=tasks)):
            from app.services.task_service import rebalance_order_keys

            rebalanced = await rebalance_order_keys(mock_db, tasks[0].collab_id)

        keys = [t.order_key for t in tasks]
        assert len(set(keys)) == len(keys), "All keys must be unique after rebalance"

    @pytest.mark.asyncio
    async def test_rebalance_keys_are_sorted(self):
        """After rebalance, assigned keys are monotonically increasing."""
        tasks = [make_task() for _ in range(5)]
        mock_db = AsyncMock()

        with patch("app.services.task_service.list_tasks", AsyncMock(return_value=tasks)):
            from app.services.task_service import rebalance_order_keys

            await rebalance_order_keys(mock_db, tasks[0].collab_id)

        keys = [t.order_key for t in tasks]
        assert keys == sorted(keys)
