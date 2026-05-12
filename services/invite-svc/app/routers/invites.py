"""
invite-svc — Invite endpoints.

POST   /invites                  Send a Vibe Check
POST   /invites/{id}/accept      Accept (recipient only)
POST   /invites/{id}/reject      Reject (recipient only; silent to sender)
DELETE /invites/{id}             Cancel (sender only; pending state only)
GET    /invites/inbox            Received invites (cursor-paginated)
GET    /invites/sent             Sent invites (cursor-paginated)
"""

from __future__ import annotations

import base64
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import aio_pika
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_session
from app.models.invite import Block, CollabInvite
from app.schemas.invite import (
    AcceptInviteResponse,
    CancelInviteResponse,
    InviteCard,
    InviteListResponse,
    RejectInviteResponse,
    SendInviteRequest,
    SendInviteResponse,
)
from app.services.events import (
    emit_invite_accepted,
    emit_invite_cancelled,
    emit_invite_rejected,
    emit_invite_sent,
    emit_match_created,
)
from app.services.moderation import SynopsisFlagged, scan_synopsis
from app.services.profile_client import fetch_profile_cards
from app.services.quota import (
    check_and_increment_quota,
    check_idempotency,
    make_dedup_key,
    set_idempotency,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/invites", tags=["invites"])

settings = get_settings()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_redis(request: Request):  # type: ignore[return]
    return request.app.state.redis


def _get_channel(request: Request) -> aio_pika.abc.AbstractChannel:
    return request.app.state.amqp_channel


def _require_user(request: Request) -> uuid.UUID:
    """Extract authenticated profile_id from request state (set by auth middleware)."""
    user_id = getattr(request.state, "profile_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    return uuid.UUID(str(user_id))


async def _is_blocked(
    db: AsyncSession,
    profile_a: uuid.UUID,
    profile_b: uuid.UUID,
) -> bool:
    """Bidirectional block check: A→B or B→A."""
    result = await db.execute(
        select(Block).where(
            or_(
                and_(Block.blocker_id == profile_a, Block.blocked_id == profile_b),
                and_(Block.blocker_id == profile_b, Block.blocked_id == profile_a),
            )
        ).limit(1)
    )
    return result.scalar_one_or_none() is not None


def _encode_cursor(created_at: datetime, invite_id: uuid.UUID) -> str:
    payload = json.dumps({"t": created_at.isoformat(), "id": str(invite_id)})
    return base64.urlsafe_b64encode(payload.encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID] | None:
    try:
        payload = json.loads(base64.urlsafe_b64decode(cursor.encode()))
        dt = datetime.fromisoformat(payload["t"])
        uid = uuid.UUID(payload["id"])
        return dt, uid
    except Exception:
        return None


# ---------------------------------------------------------------------------
# POST /invites — Send Vibe Check
# ---------------------------------------------------------------------------


@router.post("", status_code=201, response_model=SendInviteResponse)
async def send_invite(
    body: SendInviteRequest,
    request: Request,
    db: AsyncSession = Depends(get_session),
    x_idempotency_key: Optional[str] = Header(None, alias="X-Idempotency-Key"),
) -> Any:
    """
    Send a Vibe Check invite.

    Flow:
      1. Auth → profile_id
      2. Block check (bidirectional)
      3. Idempotency dedup
      4. Entitlement + rolling 7-day quota (Lua atomic)
      5. Pre-send synopsis moderation
      6. DB insert (status=pending, archive_at=NOW()+30d)
      7. Publish invite.sent
      8. Return 201 {invite_id, quota_remaining, archive_at}
    """
    redis = _get_redis(request)
    channel = _get_channel(request)

    from_profile_id = _require_user(request)
    to_profile_id = body.to_profile_id

    # 1. Self-invite guard
    if from_profile_id == to_profile_id:
        raise HTTPException(status_code=400, detail="Cannot send invite to yourself")

    # 2. Block check
    if await _is_blocked(db, from_profile_id, to_profile_id):
        raise HTTPException(
            status_code=403,
            detail={"error": "blocked"},
        )

    # 3. Idempotency — client-supplied key or deterministic dedup
    idem_key = x_idempotency_key or make_dedup_key(from_profile_id, to_profile_id, body.synopsis)
    cached_resp = await check_idempotency(redis, idem_key)
    if cached_resp:
        try:
            return json.loads(cached_resp)
        except Exception:
            pass  # fall through to create

    # 4. Quota check (Lua atomic)
    probe_invite_id = uuid.uuid4()
    allowed, quota_remaining = await check_and_increment_quota(
        redis, from_profile_id, probe_invite_id
    )
    if not allowed:
        raise HTTPException(
            status_code=402,
            detail={
                "error": "quota_exceeded",
                "quota_remaining": 0,
                "upsell": True,
            },
        )

    # 5. Moderation pre-check (200ms timeout; allow on timeout per R-004)
    try:
        mod_case_id = await scan_synopsis(
            body.synopsis, from_profile_id, probe_invite_id
        )
    except SynopsisFlagged as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "synopsis_flagged",
                "reason": exc.reason,
            },
        )

    # 6. DB insert
    now = datetime.now(tz=timezone.utc)
    archive_at = now + timedelta(days=settings.invite_ttl_days)

    invite = CollabInvite(
        id=probe_invite_id,
        from_profile_id=from_profile_id,
        to_profile_id=to_profile_id,
        synopsis=body.synopsis,
        status="pending",
        mod_case_id=mod_case_id,
        created_at=now,
        archive_at=archive_at,
        idempotency_key=idem_key if x_idempotency_key else None,
    )
    db.add(invite)
    try:
        await db.commit()
    except Exception as exc:
        await db.rollback()
        # Unique constraint on idempotency_key → return cached or re-query
        logger.warning("invite insert conflict (idem_key=%s): %s", idem_key, exc)
        existing = await db.execute(
            select(CollabInvite).where(CollabInvite.idempotency_key == idem_key)
        )
        inv = existing.scalar_one_or_none()
        if inv:
            response_data = {
                "invite_id": str(inv.id),
                "status": inv.status,
                "quota_remaining": quota_remaining,
                "archive_at": inv.archive_at.isoformat(),
            }
            return response_data
        raise

    # 7. Publish invite.sent
    try:
        await emit_invite_sent(channel, probe_invite_id, from_profile_id, to_profile_id)
    except Exception as exc:
        logger.error("Failed to publish invite.sent: %s", exc)

    # 8. Cache idempotency + return
    response_data = {
        "invite_id": str(probe_invite_id),
        "status": "pending",
        "quota_remaining": quota_remaining,
        "archive_at": archive_at.isoformat(),
    }
    await set_idempotency(redis, idem_key, response_data)

    return SendInviteResponse(
        invite_id=probe_invite_id,
        status="pending",
        quota_remaining=quota_remaining,
        archive_at=archive_at,
    )


