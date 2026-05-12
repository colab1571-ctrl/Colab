"""
admin-svc — Billing admin endpoints.

Tier definitions, EntitlementConfig writes, Stripe Price mapping, refund decisions,
credit grants.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import write as audit_write
from app.config import get_settings
from app.db import get_db
from app.models import EntitlementConfig
from app.rbac import requires_permission, get_admin_user_id

router = APIRouter(prefix="/admin/v1", tags=["billing"])


async def _billing_client() -> httpx.AsyncClient:
    settings = get_settings()
    return httpx.AsyncClient(base_url=settings.billing_svc_url, timeout=10.0)


# ---------------------------------------------------------------------------
# Tier & entitlement config
# ---------------------------------------------------------------------------

@router.get("/tiers")
async def get_tiers(
    request: Request,
    sess: AsyncSession = Depends(get_db),
    _: None = Depends(requires_permission("tier", "read")),
) -> Any:
    """Return currently-active entitlement values per tier."""
    now = datetime.now(tz=timezone.utc)
    rows = await sess.execute(
        select(EntitlementConfig)
        .where(
            EntitlementConfig.effective_at <= now,
            (EntitlementConfig.superseded_at == None)  # noqa: E711
            | (EntitlementConfig.superseded_at > now),
        )
        .order_by(EntitlementConfig.tier, EntitlementConfig.axis_key)
    )
    configs = rows.scalars().all()
    # Group by tier
    result: dict[str, dict[str, Any]] = {}
    for cfg in configs:
        result.setdefault(cfg.tier, {})[cfg.axis_key] = {
            "value": cfg.value,
            "currency": cfg.currency,
            "effective_at": cfg.effective_at.isoformat(),
        }
    return result


@router.put("/tiers/{tier}")
async def update_tier(
    tier: str,
    request: Request,
    body: dict[str, Any] = Body(...),
    sess: AsyncSession = Depends(get_db),
    _: None = Depends(requires_permission("tier", "write")),
) -> Any:
    """
    Update entitlement axes for a tier.

    Appends new EntitlementConfig rows and supersedes prior rows.
    Broadcasts entitlement.changed event.
    """
    admin_user_id = uuid.UUID(get_admin_user_id(request))
    ip = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip() or (
        request.client.host if request.client else None
    )
    now = datetime.now(tz=timezone.utc)
    axes: list[dict[str, Any]] = body.get("axes", [])
    reason = body.get("reason", "")

    updated: list[dict[str, Any]] = []
    for axis in axes:
        axis_key = axis["axis_key"]
        # Supersede existing active rows
        existing = await sess.execute(
            select(EntitlementConfig)
            .where(
                EntitlementConfig.tier == tier,
                EntitlementConfig.axis_key == axis_key,
                EntitlementConfig.superseded_at == None,  # noqa: E711
            )
        )
        for old in existing.scalars().all():
            old.superseded_at = now

        effective_at = axis.get("effective_at")
        if effective_at:
            effective_dt = datetime.fromisoformat(effective_at)
        else:
            effective_dt = now

        new_row = EntitlementConfig(
            id=uuid.uuid4(),
            tier=tier,
            axis_key=axis_key,
            value=axis["value"],
            currency=axis.get("currency"),
            effective_at=effective_dt,
            updated_by=admin_user_id,
        )
        sess.add(new_row)
        updated.append({"tier": tier, "axis_key": axis_key, "value": axis["value"]})

    await audit_write(
        sess,
        admin_user_id=admin_user_id,
        action_type="entitlement.update",
        target_kind="tier",
        target_id=tier,
        payload_after={"axes": updated, "reason": reason},
        reason=reason,
        ip=ip,
        user_agent=request.headers.get("user-agent"),
    )
    await sess.commit()

    # Broadcast entitlement.changed (fire-and-forget via billing-svc internal endpoint)
    try:
        async with await _billing_client() as client:
            await client.post(
                "/billing/internal/entitlement-changed",
                json={"tier": tier, "axes": updated},
                headers={"X-Service-Auth": "admin-svc"},
                timeout=5.0,
            )
    except Exception:
        pass  # logged by billing-svc; does not fail the admin request

    return {"updated": updated, "tier": tier}


@router.get("/entitlements")
async def get_entitlements(
    request: Request,
    sess: AsyncSession = Depends(get_db),
    _: None = Depends(requires_permission("entitlement", "read")),
) -> Any:
    """All active entitlement rows across tiers."""
    return await get_tiers(request, sess=sess, _=_)


@router.put("/entitlements")
async def update_entitlements(
    request: Request,
    body: list[dict[str, Any]] = Body(...),
    sess: AsyncSession = Depends(get_db),
    _: None = Depends(requires_permission("entitlement", "write")),
) -> Any:
    """Bulk update entitlements across multiple tiers."""
    admin_user_id = uuid.UUID(get_admin_user_id(request))
    now = datetime.now(tz=timezone.utc)
    updated = []

    for item in body:
        tier = item["tier"]
        axis_key = item["axis_key"]
        existing = await sess.execute(
            select(EntitlementConfig)
            .where(
                EntitlementConfig.tier == tier,
                EntitlementConfig.axis_key == axis_key,
                EntitlementConfig.superseded_at == None,  # noqa: E711
            )
        )
        for old in existing.scalars().all():
            old.superseded_at = now

        effective_at = item.get("effective_at")
        effective_dt = datetime.fromisoformat(effective_at) if effective_at else now

        new_row = EntitlementConfig(
            id=uuid.uuid4(),
            tier=tier,
            axis_key=axis_key,
            value=item["value"],
            currency=item.get("currency"),
            effective_at=effective_dt,
            updated_by=admin_user_id,
        )
        sess.add(new_row)
        updated.append(item)

    await audit_write(
        sess,
        admin_user_id=admin_user_id,
        action_type="entitlement.update",
        target_kind="entitlement_axis",
        target_id="bulk",
        payload_after={"items": updated},
        ip=(request.headers.get("x-forwarded-for") or "").split(",")[0].strip(),
        user_agent=request.headers.get("user-agent"),
    )
    await sess.commit()
    return {"updated": updated}


# ---------------------------------------------------------------------------
# Refunds
# ---------------------------------------------------------------------------

@router.get("/refunds")
async def get_refunds(
    request: Request,
    status: str | None = Query("pending"),
    _: None = Depends(requires_permission("refund", "read")),
) -> Any:
    async with await _billing_client() as client:
        resp = await client.get(
            "/billing/admin/refunds",
            params={"status": status} if status else {},
            headers={"X-Service-Auth": "admin-svc"},
        )
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


@router.post("/refunds/{refund_id}/decision")
async def decide_refund(
    refund_id: uuid.UUID,
    request: Request,
    body: dict[str, Any] = Body(...),
    sess: AsyncSession = Depends(get_db),
    _: None = Depends(requires_permission("refund", "decide")),
) -> Any:
    admin_user_id = uuid.UUID(get_admin_user_id(request))
    ip = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip() or (
        request.client.host if request.client else None
    )

    async with await _billing_client() as client:
        resp = await client.post(
            f"/billing/admin/refunds/{refund_id}/decision",
            json=body,
            headers={"X-Service-Auth": "admin-svc"},
        )
    if resp.status_code not in (200, 201):
        raise HTTPException(status_code=resp.status_code, detail=resp.text)

    result = resp.json()
    await audit_write(
        sess,
        admin_user_id=admin_user_id,
        action_type="refund.decide",
        target_kind="refund",
        target_id=str(refund_id),
        payload_after={"decision": body.get("decision"), "amount": body.get("amount")},
        reason=body.get("reason"),
        ip=ip,
        user_agent=request.headers.get("user-agent"),
    )
    await sess.commit()
    return result


# ---------------------------------------------------------------------------
# Credit grants
# ---------------------------------------------------------------------------

@router.post("/credits/grant")
async def grant_credits(
    request: Request,
    body: dict[str, Any] = Body(...),
    sess: AsyncSession = Depends(get_db),
    _: None = Depends(requires_permission("credit_grant", "create")),
) -> Any:
    """
    Grant credits to a user.

    Support agents are capped at $20/grant and $200/day rolling.
    Enforced here via X-Admin-Roles check.
    """
    admin_user_id = uuid.UUID(get_admin_user_id(request))
    roles = request.headers.get("X-Admin-Roles", "")
    settings = get_settings()
    ip = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip() or (
        request.client.host if request.client else None
    )

    delta_cents: int = body.get("delta_cents", 0)

    # Support-role cap enforcement
    if "super_admin" not in roles and "billing_admin" not in roles:
        if delta_cents > settings.support_credit_grant_single_cap_cents:
            raise HTTPException(
                status_code=403,
                detail=f"Support agents may not grant more than "
                       f"${settings.support_credit_grant_single_cap_cents // 100} per grant.",
            )

    async with await _billing_client() as client:
        resp = await client.post(
            "/billing/admin/credits/grant",
            json=body,
            headers={"X-Service-Auth": "admin-svc", "X-Admin-User-Id": str(admin_user_id)},
        )
    if resp.status_code not in (200, 201):
        raise HTTPException(status_code=resp.status_code, detail=resp.text)

    result = resp.json()
    await audit_write(
        sess,
        admin_user_id=admin_user_id,
        action_type="credit.grant",
        target_kind="credit_wallet",
        target_id=str(body.get("user_id", "")),
        payload_after={"delta_cents": delta_cents, "reason": body.get("reason")},
        reason=body.get("reason"),
        ip=ip,
        user_agent=request.headers.get("user-agent"),
    )
    await sess.commit()
    return result
