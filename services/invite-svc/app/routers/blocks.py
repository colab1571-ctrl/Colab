"""
invite-svc — Block/unblock endpoints.

POST   /blocks/{profile_id}   Block a profile
DELETE /blocks/{profile_id}   Remove a block
GET    /blocks                List my blocks (paginated, 50/page)
"""

from __future__ import annotations

import base64
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import aio_pika
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models.invite import Block
from app.schemas.invite import BlockCard, BlockListResponse, BlockResponse, CreateBlockRequest, UnblockResponse
from app.services.events import emit_block_created, emit_block_removed
from app.services.profile_client import fetch_profile_cards

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/blocks", tags=["blocks"])


def _get_channel(request: Request) -> aio_pika.abc.AbstractChannel:
    return request.app.state.amqp_channel


def _require_user(request: Request) -> uuid.UUID:
    user_id = getattr(request.state, "profile_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    return uuid.UUID(str(user_id))


def _encode_cursor(created_at: datetime, profile_id: uuid.UUID) -> str:
    payload = json.dumps({"t": created_at.isoformat(), "id": str(profile_id)})
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
# POST /blocks/{profile_id}
# ---------------------------------------------------------------------------


@router.post("/{profile_id}", response_model=BlockResponse)
async def create_block(
    profile_id: uuid.UUID,
    body: CreateBlockRequest,
    request: Request,
    db: AsyncSession = Depends(get_session),
) -> BlockResponse:
    """
    Block a profile.
    One-way write, two-way effect: neither user appears in the other's feed/recs.
    Emits block.created + profile.blocked (for discovery-svc cache invalidation).
    """
    channel = _get_channel(request)
    caller_id = _require_user(request)

    if caller_id == profile_id:
        raise HTTPException(status_code=400, detail="Cannot block yourself")

    # Upsert — idempotent if already blocked
    existing = await db.execute(
        select(Block).where(
            Block.blocker_id == caller_id,
            Block.blocked_id == profile_id,
        )
    )
    block = existing.scalar_one_or_none()

    if block is None:
        block = Block(
            blocker_id=caller_id,
            blocked_id=profile_id,
            reason=body.reason,
        )
        db.add(block)
        await db.commit()
        await db.refresh(block)

        try:
            await emit_block_created(channel, caller_id, profile_id)
        except Exception as exc:
            logger.error("Failed to publish block.created: %s", exc)

    return BlockResponse(
        blocker_id=block.blocker_id,
        blocked_id=block.blocked_id,
        created_at=block.created_at,
    )


# ---------------------------------------------------------------------------
# DELETE /blocks/{profile_id}
# ---------------------------------------------------------------------------


@router.delete("/{profile_id}", response_model=UnblockResponse)
async def remove_block(
    profile_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_session),
) -> UnblockResponse:
    """
    Remove a block. Only the blocker can remove it.
    The blocked user has no knowledge of the block.
    """
    channel = _get_channel(request)
    caller_id = _require_user(request)

    result = await db.execute(
        select(Block).where(
            Block.blocker_id == caller_id,
            Block.blocked_id == profile_id,
        )
    )
    block = result.scalar_one_or_none()

    if not block:
        raise HTTPException(status_code=404, detail="Block not found")

    await db.delete(block)
    await db.commit()

    try:
        await emit_block_removed(channel, caller_id, profile_id)
    except Exception as exc:
        logger.error("Failed to publish block.removed: %s", exc)

    return UnblockResponse(unblocked=True)


# ---------------------------------------------------------------------------
# GET /blocks
# ---------------------------------------------------------------------------


@router.get("", response_model=BlockListResponse)
async def list_blocks(
    request: Request,
    cursor: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_session),
) -> BlockListResponse:
    """List profiles the calling user has blocked. Paginated, 50/page."""
    caller_id = _require_user(request)

    q = select(Block).where(Block.blocker_id == caller_id)

    if cursor:
        decoded = _decode_cursor(cursor)
        if decoded:
            cur_dt, cur_id = decoded
            q = q.where(
                Block.created_at < cur_dt
            )

    q = q.order_by(Block.created_at.desc()).limit(limit + 1)

    result = await db.execute(q)
    rows = result.scalars().all()

    has_next = len(rows) > limit
    items = rows[:limit]

    next_cursor = None
    if has_next and items:
        last = items[-1]
        next_cursor = _encode_cursor(last.created_at, last.blocked_id)

    # Fetch profile cards for blocked users
    blocked_ids = [b.blocked_id for b in items]
    cards = await fetch_profile_cards(blocked_ids)

    block_cards = [
        BlockCard(
            profile_id=b.blocked_id,
            display_name=cards.get(b.blocked_id, None) and cards[b.blocked_id].display_name,
            avatar_url=cards.get(b.blocked_id, None) and cards[b.blocked_id].avatar_url,
            blocked_at=b.created_at,
        )
        for b in items
    ]

    return BlockListResponse(items=block_cards, next_cursor=next_cursor)
