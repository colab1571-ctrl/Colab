"""Pydantic schemas for P9 collab-tools (Whiteboard + Project Plan)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Task schemas
# ---------------------------------------------------------------------------

TaskStatus = Literal["todo", "in_progress", "done", "blocked"]
TASK_STATUS_LABELS: dict[str, str] = {
    "todo": "To Do",
    "in_progress": "In Progress",
    "done": "Done",
    "blocked": "Blocked",
}


class TaskCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: str | None = Field(None, max_length=2000)
    assignee_profile_id: uuid.UUID | None = None
    due_date: date | None = None
    order_key: str = Field(..., min_length=1, max_length=255)


class TaskPatchRequest(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = Field(None, max_length=2000)
    assignee_profile_id: uuid.UUID | None = None
    due_date: date | None = None
    status: TaskStatus | None = None
    order_key: str | None = Field(None, min_length=1, max_length=255)


class TaskOut(BaseModel):
    id: uuid.UUID
    collab_id: uuid.UUID
    title: str
    description: str | None
    assignee_profile_id: uuid.UUID | None
    due_date: date | None
    status: str
    order_key: str
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None
    comment_count: int = 0

    model_config = {"from_attributes": True}


class TaskListResponse(BaseModel):
    tasks: list[TaskOut]
    total: int


# ---------------------------------------------------------------------------
# TaskComment schemas
# ---------------------------------------------------------------------------


class TaskCommentCreateRequest(BaseModel):
    body: str = Field(..., min_length=1, max_length=500)


class TaskCommentOut(BaseModel):
    id: uuid.UUID
    task_id: uuid.UUID
    author_profile_id: uuid.UUID
    body: str
    created_at: datetime

    model_config = {"from_attributes": True}


class TaskCommentListResponse(BaseModel):
    comments: list[TaskCommentOut]
    next_cursor: uuid.UUID | None


# ---------------------------------------------------------------------------
# Whiteboard schemas
# ---------------------------------------------------------------------------

WhiteboardExportFormat = Literal["png", "pdf"]
WhiteboardExportResolution = Literal["basic", "hi"]
WhiteboardExportStatus = Literal["pending", "generating", "ready", "failed"]


class WhiteboardSnapshotOut(BaseModel):
    collab_id: uuid.UUID
    version: int
    s3_key: str
    url: str
    url_expires_at: datetime
    created_at: datetime


class WhiteboardExportRequestOut(BaseModel):
    export_id: uuid.UUID
    status: WhiteboardExportStatus
    poll_url: str


class WhiteboardExportReadyOut(BaseModel):
    export_id: uuid.UUID
    status: WhiteboardExportStatus
    url: str | None = None
    url_expires_at: datetime | None = None
    mime_type: str | None = None
    resolution: str | None = None
    error: str | None = None
