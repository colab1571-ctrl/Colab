"""
billing-svc — Admin API endpoints.

GET  /admin/billing/users/{user_id}/360
POST /admin/billing/refunds/{id}/decide
POST /admin/billing/grants
POST /admin/billing/credit-adjustment
PUT  /admin/billing/tier-config
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.billing import (
    CreditTransaction,
    DunningCase,
    EntitlementSnapshot,
    Invoice,
    RefundRequest,
    Subscription,
)
from app.schemas.billing import (
    AdminCreditAdjustment,
    AdminGrantRequest,
    AdminRefundDecide,
    AdminTierConfigUpdate,
)
from app.services.credits import admin_adjust_credits
from app.services.entitlements import AXIS_REGISTRY, TIER_DEFAULTS, invalidate_entitlement_cache
from app.services.refunds import admin_decide_refund
from app.services.subscriptions import publish_entitlement_changed
from colab_common.auth import AuthUser, require_role
from colab_common.db import get_session
from colab_common.errors import NotFoundError, ValidationError

router = APIRouter(prefix="/admin/billing", tags=["admin-billing"])

logger = logging.getLogger(__name__)


def _get_redis(request: Request):  # type: ignore[return]
    return request.app.state.redis


def _get_amqp(request: Request):  # type: ignore[return]
    return request.app.state.amqp_channel


@router.get("/users/{user_id}/360")
async def user_360(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_session),
    admin: AuthUser = Depends(require_role("admin")),
) -> dict[str, Any]:
    """Full billing view: subscriptions, invoices, credits, refunds, dunning."""
    subs = (await db.execute(
        select(Subscription).where(Subscription.user_id == user_id)
        .order_by(Subscription.created_at.desc())
    )).scalars().all()

    invoices = (await db.execute(
        select(Invoice).where(Invoice.user_id == user_id)
        .order_by(Invoice.created_at.desc()).limit(50)
    )).scalars().all()

    txns = (await db.execute(
        select(CreditTransaction).where(CreditTransaction.user_id == user_id)
        .order_by(CreditTransaction.created_at.desc()).limit(100)
    )).scalars().all()

    refunds = (await db.execute(
        select(RefundRequest).where(RefundRequest.user_id == user_id)
    )).scalars().all()

    dunning = (await db.execute(
        select(DunningCase).where(DunningCase.user_id == user_id)
    )).scalars().all()

    return {
        "subscriptions": [
            {
                "id": str(s.id), "source": s.source, "gateway": s.gateway,
                "tier": s.tier, "status": s.status, "period_end": s.current_period_end.isoformat(),
            }
            for s in subs
        ],
        "invoices": [
            {
                "id": str(i.id), "amount_minor": i.amount_minor, "currency": i.currency,
                "status": i.status, "created_at": i.created_at.isoformat(),
            }
            for i in invoices
        ],
        "credit_transactions": [
            {
                "id": str(t.id), "delta": t.delta, "reason": t.reason,
                "status": t.status, "created_at": t.created_at.isoformat(),
            }
            for t in txns
        ],
        "refund_requests": [
            {
                "id": str(r.id), "status": r.status, "within_14d": r.within_14d,
                "requested_at": r.requested_at.isoformat(),
            }
            for r in refunds
        ],
        "dunning_cases": [
            {
                "id": str(d.id), "state": d.state, "opened_at": d.opened_at.isoformat(),
            }
            for d in dunning
        ],
    }


@router.post("/refunds/{refund_id}/decide")
async def decide_refund(
    refund_id: uuid.UUID,
    body: AdminRefundDecide,
    request: Request,
    db: AsyncSession = Depends(get_session),
    admin: AuthUser = Depends(require_role("admin")),
) -> dict[str, Any]:
    rr = await admin_decide_refund(
        db=db,
        refund_request_id=refund_id,
        admin_user_id=uuid.UUID(admin.user_id),
        decision=body.decision,
        internal_note=body.internal_note,
    )
    await db.commit()
    return {"refund_request_id": str(rr.id), "status": rr.status}


@router.post("/grants", status_code=201)
async def create_entitlement_grant(
    body: AdminGrantRequest,
    request: Request,
    db: AsyncSession = Depends(get_session),
    admin: AuthUser = Depends(require_role("admin")),
) -> dict[str, Any]:
    if body.axis_key not in AXIS_REGISTRY:
        raise ValidationError(f"Unknown axis_key: {body.axis_key}")

    snap = EntitlementSnapshot(
        id=uuid.uuid4(),
        user_id=body.user_id,
        axis_key=body.axis_key,
        value={"v": body.value},
        source="grant",
        source_ref=uuid.UUID(admin.user_id),
        expires_at=body.expires_at,
    )
    db.add(snap)
    await db.flush()

    redis = _get_redis(request)
    amqp = _get_amqp(request)
    await invalidate_entitlement_cache(redis, body.user_id)
    await publish_entitlement_changed(amqp, body.user_id, axis_keys=[body.axis_key])
    await db.commit()

    return {"snapshot_id": str(snap.id), "status": "granted"}


@router.post("/credit-adjustment", status_code=201)
async def adjust_credits(
    body: AdminCreditAdjustment,
    db: AsyncSession = Depends(get_session),
    admin: AuthUser = Depends(require_role("admin")),
) -> dict[str, Any]:
    tx = await admin_adjust_credits(
        db=db,
        user_id=body.user_id,
        delta=body.delta,
        reason=body.reason,
        admin_action_id=f"admin:{admin.user_id}:{datetime.now(UTC).timestamp()}",
    )
    await db.commit()
    return {"transaction_id": str(tx.id), "delta": tx.delta}


@router.put("/tier-config")
async def update_tier_config(
    body: AdminTierConfigUpdate,
    request: Request,
    db: AsyncSession = Depends(get_session),
    admin: AuthUser = Depends(require_role("admin")),
) -> dict[str, Any]:
    """
    Update axis value for a tier. Broadcasts entitlement.changed to all affected users.
    In production: persists to EntitlementConfig table and triggers batch invalidation.
    """
    if body.axis_key not in AXIS_REGISTRY:
        raise ValidationError(f"Unknown axis_key: {body.axis_key}")

    # Update in-memory defaults (production: persist to DB)
    if body.tier in TIER_DEFAULTS:
        TIER_DEFAULTS[body.tier][body.axis_key] = body.value

    # Batch invalidation: emit a broadcast event
    amqp = _get_amqp(request)
    import aio_pika, json
    message = aio_pika.Message(
        body=json.dumps({
            "broadcast": True,
            "tier": body.tier,
            "axis_keys": [body.axis_key],
        }).encode(),
        content_type="application/json",
        delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
    )
    await amqp.default_exchange.publish(message, routing_key="entitlement.changed")

    logger.info("Admin %s updated tier_config: tier=%s axis=%s", admin.user_id, body.tier, body.axis_key)
    return {"status": "updated", "tier": body.tier, "axis_key": body.axis_key}
