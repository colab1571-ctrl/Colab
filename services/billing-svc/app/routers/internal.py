"""
billing-svc — Internal (service-to-service) API.

POST /internal/credits/reserve
POST /internal/credits/commit
POST /internal/credits/release
GET  /internal/entitlements/{user_id}
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.billing import (
    CommitCreditsRequest,
    EntitlementsResponse,
    ReleaseCreditsRequest,
    ReserveCreditsRequest,
    ReserveCreditsResponse,
)
from app.services.credits import (
    InsufficientCreditsError,
    commit_reservation,
    release_reservation,
    reserve_credits,
)
from app.services.entitlements import get_cached_entitlements
from colab_common.auth import require_role
from colab_common.db import get_session

router = APIRouter(prefix="/internal", tags=["internal"])

logger = logging.getLogger(__name__)


def _get_redis(request: Request):  # type: ignore[return]
    return request.app.state.redis


@router.post("/credits/reserve", response_model=ReserveCreditsResponse)
async def reserve_credits_endpoint(
    body: ReserveCreditsRequest,
    db: AsyncSession = Depends(get_session),
    _svc: Any = Depends(require_role("service", "admin")),
) -> ReserveCreditsResponse:
    """
    Reserve credits pessimistically. Returns 402 if insufficient.
    Uses SERIALIZABLE isolation.
    """
    idem_key = body.idempotency_key or f"reserve:{body.user_id}:{body.reference_id}"
    try:
        reservation_id = await reserve_credits(
            db=db,
            user_id=body.user_id,
            amount=body.amount,
            reference_kind=body.reference_kind,
            reference_id=body.reference_id,
            idempotency_key=idem_key,
        )
        await db.commit()
        return ReserveCreditsResponse(reservation_id=reservation_id)
    except InsufficientCreditsError as exc:
        raise HTTPException(
            status_code=402,
            detail={
                "error": "insufficient_credits",
                "balance": exc.balance,
                "requested": exc.requested,
            },
        )


@router.post("/credits/commit", status_code=204)
async def commit_credits_endpoint(
    body: CommitCreditsRequest,
    db: AsyncSession = Depends(get_session),
    _svc: Any = Depends(require_role("service", "admin")),
) -> None:
    await commit_reservation(db, body.reservation_id)
    await db.commit()


@router.post("/credits/release", status_code=204)
async def release_credits_endpoint(
    body: ReleaseCreditsRequest,
    db: AsyncSession = Depends(get_session),
    _svc: Any = Depends(require_role("service", "admin")),
) -> None:
    await release_reservation(db, body.reservation_id, body.reason)
    await db.commit()


@router.get("/entitlements/{user_id}", response_model=EntitlementsResponse)
async def get_entitlements_for_user(
    user_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_session),
    _svc: Any = Depends(require_role("service", "admin")),
) -> EntitlementsResponse:
    """Server-side entitlement check for any user (service-to-service)."""
    redis = _get_redis(request)
    resolved = await get_cached_entitlements(redis, db, user_id)
    return EntitlementsResponse(
        axes=resolved.axes,
        tier=resolved.tier,  # type: ignore[arg-type]
        subscription_status=resolved.subscription_status,
        current_period_end=resolved.current_period_end,
    )