# ---------------------------------------------------------------------------
# POST /invites/{id}/accept
# ---------------------------------------------------------------------------


@router.post("/{invite_id}/accept", response_model=AcceptInviteResponse)
async def accept_invite(
    invite_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_session),
) -> AcceptInviteResponse:
    """
    Accept a Vibe Check. Recipient only.
    Checks for mirror invite (B→A also accepted) → emits match.created.
    Wrapped in a SELECT FOR UPDATE transaction to prevent race conditions.
    """
    channel = _get_channel(request)
    caller_id = _require_user(request)

    async with db.begin():
        # Lock the invite row
        result = await db.execute(
            select(CollabInvite)
            .where(CollabInvite.id == invite_id)
            .with_for_update()
        )
        invite = result.scalar_one_or_none()

        if not invite:
            raise HTTPException(status_code=404, detail="Invite not found")
        if invite.to_profile_id != caller_id:
            raise HTTPException(status_code=403, detail="Not the recipient")
        if invite.status != "pending":
            raise HTTPException(
                status_code=409, detail=f"Invite already in terminal state: {invite.status}"
            )

        now = datetime.now(tz=timezone.utc)
        invite.status = "accepted"
        invite.responded_at = now

        # Check for mirror invite (A←B already accepted) → mutual match
        mirror_result = await db.execute(
            select(CollabInvite).where(
                CollabInvite.from_profile_id == invite.to_profile_id,
                CollabInvite.to_profile_id == invite.from_profile_id,
                CollabInvite.status == "accepted",
            )
        )
        mirror = mirror_result.scalar_one_or_none()
        matched = mirror is not None

        # Flush (still inside transaction)
        await db.flush()

    # Publish events outside the transaction (at-least-once delivery)
    try:
        await emit_invite_accepted(
            channel, invite_id, invite.from_profile_id, invite.to_profile_id
        )
        if matched:
            await emit_match_created(
                channel,
                invite.from_profile_id,
                invite.to_profile_id,
                invite_id,
                mirror.id,  # type: ignore[union-attr]
            )
    except Exception as exc:
        logger.error("Failed to publish accept/match events: %s", exc)

    return AcceptInviteResponse(
        invite_id=invite_id,
        status="accepted",
        matched=matched,
    )


