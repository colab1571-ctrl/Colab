"""
admin-svc — Feature flag CRUD.

Writes to FeatureFlag table and mirrors to PostHog Personal API.
prod writes require super_admin + MFA step-up.
"""

from __future__ import annotations

import uuid
from typing import Any

import httpx
from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import write as audit_write
from app.config import get_settings
from app.db import get_db
from app.models import FeatureFlag
from app.rbac import requires_permission, get_admin_user_id, get_admin_roles

router = APIRouter(prefix="/admin/v1", tags=["flags"])


async def _mirror_to_posthog(key: str, env: str, value: Any, canary_pct: float) -> None:
    """Synchronously mirror flag to PostHog Personal API. Raises on failure."""
    settings = get_settings()
    if not settings.posthog_api_key or not settings.posthog_project_id:
        return  # not configured (dev/local)

    payload = {
        "name": f"{env}.{key}",
        "key": f"{env}_{key}",
        "active": True,
        "filters": {
            "groups": [{"properties": [], "rollout_percentage": int(canary_pct)}]
        },
        "variants": [],
    }

    async with httpx.AsyncClient(
        base_url="https://app.posthog.com",
        headers={"Authorization": f"Bearer {settings.posthog_api_key}"},
        timeout=5.0,
    ) as client:
        resp = await client.post(
            f"/api/projects/{settings.posthog_project_id}/feature_flags/",
            json=payload,
        )
    if resp.status_code not in (200, 201):
        raise HTTPException(
            status_code=502,
            detail=f"PostHog mirror failed: {resp.status_code} {resp.text[:200]}",
        )


@router.get("/flags")
async def get_flags(
    request: Request,
    env: str | None = Query(None),
    sess: AsyncSession = Depends(get_db),
    _: None = Depends(requires_permission("feature_flag", "read")),
) -> Any:
    q = select(FeatureFlag)
    if env:
        q = q.where(FeatureFlag.env == env)
    result = await sess.execute(q.order_by(FeatureFlag.env, FeatureFlag.key))
    flags = result.scalars().all()
    return [
        {
            "key": f.key,
            "env": f.env,
            "value": f.value,
            "canary_pct": float(f.canary_pct),
            "description": f.description,
            "updated_by": str(f.updated_by),
            "updated_at": f.updated_at.isoformat(),
        }
        for f in flags
    ]


@router.put("/flags")
async def upsert_flag(
    request: Request,
    body: dict[str, Any] = Body(...),
    sess: AsyncSession = Depends(get_db),
) -> Any:
    """
    Create or update a feature flag.

    - prod env requires super_admin role.
    - PostHog mirror is synchronous; failure returns 502 and rolls back.
    """
    env: str = body.get("env", "dev")
    key: str = body["key"]
    roles = get_admin_roles(request)

    # prod flag writes require super_admin
    if env == "prod":
        if "super_admin" not in roles:
            raise HTTPException(
                status_code=403,
                detail="prod feature flags require super_admin role.",
            )
        # MFA step-up check (header set by admin-web after re-auth)
        if request.headers.get("X-Mfa-Stepup") != "true":
            raise HTTPException(
                status_code=401,
                detail="stepup_required",
                headers={"X-Stepup-Required": "true"},
            )
    else:
        # non-prod requires write_nonprod permission at minimum
        from app.rbac import get_enforcer
        enforcer = get_enforcer()
        allowed = any(enforcer.enforce(r, "feature_flag", "write_nonprod") for r in roles)
        if not allowed:
            raise HTTPException(status_code=403, detail="Insufficient role for flag write.")

    admin_user_id = uuid.UUID(get_admin_user_id(request))
    ip = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip() or (
        request.client.host if request.client else None
    )

    # Fetch existing for before-snapshot
    existing = await sess.execute(
        select(FeatureFlag).where(FeatureFlag.key == key, FeatureFlag.env == env)
    )
    flag = existing.scalar_one_or_none()
    before = {"value": flag.value, "canary_pct": float(flag.canary_pct)} if flag else None

    value = body["value"]
    canary_pct = float(body.get("canary_pct", 0))
    description = body.get("description", flag.description if flag else "")

    if flag is None:
        flag = FeatureFlag(
            key=key,
            env=env,
            value=value,
            canary_pct=canary_pct,
            description=description,
            updated_by=admin_user_id,
        )
        sess.add(flag)
    else:
        flag.value = value
        flag.canary_pct = canary_pct
        flag.description = description
        flag.updated_by = admin_user_id

    # Mirror to PostHog synchronously — if it fails, we raise and the DB write rolls back
    await _mirror_to_posthog(key, env, value, canary_pct)

    await audit_write(
        sess,
        admin_user_id=admin_user_id,
        action_type="flag.toggle",
        target_kind="feature_flag",
        target_id=f"{env}/{key}",
        payload_before=before,
        payload_after={"value": value, "canary_pct": canary_pct, "env": env},
        ip=ip,
        user_agent=request.headers.get("user-agent"),
    )
    await sess.commit()
    return {"key": key, "env": env, "value": value, "canary_pct": canary_pct}
