"""
collab-svc core business logic:
- Create collaboration from match.created
- Status transitions with state machine enforcement
- Feedback upsert (idempotent)
- List / detail queries with cursor pagination
- Search (tsvector)
- Block handling
"""

from __future__ import annotations

import base64
import json
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import and_, func, or_, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_collab_settings
from app.domain.state_machine import InvalidTransitionError, is_terminal, validate_transition
from app.models import (
    Collaboration,
    CollabFeedback,
    CollabParticipantNameCache,
    CollabStatusEvent,
)
from app.schemas import FeedbackRequest

logger = logging.getLogger(__name__)
settings = get_collab_settings()


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


async def create_collaboration(
    db: AsyncSession,
    profile_id_a: uuid.UUID,
    profile_id_b: uuid.UUID,
    match_id: uuid.UUID | None = None,
) -> Collaboration:
    """
    Idempotent — unique index on (LEAST, GREATEST) prevents duplicates.
    Returns existing row on conflict.
    """
    least = min(profile_id_a, profile_id_b)
    greatest = max(profile_id_a, profile_id_b)

    stmt = (
        pg_insert(Collaboration)
        .values(
            profile_id_a=profile_id_a,
            profile_id_b=profile_id_b,
            least_participant=least,
            greatest_participant=greatest,
            status="still_deciding",
        )
        .on_conflict_do_nothing(constraint="collaboration_participants_unique")
        .returning(Collaboration)
    )
    result = await db.execute(stmt)
    row = result.scalars().first()

    if row is None:
        # Already exists — fetch it
        existing = await db.execute(
            select(Collaboration).where(
                Collaboration.least_participant == least,
                Collaboration.greatest_participant == greatest,
            )
        )
        row = existing.scalars().one()

    await db.commit()
    return row


# ---------------------------------------------------------------------------
# Get / List
# ---------------------------------------------------------------------------


async def get_collab(
    db: AsyncSession,
    collab_id: uuid.UUID,
    profile_id: uuid.UUID,
) -> Collaboration | None:
    """Return collab only if caller is a participant."""
    result = await db.execute(
        select(Collaboration).where(
            Collaboration.id == collab_id,
            or_(
                Collaboration.profile_id_a == profile_id,
                Collaboration.profile_id_b == profile_id,
            ),
        )
    )
    return result.scalars().first()


async def list_collabs(
    db: AsyncSession,
    profile_id: uuid.UUID,
    status_filter: str | None = None,  # "active", "past", "all"
    q: str | None = None,
    cursor: str | None = None,
    limit: int = 20,
    include_archived: bool = False,
) -> tuple[list[Collaboration], str | None]:
    """Cursor-paginated list with optional full-text search."""
    limit = min(limit, 50)

    base_where = or_(
        Collaboration.profile_id_a == profile_id,
        Collaboration.profile_id_b == profile_id,
    )

    # Status filter
    if status_filter == "active":
        status_cond = and_(
            Collaboration.status.in_(["still_deciding", "in_progress"]),
            Collaboration.archived_at.is_(None),
        )
    elif status_filter == "past":
        status_cond = or_(
            Collaboration.status.in_(["completed", "didnt_work_out"]),
            Collaboration.archived_at.isnot(None),
        )
    else:
        status_cond = text("TRUE")
        if not include_archived:
            status_cond = Collaboration.archived_at.is_(None)

    # Full-text search
    if q:
        ts_query = func.plainto_tsquery("english", q)
        fts_cond = Collaboration.search_vector.op("@@")(ts_query)
        rank_col = func.ts_rank_cd(Collaboration.search_vector, ts_query).label("rank")
    else:
        fts_cond = text("TRUE")
        rank_col = text("0.0").label("rank")

    # Cursor decode
    cursor_filter = text("TRUE")
    if cursor:
        try:
            cursor_data = json.loads(base64.urlsafe_b64decode(cursor + "==").decode())
            cursor_ts = datetime.fromisoformat(cursor_data["last_activity_at"])
            cursor_id = uuid.UUID(cursor_data["id"])
            cursor_filter = or_(
                Collaboration.last_activity_at < cursor_ts,
                and_(
                    Collaboration.last_activity_at == cursor_ts,
                    Collaboration.id < cursor_id,
                ),
            )
        except Exception:
            cursor_filter = text("TRUE")

    stmt = (
        select(Collaboration, rank_col)
        .where(and_(base_where, status_cond, fts_cond, cursor_filter))
        .order_by(text("rank DESC"), Collaboration.last_activity_at.desc(), Collaboration.id.desc())
        .limit(limit + 1)
    )

    result = await db.execute(stmt)
    rows = result.all()

    collabs = [r[0] for r in rows]
    next_cursor: str | None = None

    if len(collabs) > limit:
        collabs = collabs[:limit]
        last = collabs[-1]
        cursor_payload = {
            "last_activity_at": last.last_activity_at.isoformat(),
            "id": str(last.id),
        }
        next_cursor = base64.urlsafe_b64encode(
            json.dumps(cursor_payload).encode()
        ).decode().rstrip("=")

    return collabs, next_cursor


# ---------------------------------------------------------------------------
# Update (title/description)
# ---------------------------------------------------------------------------


