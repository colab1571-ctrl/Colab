"""
admin-svc — Moderator console endpoints.

Proxies to moderation-svc; enriches with AdminAuditLog writes.
"""

from __future__ import annotations

import uuid
from typing import Any

import httpx
from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import write as audit_write
from app.config import get_settings
from app.db import get_db
from app.rbac import requires_permission, get_admin_user_id

router = APIRouter(prefix="/admin/v1", tags=["moderation"])


async def _mod_client() -> httpx.AsyncClient:
    settings = get_settings()
    return httpx.AsyncClient(base_url=settings.moderation_svc_url, timeout=10.0)


@router.get("/queue/moderation")
async def get_moderation_queue(
    request: Request,
    score: str | None = Query(None),
    kind: str | None = Query(None),
    sla: str | None = Query(None),
    assignee: str | None = Query(None),
    limit: int = Query(50, le=200),
    cursor: str | None = Query(None),
    _: None = Depends(requires_permission("moderation_queue", "read")),
) -> Any:
    """Paginated moderation queue with SLA highlights."""
    params: dict[str, Any] = {"limit": limit}
    if score:
        params["score"] = score
    if kind:
        params["kind"] = kind
    if sla:
        params["sla"] = sla
    if assignee:
        params["assignee"] = assignee
    if cursor:
        params["cursor"] = cursor

    async with await _mod_client() as client:
        resp = await client.get(
            "/moderation/queue",
            params=params,
            headers={"X-Service-Auth": "admin-svc"},
        )
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


@router.get("/cases/{case_id}")
async def get_case_detail(
    case_id: uuid.UUID,
    request: Request,
    _: None = Depends(requires_permission("moderation_case", "read")),
) -> Any:
    """Case detail including scores breakdown and audit history."""
    async with await _mod_client() as client:
        resp = await client.get(
            f"/moderation/cases/{case_id}",
            headers={"X-Service-Auth": "admin-svc"},
        )
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


@router.post("/cases/{case_id}/action")
async def take_case_action(
    case_id: uuid.UUID,
    request: Request,
    body: dict[str, Any] = Body(...),
    sess: AsyncSession = Depends(get_db),
    _: None = Depends(requires_permission("moderation_case", "action")),
) -> Any:
    """Apply moderation action (warn/hide/mute/ban) and audit-log it."""
    admin_user_id = uuid.UUID(get_admin_user_id(request))
    ip = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip() or (
        request.client.host if request.client else None
    )

    async with await _mod_client() as client:
        resp = await client.post(
            f"/moderation/cases/{case_id}/action",
            json=body,
            headers={"X-Service-Auth": "admin-svc", "X-Admin-User-Id": str(admin_user_id)},
        )
    if resp.status_code not in (200, 201):
        raise HTTPException(status_code=resp.status_code, detail=resp.text)

    result = resp.json()
    await audit_write(
        sess,
        admin_user_id=admin_user_id,
        action_type="case.action",
        target_kind="moderation_case",
        target_id=str(case_id),
        payload_before={"status": "open"},
        payload_after={"action_type": body.get("action_type"), "result": result},
        reason=body.get("reason"),
        ip=ip,
        user_agent=request.headers.get("user-agent"),
    )
    await sess.commit()
    return result


@router.get("/dmca/{dmca_id}")
async def get_dmca_case(
    dmca_id: uuid.UUID,
    request: Request,
    _: None = Depends(requires_permission("dmca", "read")),
) -> Any:
    async with await _mod_client() as client:
        resp = await client.get(
            f"/moderation/dmca/{dmca_id}",
            headers={"X-Service-Auth": "admin-svc"},
        )
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


@router.post("/dmca/{dmca_id}/decision")
async def dmca_decision(
    dmca_id: uuid.UUID,
    request: Request,
    body: dict[str, Any] = Body(...),
    sess: AsyncSession = Depends(get_db),
    _: None = Depends(requires_permission("dmca", "decide")),
) -> Any:
    """DMCA decision: hide_24h | restore | escalate_to_super."""
    admin_user_id = uuid.UUID(get_admin_user_id(request))
    ip = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip() or (
        request.client.host if request.client else None
    )

    async with await _mod_client() as client:
        resp = await client.post(
            f"/moderation/dmca/{dmca_id}/decision",
            json=body,
            headers={"X-Service-Auth": "admin-svc"},
        )
    if resp.status_code not in (200, 201):
        raise HTTPException(status_code=resp.status_code, detail=resp.text)

    result = resp.json()
    await audit_write(
        sess,
        admin_user_id=admin_user_id,
        action_type="dmca.decide",
        target_kind="dmca_case",
        target_id=str(dmca_id),
        payload_after={"decision": body.get("decision"), "result": result},
        reason=body.get("reason"),
        ip=ip,
        user_agent=request.headers.get("user-agent"),
    )
    await sess.commit()
    return result
