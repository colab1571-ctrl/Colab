"""
Task + TaskComment CRUD service for collab-svc.

LexoRank order_key logic: the client is responsible for computing
midpoint keys. The server validates uniqueness within a collab and
provides a /rebalance endpoint to redistribute all order_keys when
the client signals key exhaustion.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models_tools import Task, TaskComment

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

INITIAL_ORDER_KEY = "i"  # Balanced midpoint of a–z


def _lexo_midpoint(a: str, b: str) -> str:
    """
    Compute a lexicographic midpoint string between a and b.
    Used by rebalance — not used for regular insert (client provides key).
    """
    if a >= b:
        raise ValueError(f"a ({a!r}) must be less than b ({b!r})")
    result = []
    for i in range(max(len(a), len(b))):
        ca = ord(a[i]) if i < len(a) else ord("a") - 1
        cb = ord(b[i]) if i < len(b) else ord("z") + 1
        if ca + 1 < cb:
            mid_char = chr((ca + cb) // 2)
            result.append(mid_char)
            return "".join(result)
        result.append(chr(ca))
    # Append midpoint character to disambiguate
    result.append("m")
    return "".join(result)


def _generate_balanced_keys(n: int) -> list[str]:
    """Generate n evenly-spaced keys in [a..z] space."""
    if n == 0:
        return []
    alphabet = "abcdefghijklmnopqrstuvwxyz"
    step = max(1, len(alphabet) // (n + 1))
    return [alphabet[min(i * step, len(alphabet) - 1)] for i in range(1, n + 1)]


# ---------------------------------------------------------------------------
# Task queries
# ---------------------------------------------------------------------------


async def list_tasks(
    db: AsyncSession,
    collab_id: uuid.UUID,
    sort: str = "order",
    status_filter: str | None = None,
) -> list[Task]:
    stmt = select(Task).where(
        Task.collab_id == collab_id,
        Task.deleted_at.is_(None),
    )
    if status_filter:
        stmt = stmt.where(Task.status == status_filter)

    if sort == "due_date":
        # NULLs last
        stmt = stmt.order_by(Task.due_date.asc().nullslast(), Task.order_key.asc())
    elif sort == "status":
        stmt = stmt.order_by(Task.status.asc(), Task.order_key.asc())
    else:
        stmt = stmt.order_by(Task.order_key.asc())

    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_task(
    db: AsyncSession,
    task_id: uuid.UUID,
    collab_id: uuid.UUID | None = None,
) -> Task | None:
    stmt = select(Task).where(Task.id == task_id, Task.deleted_at.is_(None))
    if collab_id is not None:
        stmt = stmt.where(Task.collab_id == collab_id)
    result = await db.execute(stmt)
    return result.scalars().first()


async def create_task(
    db: AsyncSession,
    collab_id: uuid.UUID,
    created_by: uuid.UUID,
    title: str,
    description: str | None,
    assignee_profile_id: uuid.UUID | None,
    due_date: "date | None",
    order_key: str,
) -> Task:
    task = Task(
        collab_id=collab_id,
        title=title,
        description=description,
        assignee_profile_id=assignee_profile_id,
        due_date=due_date,
        order_key=order_key,
        created_by=created_by,
        status="todo",
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return task


async def update_task(
    db: AsyncSession,
    task: Task,
    **kwargs,
) -> tuple[Task, str | None]:
    """
    Apply partial update fields. Returns (updated_task, prev_status_if_changed).
    """
    prev_status: str | None = None

    for field, value in kwargs.items():
        if field == "status" and value is not None and value != task.status:
            prev_status = task.status
            setattr(task, field, value)
            if value == "done":
                task.closed_at = datetime.now(UTC)
            elif prev_status == "done" and value != "done":
                task.closed_at = None
        elif value is not None or field in ("assignee_profile_id", "due_date", "description"):
            setattr(task, field, value)

    await db.commit()
    await db.refresh(task)
    return task, prev_status


async def soft_delete_task(db: AsyncSession, task: Task) -> None:
    task.deleted_at = datetime.now(UTC)
    await db.commit()


async def rebalance_order_keys(
    db: AsyncSession,
    collab_id: uuid.UUID,
) -> list[Task]:
    """
    Re-assign balanced order_keys to all non-deleted tasks in a collab,
    sorted by current order_key. Run inside a single transaction.
    """
    tasks = await list_tasks(db, collab_id, sort="order")
    new_keys = _generate_balanced_keys(len(tasks))
    for task, key in zip(tasks, new_keys):
        task.order_key = key
    await db.commit()
    return tasks


async def get_comment_count(db: AsyncSession, task_id: uuid.UUID) -> int:
    result = await db.execute(
        select(func.count()).where(
            TaskComment.task_id == task_id,
            TaskComment.deleted_at.is_(None),
        )
    )
    return result.scalar_one()


# ---------------------------------------------------------------------------
# TaskComment queries
# ---------------------------------------------------------------------------


async def create_comment(
    db: AsyncSession,
    task_id: uuid.UUID,
    author_profile_id: uuid.UUID,
    body: str,
) -> TaskComment:
    comment = TaskComment(
        task_id=task_id,
        author_profile_id=author_profile_id,
        body=body,
    )
    db.add(comment)
    await db.commit()
    await db.refresh(comment)
    return comment


async def list_comments(
    db: AsyncSession,
    task_id: uuid.UUID,
    cursor: uuid.UUID | None = None,
    limit: int = 20,
) -> tuple[list[TaskComment], uuid.UUID | None]:
    stmt = select(TaskComment).where(
        TaskComment.task_id == task_id,
        TaskComment.deleted_at.is_(None),
    )
    if cursor is not None:
        # Cursor is a comment id; get its created_at then page after it
        ref = await db.execute(
            select(TaskComment.created_at).where(TaskComment.id == cursor)
        )
        ref_ts = ref.scalar_one_or_none()
        if ref_ts is not None:
            stmt = stmt.where(TaskComment.created_at > ref_ts)

    stmt = stmt.order_by(TaskComment.created_at.asc()).limit(limit + 1)
    result = await db.execute(stmt)
    rows = list(result.scalars().all())

    next_cursor: uuid.UUID | None = None
    if len(rows) > limit:
        next_cursor = rows[limit].id
        rows = rows[:limit]

    return rows, next_cursor