# ---------------------------------------------------------------------------
# POST /invites/{id}/reject
# ---------------------------------------------------------------------------


@router.post("/{invite_id}/reject", response_model=RejectInviteResponse)
async def reject_invite(
    invite_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_session),
) -> RejectInviteResponse:
    """
    Reject a Vibe Check. Recipient only. SILENT to sender (no push notification).
    Invite disappears from recipient's inbox; visible only in Journey G history.
    """
    channel = _get_channel(request)
    caller_id = _require_user(request)

    async with db.begin():
        result = await db.execute(
            select(CollabInvite)
            .where(CollabInvite.id == invite_id)
            .with_for_update()
        )
        invite = result.scalar_one_or_none()

        if not invite:
            raise HTTPException(status_code=404, detail="Invite not found")
        if invite.to_profile_id != caller_id:
            raise HTTPException(status_code=403, detail="Not the recipient")
        if invite.status != "pending":
            raise HTTPException(status_code=409, detail=f"Invite in terminal state: {invite.status}")

        now = datetime.now(tz=timezone.utc)
        invite.status = "rejected"
        invite.responded_at = now
        await db.flush()

    # Emit rejected event (silent=True tag; notification-svc will not deliver to sender)
    try:
        await emit_invite_rejected(
            channel, invite_id, invite.from_profile_id, invite.to_profile_id
        )
    except Exception as exc:
        logger.error("Failed to publish invite.rejected: %s", exc)

    return RejectInviteResponse(invite_id=invite_id, status="rejected")


# ---------------------------------------------------------------------------
# DELETE /invites/{id} — Cancel (sender only, pending only)
# ---------------------------------------------------------------------------


@router.delete("/{invite_id}", response_model=CancelInviteResponse)
async def cancel_invite(
    invite_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_session),
) -> CancelInviteResponse:
    """Cancel a sent invite. Sender only. Only valid when status=pending."""
    channel = _get_channel(request)
    caller_id = _require_user(request)

    async with db.begin():
        result = await db.execute(
            select(CollabInvite)
            .where(CollabInvite.id == invite_id)
            .with_for_update()
        )
        invite = result.scalar_one_or_none()

        if not invite:
            raise HTTPException(status_code=404, detail="Invite not found")
        if invite.from_profile_id != caller_id:
            raise HTTPException(status_code=403, detail="Not the sender")
        if invite.status != "pending":
            raise HTTPException(
                status_code=409, detail=f"Cannot cancel invite in state: {invite.status}"
            )

        invite.status = "cancelled"
        invite.responded_at = datetime.now(tz=timezone.utc)
        await db.flush()

    try:
        await emit_invite_cancelled(
            channel, invite_id, invite.from_profile_id, invite.to_profile_id
        )
    except Exception as exc:
        logger.error("Failed to publish invite.cancelled: %s", exc)

    return CancelInviteResponse(invite_id=invite_id, status="cancelled")


# ---------------------------------------------------------------------------
# GET /invites/inbox
# ---------------------------------------------------------------------------


