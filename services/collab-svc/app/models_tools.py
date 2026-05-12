"""
collab-svc ORM models — P9 collab-tools extension.

New tables (all in `collab` schema):
- Task
- TaskComment
- WhiteboardSnapshot
- WhiteboardOp
- WhiteboardExport
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Column,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    LargeBinary,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.models import Base  # re-use same DeclarativeBase


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

TaskStatusEnum = Enum(
    "todo",
    "in_progress",
    "done",
    "blocked",
    name="task_status",
    schema="collab",
)

WhiteboardExportStatusEnum = Enum(
    "pending",
    "generating",
    "ready",
    "failed",
    name="whiteboard_export_status",
    schema="collab",
)


# ---------------------------------------------------------------------------
# Task
# ---------------------------------------------------------------------------


class Task(Base):
    __tablename__ = "task"
    __table_args__ = (
        Index(
            "idx_task_collab_order",
            "collab_id",
            "order_key",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "idx_task_collab_due",
            "collab_id",
            "due_date",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "idx_task_collab_status",
            "collab_id",
            "status",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        {"schema": "collab"},
    )

    id: uuid.UUID = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    collab_id: uuid.UUID = Column(
        UUID(as_uuid=True),
        ForeignKey("collab.collaboration.id", ondelete="CASCADE"),
        nullable=False,
    )
    title: str = Column(Text, nullable=False)
    description: str | None = Column(Text, nullable=True)
    assignee_profile_id: uuid.UUID | None = Column(UUID(as_uuid=True), nullable=True)
    due_date: date | None = Column(Date, nullable=True)
    status: str = Column(TaskStatusEnum, nullable=False, default="todo")
    order_key: str = Column(Text, nullable=False)
    created_by: uuid.UUID = Column(UUID(as_uuid=True), nullable=False)
    created_at: datetime = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: datetime = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    closed_at: datetime | None = Column(DateTime(timezone=True), nullable=True)
    deleted_at: datetime | None = Column(DateTime(timezone=True), nullable=True)

    comments: list[TaskComment] = relationship(
        "TaskComment", back_populates="task", lazy="noload"
    )


# ---------------------------------------------------------------------------
# TaskComment
# ---------------------------------------------------------------------------


class TaskComment(Base):
    __tablename__ = "task_comment"
    __table_args__ = (
        Index(
            "idx_task_comment_task",
            "task_id",
            "created_at",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        {"schema": "collab"},
    )

    id: uuid.UUID = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    task_id: uuid.UUID = Column(
        UUID(as_uuid=True),
        ForeignKey("collab.task.id", ondelete="CASCADE"),
        nullable=False,
    )
    author_profile_id: uuid.UUID = Column(UUID(as_uuid=True), nullable=False)
    body: str = Column(Text, nullable=False)
    created_at: datetime = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    deleted_at: datetime | None = Column(DateTime(timezone=True), nullable=True)

    task: Task = relationship("Task", back_populates="comments")


# ---------------------------------------------------------------------------
# WhiteboardSnapshot
# ---------------------------------------------------------------------------


class WhiteboardSnapshot(Base):
    __tablename__ = "whiteboard_snapshot"
    __table_args__ = (
        Index("idx_whiteboard_snapshot_collab_version", "collab_id", "version"),
        {"schema": "collab"},
    )

    id: uuid.UUID = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    collab_id: uuid.UUID = Column(
        UUID(as_uuid=True),
        ForeignKey("collab.collaboration.id", ondelete="CASCADE"),
        nullable=False,
    )
    s3_key: str = Column(Text, nullable=False)
    version: int = Column(BigInteger, nullable=False, default=0)
    created_at: datetime = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


# ---------------------------------------------------------------------------
# WhiteboardOp (Y.js binary op log)
# ---------------------------------------------------------------------------


class WhiteboardOp(Base):
    __tablename__ = "whiteboard_op"
    __table_args__ = (
        Index("idx_whiteboard_op_collab_lamport", "collab_id", "lamport"),
        {"schema": "collab"},
    )

    id: uuid.UUID = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    collab_id: uuid.UUID = Column(
        UUID(as_uuid=True),
        ForeignKey("collab.collaboration.id", ondelete="CASCADE"),
        nullable=False,
    )
    lamport: int = Column(BigInteger, nullable=False)
    actor_profile_id: uuid.UUID = Column(UUID(as_uuid=True), nullable=False)
    op_data: bytes = Column(LargeBinary, nullable=False)
    applied_at: datetime = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


# ---------------------------------------------------------------------------
# WhiteboardExport
# ---------------------------------------------------------------------------


class WhiteboardExport(Base):
    __tablename__ = "whiteboard_export"
    __table_args__ = (
        Index("idx_whiteboard_export_collab", "collab_id", "requested_at"),
        Index("idx_whiteboard_export_requested_by", "requested_by"),
        {"schema": "collab"},
    )

    id: uuid.UUID = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    collab_id: uuid.UUID = Column(
        UUID(as_uuid=True),
        ForeignKey("collab.collaboration.id", ondelete="CASCADE"),
        nullable=False,
    )
    requested_by: uuid.UUID = Column(UUID(as_uuid=True), nullable=False)
    format: str = Column(Text, nullable=False)        # 'png' | 'pdf'
    resolution: str = Column(Text, nullable=False)    # 'basic' | 'hi'
    status: str = Column(WhiteboardExportStatusEnum, nullable=False, default="pending")
    s3_key: str | None = Column(Text, nullable=True)
    error_detail: str | None = Column(Text, nullable=True)
    requested_at: datetime = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: datetime | None = Column(DateTime(timezone=True), nullable=True)
    expires_at: datetime | None = Column(DateTime(timezone=True), nullable=True)