async def patch_collab(
    db: AsyncSession,
    collab: Collaboration,
    title: str | None,
    description: str | None,
) -> Collaboration:
    if title is not None:
        collab.title = title
    if description is not None:
        collab.description = description
    collab.updated_at = datetime.now(UTC)
    db.add(collab)
    await db.commit()
    await db.refresh(collab)
    # Refresh search vector via DB function
    await db.execute(
        text("SELECT collab.refresh_search_vector(:cid)").bindparams(cid=str(collab.id))
    )
    await db.commit()
    return collab


# ---------------------------------------------------------------------------
# Status transition
# ---------------------------------------------------------------------------


async def transition_status(
    db: AsyncSession,
    collab: Collaboration,
    new_status: str,
    actor_profile_id: uuid.UUID,
    note: str | None = None,
) -> CollabStatusEvent:
    """
    Apply a status transition. Raises InvalidTransitionError on bad transitions.
    Side-effects: sets completed_at, archive_at, clears nudge_sent_at per spec.
    """
    validate_transition(collab.status, new_status)

    prev_status = collab.status
    now = datetime.now(UTC)

    # Side-effects
    if new_status in ("completed", "didnt_work_out"):
        collab.archive_at = now
        if new_status == "completed":
            collab.completed_at = now
    elif new_status == "in_progress":
        collab.nudge_sent_at = None
        # Reset archive_at based on last_activity_at + 30d
        collab.archive_at = collab.last_activity_at + timedelta(days=30)
    elif new_status == "still_deciding":
        collab.nudge_sent_at = None
        collab.archive_at = collab.last_activity_at + timedelta(days=30)

    collab.status = new_status
    collab.updated_at = now
    db.add(collab)

    event = CollabStatusEvent(
        collab_id=collab.id,
        actor_profile_id=actor_profile_id,
        prev_status=prev_status,
        new_status=new_status,
        note=note,
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)
    return event


# ---------------------------------------------------------------------------
# Feedback (idempotent upsert)
# ---------------------------------------------------------------------------


async def upsert_feedback(
    db: AsyncSession,
    collab: Collaboration,
    actor_profile_id: uuid.UUID,
    req: FeedbackRequest,
) -> CollabFeedback:
    """
    Idempotent per (collab_id, from_profile_id, target).
    ON CONFLICT DO UPDATE.
    """
    # Determine to_profile_id
    if req.target == "partner":
        if collab.profile_id_a == actor_profile_id:
            to_profile_id = collab.profile_id_b
        else:
            to_profile_id = collab.profile_id_a
    else:
        to_profile_id = None

    now = datetime.now(UTC)

    stmt = (
        pg_insert(CollabFeedback)
        .values(
            collab_id=collab.id,
            from_profile_id=actor_profile_id,
            to_profile_id=to_profile_id,
            target=req.target,
            rating=req.rating,
            tags=req.tags,
            comment=req.comment,
            created_at=now,
        )
        .on_conflict_do_update(
            constraint="collab_feedback_unique",
            set_={
                "rating": req.rating,
                "tags": req.tags,
                "comment": req.comment,
                "created_at": now,
            },
        )
        .returning(CollabFeedback)
    )
    result = await db.execute(stmt)
    row = result.scalars().one()
    await db.commit()
    return row


# ---------------------------------------------------------------------------
# Block handling
# ---------------------------------------------------------------------------


async def apply_block(
    db: AsyncSession,
    profile_id_a: uuid.UUID,
    profile_id_b: uuid.UUID,
) -> None:
    """
    Mark all active collabs between the pair as read-only with archive_at = now+30d.
    """
    least = min(profile_id_a, profile_id_b)
    greatest = max(profile_id_a, profile_id_b)
    archive_at = datetime.now(UTC) + timedelta(days=30)

    await db.execute(
        update(Collaboration)
        .where(
            Collaboration.least_participant == least,
            Collaboration.greatest_participant == greatest,
            Collaboration.archived_at.is_(None),
        )
        .values(is_read_only=True, archive_at=archive_at, updated_at=datetime.now(UTC))
    )
    await db.commit()


# ---------------------------------------------------------------------------
# Activity update (from chat.message.sent)
# ---------------------------------------------------------------------------


async def update_last_activity(
    db: AsyncSession,
    collab_id: uuid.UUID,
    activity_at: datetime,
) -> None:
    await db.execute(
        update(Collaboration)
        .where(Collaboration.id == collab_id)
        .values(
            last_activity_at=activity_at,
            nudge_sent_at=None,
            updated_at=datetime.now(UTC),
        )
    )
    await db.commit()


# ---------------------------------------------------------------------------
# Name cache update (for search_vector)
# ---------------------------------------------------------------------------


async def upsert_name_cache(
    db: AsyncSession,
    collab_id: uuid.UUID,
    profile_id: uuid.UUID,
    display_name: str,
) -> None:
    stmt = (
        pg_insert(CollabParticipantNameCache)
        .values(collab_id=collab_id, profile_id=profile_id, display_name=display_name)
        .on_conflict_do_update(
            constraint="collab_name_cache_unique",
            set_={"display_name": display_name, "updated_at": datetime.now(UTC)},
        )
    )
    await db.execute(stmt)
    await db.commit()
    # Refresh search vector
    await db.execute(
        text("SELECT collab.refresh_search_vector(:cid)").bindparams(cid=str(collab_id))
    )
    await db.commit()