@router.get("/inbox", response_model=InviteListResponse)
async def get_inbox(
    request: Request,
    status_filter: Optional[str] = Query(None, alias="status"),
    cursor: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_session),
) -> InviteListResponse:
    """
    List received invites (to_profile_id = me).
    Block-aware: invites from blocked senders excluded.
    Cursor-based keyset pagination on (created_at DESC, id).
    """
    caller_id = _require_user(request)

    # Base query: recipient = me, exclude invites from/to blocked users
    blocked_senders_sq = (
        select(Block.blocker_id)
        .where(Block.blocked_id == caller_id)
        .union(
            select(Block.blocked_id).where(Block.blocker_id == caller_id)
        )
        .scalar_subquery()
    )

    q = select(CollabInvite).where(
        CollabInvite.to_profile_id == caller_id,
        CollabInvite.from_profile_id.not_in(blocked_senders_sq),
    )

    # Status filter
    valid_statuses = ("pending", "accepted", "rejected", "expired", "cancelled")
    if status_filter and status_filter != "all":
        if status_filter not in valid_statuses:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status_filter}")
        q = q.where(CollabInvite.status == status_filter)
    elif not status_filter or status_filter == "pending":
        q = q.where(CollabInvite.status == "pending")

    # Cursor pagination
    if cursor:
        decoded = _decode_cursor(cursor)
        if decoded:
            cur_dt, cur_id = decoded
            q = q.where(
                or_(
                    CollabInvite.created_at < cur_dt,
                    and_(
                        CollabInvite.created_at == cur_dt,
                        CollabInvite.id < cur_id,
                    ),
                )
            )

    q = q.order_by(CollabInvite.created_at.desc(), CollabInvite.id.desc()).limit(limit + 1)

    result = await db.execute(q)
    rows = result.scalars().all()

    has_next = len(rows) > limit
    items = rows[:limit]

    next_cursor = None
    if has_next and items:
        last = items[-1]
        next_cursor = _encode_cursor(last.created_at, last.id)

    # Count total pending (for badge display)
    count_result = await db.execute(
        select(func.count()).where(
            CollabInvite.to_profile_id == caller_id,
            CollabInvite.status == "pending",
            CollabInvite.from_profile_id.not_in(blocked_senders_sq),
        )
    )
    total_pending = count_result.scalar() or 0

    # Fetch profile cards for from_profile_ids
    from_ids = list({inv.from_profile_id for inv in items})
    cards = await fetch_profile_cards(from_ids)

    invite_cards = [
        InviteCard(
            invite_id=inv.id,
            from_profile=cards.get(inv.from_profile_id),
            to_profile=None,  # not needed in inbox view
            synopsis=inv.synopsis,
            status=inv.status,  # type: ignore[arg-type]
            created_at=inv.created_at,
            archive_at=inv.archive_at,
            ai_match_score=float(inv.ai_match_score) if inv.ai_match_score else None,
            responded_at=inv.responded_at,
        )
        for inv in items
    ]

    return InviteListResponse(
        items=invite_cards,
        next_cursor=next_cursor,
        total_pending=total_pending,
    )


# ---------------------------------------------------------------------------
# GET /invites/sent
# ---------------------------------------------------------------------------


@router.get("/sent", response_model=InviteListResponse)
async def get_sent(
    request: Request,
    status_filter: Optional[str] = Query(None, alias="status"),
    cursor: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_session),
) -> InviteListResponse:
    """
    List sent invites (from_profile_id = me).
    Block-aware: invites to blocked recipients excluded.
    """
    caller_id = _require_user(request)

    blocked_recipients_sq = (
        select(Block.blocker_id)
        .where(Block.blocked_id == caller_id)
        .union(
            select(Block.blocked_id).where(Block.blocker_id == caller_id)
        )
        .scalar_subquery()
    )

    q = select(CollabInvite).where(
        CollabInvite.from_profile_id == caller_id,
        CollabInvite.to_profile_id.not_in(blocked_recipients_sq),
    )

    valid_statuses = ("pending", "accepted", "rejected", "expired", "cancelled")
    if status_filter and status_filter != "all":
        if status_filter not in valid_statuses:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status_filter}")
        q = q.where(CollabInvite.status == status_filter)

    if cursor:
        decoded = _decode_cursor(cursor)
        if decoded:
            cur_dt, cur_id = decoded
            q = q.where(
                or_(
                    CollabInvite.created_at < cur_dt,
                    and_(
                        CollabInvite.created_at == cur_dt,
                        CollabInvite.id < cur_id,
                    ),
                )
            )

    q = q.order_by(CollabInvite.created_at.desc(), CollabInvite.id.desc()).limit(limit + 1)

    result = await db.execute(q)
    rows = result.scalars().all()

    has_next = len(rows) > limit
    items = rows[:limit]

    next_cursor = None
    if has_next and items:
        last = items[-1]
        next_cursor = _encode_cursor(last.created_at, last.id)

    # Count total pending (for UI indicators)
    count_result = await db.execute(
        select(func.count()).where(
            CollabInvite.from_profile_id == caller_id,
            CollabInvite.status == "pending",
        )
    )
    total_pending = count_result.scalar() or 0

    to_ids = list({inv.to_profile_id for inv in items})
    cards = await fetch_profile_cards(to_ids)

    invite_cards = [
        InviteCard(
            invite_id=inv.id,
            from_profile=None,
            to_profile=cards.get(inv.to_profile_id),
            synopsis=inv.synopsis,
            status=inv.status,  # type: ignore[arg-type]
            created_at=inv.created_at,
            archive_at=inv.archive_at,
            ai_match_score=float(inv.ai_match_score) if inv.ai_match_score else None,
            responded_at=inv.responded_at,
        )
        for inv in items
    ]

    return InviteListResponse(
        items=invite_cards,
        next_cursor=next_cursor,
        total_pending=total_pending,
    )
