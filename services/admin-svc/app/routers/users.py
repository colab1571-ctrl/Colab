"""
admin-svc — User 360° composite endpoint + user management.

Fans out to auth-svc, profile-svc, identity-svc, billing-svc,
moderation-svc, support-svc, analytics-svc.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

import httpx
from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import write as audit_write
from app.config import get_settings
from app.db import get_db
from app.rbac import requires_permission, get_admin_user_id

router = APIRouter(prefix="/admin/v1", tags=["users"])


def _svc_headers() -> dict[str, str]:
    return {"X-Service-Auth": "admin-svc"}


@router.get("/users")
async def search_users(
    request: Request,
    q: str = Query(..., min_length=2),
    limit: int = Query(20, le=100),
    _: None = Depends(requires_permission("user_360", "read")),
) -> Any:
    """Search users by email / handle / id."""
    settings = get_settings()
    async with httpx.AsyncClient(base_url=settings.auth_svc_url, timeout=10.0) as client:
        resp = await client.get(
            "/auth/admin/users",
            params={"q": q, "limit": limit},
            headers=_svc_headers(),
        )
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


@router.get("/users/{user_id}/360")
async def get_user_360(
    user_id: uuid.UUID,
    request: Request,
    reveal: bool = Query(False),
    sess: AsyncSession = Depends(get_db),
    _: None = Depends(requires_permission("user_360", "read")),
) -> Any:
    """
    Composite user 360° view.

    Fans out to 9 services in parallel; each panel streams independently.
    PII is masked unless reveal=true (which triggers an audit row).
    """
    settings = get_settings()
    admin_user_id = uuid.UUID(get_admin_user_id(request))
    ip = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip() or (
        request.client.host if request.client else None
    )

    async def _fetch(base_url: str, path: str, params: dict | None = None) -> Any:
        try:
            async with httpx.AsyncClient(base_url=base_url, timeout=8.0) as client:
                resp = await client.get(path, params=params or {}, headers=_svc_headers())
            if resp.status_code == 200:
                return resp.json()
            return {"error": f"HTTP {resp.status_code}"}
        except Exception as exc:
            return {"error": str(exc)}

    uid = str(user_id)
    (
        auth_data,
        profile_data,
        identity_data,
        billing_sub,
        billing_wallet,
        mod_cases,
        support_tickets,
        analytics_last_active,
    ) = await asyncio.gather(
        _fetch(settings.auth_svc_url, f"/auth/admin/users/{uid}"),
        _fetch(settings.profile_svc_url, f"/profile/internal/{uid}"),
        _fetch(settings.identity_svc_url, f"/identity/internal/{uid}"),
        _fetch(settings.billing_svc_url, f"/billing/internal/subscriptions/{uid}"),
        _fetch(settings.billing_svc_url, f"/billing/internal/wallets/{uid}"),
        _fetch(settings.moderation_svc_url, f"/moderation/internal/users/{uid}/cases"),
        _fetch(settings.support_svc_url, f"/support/internal/users/{uid}/tickets"),
        _fetch(settings.analytics_svc_url, f"/analytics/internal/users/{uid}/last-active"),
    )

    if reveal:
        # Audit PII reveal
        await audit_write(
            sess,
            admin_user_id=admin_user_id,
            action_type="user.pii_reveal",
            target_kind="user",
            target_id=uid,
            payload_after={"fields_revealed": ["email", "phone"]},
            ip=ip,
            user_agent=request.headers.get("user-agent"),
        )
        await sess.commit()
    else:
        # Mask PII
        if isinstance(auth_data, dict):
            if "email" in auth_data:
                e = auth_data["email"]
                auth_data["email"] = e[:2] + "***" + e[e.find("@"):] if "@" in e else "***"
            auth_data.pop("phone", None)

    return {
        "user_id": uid,
        "auth": auth_data,
        "profile": profile_data,
        "identity": identity_data,
        "subscription": billing_sub,
        "credit_wallet": billing_wallet,
        "moderation_cases": mod_cases,
        "support_tickets": support_tickets,
        "last_active": analytics_last_active,
        "pii_revealed": reveal,
    }


@router.post("/users/{user_id}/suspend")
async def suspend_user(
    user_id: uuid.UUID,
    request: Request,
    body: dict[str, Any] = Body(...),
    sess: AsyncSession = Depends(get_db),
    _: None = Depends(requires_permission("user", "suspend")),
) -> Any:
    admin_user_id = uuid.UUID(get_admin_user_id(request))
    ip = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip() or (
        request.client.host if request.client else None
    )
    settings = get_settings()

    async with httpx.AsyncClient(base_url=settings.auth_svc_url, timeout=10.0) as client:
        resp = await client.post(
            f"/auth/admin/users/{user_id}/suspend",
            json=body,
            headers=_svc_headers(),
        )
    if resp.status_code not in (200, 201):
        raise HTTPException(status_code=resp.status_code, detail=resp.text)

    result = resp.json()
    await audit_write(
        sess,
        admin_user_id=admin_user_id,
        action_type="user.suspend",
        target_kind="user",
        target_id=str(user_id),
        payload_after={"reason": body.get("reason")},
        reason=body.get("reason"),
        ip=ip,
        user_agent=request.headers.get("user-agent"),
    )
    await sess.commit()
    return result


@router.post("/users/{user_id}/unsuspend")
async def unsuspend_user(
    user_id: uuid.UUID,
    request: Request,
    body: dict[str, Any] = Body(...),
    sess: AsyncSession = Depends(get_db),
    _: None = Depends(requires_permission("user", "unsuspend")),
) -> Any:
    admin_user_id = uuid.UUID(get_admin_user_id(request))
    ip = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip() or (
        request.client.host if request.client else None
    )
    settings = get_settings()

    async with httpx.AsyncClient(base_url=settings.auth_svc_url, timeout=10.0) as client:
        resp = await client.post(
            f"/auth/admin/users/{user_id}/unsuspend",
            json=body,
            headers=_svc_headers(),
        )
    if resp.status_code not in (200, 201):
        raise HTTPException(status_code=resp.status_code, detail=resp.text)

    result = resp.json()
    await audit_write(
        sess,
        admin_user_id=admin_user_id,
        action_type="user.unsuspend",
        target_kind="user",
        target_id=str(user_id),
        payload_after={"reason": body.get("reason")},
        reason=body.get("reason"),
        ip=ip,
        user_agent=request.headers.get("user-agent"),
    )
    await sess.commit()
    return result
