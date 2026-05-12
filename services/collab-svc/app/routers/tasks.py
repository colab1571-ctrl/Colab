"""
collab-svc REST API — Project Plan (Task + TaskComment).

Routes:
  GET    /collabs/{collab_id}/tasks
  POST   /collabs/{collab_id}/tasks
  POST   /collabs/{collab_id}/tasks/rebalance
  PATCH  /tasks/{task_id}
  DELETE /tasks/{task_id}
  POST   /tasks/{task_id}/comments
  GET    /tasks/{task_id}/comments
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import Collaboration
from app.routers.collabs import get_current_profile_id
from app.schemas_tools import (
    TaskCommentCreateRequest,
    TaskCommentListResponse,
    TaskCommentOut,
    TaskCreateRequest,
    TaskListResponse,
    TaskOut,
    TaskPatchRequest,
    TASK_STATUS_LABELS,
)
from app.services import collab_service
from app.services.task_service import (
    create_comment,
    create_task,
    get_task,
    list_comments,
    list_tasks,
    get_comment_count,
    rebalance_order_keys,
    soft_delete_task,
    update_task,
)
from app.workers.events import emit_event

router = APIRouter(tags=["tasks"])


# ---------------------------------------------------------------------------
# Auth + collab participant guard
# ---------------------------------------------------------------------------


async def _get_participant_collab(
    collab_id: uuid.UUID,
    profile_id: uuid.UUID,
    db: AsyncSession,
) -> Collaboration:
    collab = await collab_service.get_collab(db, collab_id, profile_id)
    if collab is None:
        raise HTTPException(status_code=404, detail="Collaboration not found")
    return collab


async def _get_participant_task(
    task_id: uuid.UUID,
    profile_id: uuid.UUID,
    db: AsyncSession,
):
    from sqlalchemy import select
    from app.models_tools import Task

    result = await db.execute(
        select(Task).where(Task.id == task_id, Task.deleted_at.is_(None))
    )
    task = result.scalars().first()
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    # Verify requester is participant in the collab
    collab = await collab_service.get_collab(db, task.collab_id, profile_id)
    if collab is None:
        raise HTTPException(status_code=403, detail="Not a participant in this collaboration")
    return task, collab


def _task_to_out(task, comment_count: int = 0) -> TaskOut:
    return TaskOut(
        id=task.id,
        collab_id=task.collab_id,
        title=task.title,
        description=task.description,
        assignee_profile_id=task.assignee_profile_id,
        due_date=task.due_date,
        status=task.status,
        order_key=task.order_key,
        created_by=task.created_by,
        created_at=task.created_at,
        updated_at=task.updated_at,
        closed_at=task.closed_at,
        comment_count=comment_count,
    )


# ---------------------------------------------------------------------------
# GET /collabs/{collab_id}/tasks
# ---------------------------------------------------------------------------


@router.get("/collabs/{collab_id}/tasks", response_model=TaskListResponse)
async def list_tasks_endpoint(
    collab_id: uuid.UUID,
    sort: str = Query("order", pattern="^(order|due_date|status)$"),
    status: str | None = Query(None, pattern="^(todo|in_progress|done|blocked)$"),
    profile_id: uuid.UUID = Depends(get_current_profile_id),
    db: AsyncSession = Depends(get_db),
) -> TaskListResponse:
    await _get_participant_collab(collab_id, profile_id, db)
    tasks = await list_tasks(db, collab_id, sort=sort, status_filter=status)

    items = []
    for t in tasks:
        cc = await get_comment_count(db, t.id)
        items.append(_task_to_out(t, comment_count=cc))

    return TaskListResponse(tasks=items, total=len(items))


# ---------------------------------------------------------------------------
# POST /collabs/{collab_id}/tasks
# ---------------------------------------------------------------------------


@router.post("/collabs/{collab_id}/tasks", response_model=TaskOut, status_code=201)
async def create_task_endpoint(
    collab_id: uuid.UUID,
    body: TaskCreateRequest,
    profile_id: uuid.UUID = Depends(get_current_profile_id),
    db: AsyncSession = Depends(get_db),
) -> TaskOut:
    await _get_participant_collab(collab_id, profile_id, db)

    # Validate assignee is one of the two participants (if provided)
    # Note: profile-svc lookup skipped here; gateway enforces participant IDs.

    task = await create_task(
        db=db,
        collab_id=collab_id,
        created_by=profile_id,
        title=body.title,
        description=body.description,
        assignee_profile_id=body.assignee_profile_id,
        due_date=body.due_date,
        order_key=body.order_key,
    )

    # Emit task.created system message
    await emit_event(
        "task.created",
        {
            "collab_id": str(collab_id),
            "task_id": str(task.id),
            "task_title": task.title,
            "actor_profile_id": str(profile_id),
        },
    )

    return _task_to_out(task)


# ---------------------------------------------------------------------------
# POST /collabs/{collab_id}/tasks/rebalance
# ---------------------------------------------------------------------------


@router.post("/collabs/{collab_id}/tasks/rebalance", response_model=TaskListResponse)
async def rebalance_tasks_endpoint(
    collab_id: uuid.UUID,
    profile_id: uuid.UUID = Depends(get_current_profile_id),
    db: AsyncSession = Depends(get_db),
) -> TaskListResponse:
    await _get_participant_collab(collab_id, profile_id, db)
    tasks = await rebalance_order_keys(db, collab_id)
    items = [_task_to_out(t) for t in tasks]

    await emit_event(
        "tasks.rebalanced",
        {"collab_id": str(collab_id), "count": len(tasks)},
    )

    return TaskListResponse(tasks=items, total=len(items))


# ---------------------------------------------------------------------------
# PATCH /tasks/{task_id}
# ---------------------------------------------------------------------------


@router.patch("/tasks/{task_id}", response_model=TaskOut)
async def patch_task_endpoint(
    task_id: uuid.UUID,
    body: TaskPatchRequest,
    profile_id: uuid.UUID = Depends(get_current_profile_id),
    db: AsyncSession = Depends(get_db),
) -> TaskOut:
    task, collab = await _get_participant_task(task_id, profile_id, db)

    update_kwargs = body.model_dump(exclude_unset=True)
    task, prev_status = await update_task(db, task, **update_kwargs)

    # Emit events for significant changes
    if prev_status is not None:
        # Status changed
        await emit_event(
            "task.status_changed",
            {
                "collab_id": str(task.collab_id),
                "task_id": str(task.id),
                "task_title": task.title,
                "actor_profile_id": str(profile_id),
                "prev_status": prev_status,
                "new_status": task.status,
                "occurred_at": task.updated_at.isoformat(),
            },
        )

    if "assignee_profile_id" in update_kwargs and body.assignee_profile_id is not None:
        await emit_event(
            "task.assigned",
            {
                "collab_id": str(task.collab_id),
                "task_id": str(task.id),
                "task_title": task.title,
                "actor_profile_id": str(profile_id),
                "assignee_profile_id": str(body.assignee_profile_id),
            },
        )

    cc = await get_comment_count(db, task.id)
    return _task_to_out(task, comment_count=cc)


# ---------------------------------------------------------------------------
# DELETE /tasks/{task_id}
# ---------------------------------------------------------------------------


@router.delete("/tasks/{task_id}", status_code=204)
async def delete_task_endpoint(
    task_id: uuid.UUID,
    profile_id: uuid.UUID = Depends(get_current_profile_id),
    db: AsyncSession = Depends(get_db),
) -> None:
    task, collab = await _get_participant_task(task_id, profile_id, db)
    task_title = task.title
    collab_id = task.collab_id

    await soft_delete_task(db, task)

    await emit_event(
        "task.deleted",
        {
            "collab_id": str(collab_id),
            "task_id": str(task_id),
            "task_title": task_title,
            "actor_profile_id": str(profile_id),
        },
    )


# ---------------------------------------------------------------------------
# POST /tasks/{task_id}/comments
# ---------------------------------------------------------------------------


@router.post("/tasks/{task_id}/comments", response_model=TaskCommentOut, status_code=201)
async def create_comment_endpoint(
    task_id: uuid.UUID,
    body: TaskCommentCreateRequest,
    profile_id: uuid.UUID = Depends(get_current_profile_id),
    db: AsyncSession = Depends(get_db),
) -> TaskCommentOut:
    task, _ = await _get_participant_task(task_id, profile_id, db)
    comment = await create_comment(
        db=db,
        task_id=task.id,
        author_profile_id=profile_id,
        body=body.body,
    )
    return TaskCommentOut(
        id=comment.id,
        task_id=comment.task_id,
        author_profile_id=comment.author_profile_id,
        body=comment.body,
        created_at=comment.created_at,
    )


# ---------------------------------------------------------------------------
# GET /tasks/{task_id}/comments
# ---------------------------------------------------------------------------


@router.get("/tasks/{task_id}/comments", response_model=TaskCommentListResponse)
async def list_comments_endpoint(
    task_id: uuid.UUID,
    cursor: uuid.UUID | None = Query(None),
    limit: int = Query(20, ge=1, le=50),
    profile_id: uuid.UUID = Depends(get_current_profile_id),
    db: AsyncSession = Depends(get_db),
) -> TaskCommentListResponse:
    await _get_participant_task(task_id, profile_id, db)
    comments, next_cursor = await list_comments(db, task_id, cursor=cursor, limit=limit)

    return TaskCommentListResponse(
        comments=[
            TaskCommentOut(
                id=c.id,
                task_id=c.task_id,
                author_profile_id=c.author_profile_id,
                body=c.body,
                created_at=c.created_at,
            )
            for c in comments
        ],
        next_cursor=next_cursor,
    )
