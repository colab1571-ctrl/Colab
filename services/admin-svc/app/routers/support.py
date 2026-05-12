"""
admin-svc — Support console endpoints.

Proxies to support-svc; enriches with AdminAuditLog writes.
"""

from __future__ import annotations

import uuid
from typing import Any

import httpx
from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import write as audit_write
from app.config import get_settings
from app.db import get_db
from app.rbac import requires_permission, get_admin_user_id

router = APIRouter(prefix="/admin/v1", tags=["support"])


async def _support_client() -> httpx.AsyncClient:
    settings = get_settings()
    return httpx.AsyncClient(base_url=settings.support_svc_url, timeout=10.0)


@router.get("/queue/support")
async def get_support_queue(
    request: Request,
    category: str | None = Query(None),
    status: str | None = Query(None),
    breached: bool | None = Query(None),
    assignee: str | None = Query(None),
    priority: str | None = Query(None),
    limit: int = Query(50, le=200),
    cursor: str | None = Query(None),
    _: None = Depends(requires_permission("support_queue", "read")),
) -> Any:
    """Paginated support ticket queue with SLA timers."""
    params: dict[str, Any] = {"limit": limit}
    for k, v in [("category", category), ("status", status), ("assignee", assignee),
                 ("priority", priority), ("cursor", cursor)]:
        if v is not None:
            params[k] = v
    if breached is not None:
        params["breached"] = breached

    async with await _support_client() as client:
        resp = await client.get(
            "/support/tickets",
            params=params,
            headers={"X-Service-Auth": "admin-svc"},
        )
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


@router.get("/tickets/{ticket_id}")
async def get_ticket_detail(
    ticket_id: uuid.UUID,
    request: Request,
    _: None = Depends(requires_permission("support_ticket", "read")),
) -> Any:
    async with await _support_client() as client:
        resp = await client.get(
            f"/support/tickets/{ticket_id}",
            headers={"X-Service-Auth": "admin-svc"},
        )
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


@router.post("/tickets/{ticket_id}/reply")
async def reply_to_ticket(
    ticket_id: uuid.UUID,
    request: Request,
    body: dict[str, Any] = Body(...),
    sess: AsyncSession = Depends(get_db),
    _: None = Depends(requires_permission("support_ticket", "reply")),
) -> Any:
    """Post agent reply; stops ack-SLA timer on first response."""
    admin_user_id = uuid.UUID(get_admin_user_id(request))
    ip = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip() or (
        request.client.host if request.client else None
    )

    async with await _support_client() as client:
        resp = await client.post(
            f"/support/tickets/{ticket_id}/reply",
            json=body,
            headers={"X-Service-Auth": "admin-svc", "X-Admin-User-Id": str(admin_user_id)},
        )
    if resp.status_code not in (200, 201):
        raise HTTPException(status_code=resp.status_code, detail=resp.text)

    result = resp.json()
    await audit_write(
        sess,
        admin_user_id=admin_user_id,
        action_type="ticket.reply",
        target_kind="support_ticket",
        target_id=str(ticket_id),
        payload_after={"reply_preview": str(body.get("body", ""))[:200]},
        ip=ip,
        user_agent=request.headers.get("user-agent"),
    )
    await sess.commit()
    return result


@router.post("/tickets/{ticket_id}/escalate")
async def escalate_ticket(
    ticket_id: uuid.UUID,
    request: Request,
    body: dict[str, Any] = Body(...),
    sess: AsyncSession = Depends(get_db),
    _: None = Depends(requires_permission("support_ticket", "escalate")),
) -> Any:
    admin_user_id = uuid.UUID(get_admin_user_id(request))
    ip = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip() or (
        request.client.host if request.client else None
    )

    async with await _support_client() as client:
        resp = await client.post(
            f"/support/tickets/{ticket_id}/escalate",
            json=body,
            headers={"X-Service-Auth": "admin-svc"},
        )
    if resp.status_code not in (200, 201):
        raise HTTPException(status_code=resp.status_code, detail=resp.text)

    result = resp.json()
    await audit_write(
        sess,
        admin_user_id=admin_user_id,
        action_type="ticket.escalate",
        target_kind="support_ticket",
        target_id=str(ticket_id),
        payload_after={"to_role": body.get("to_role"), "reason": body.get("reason")},
        reason=body.get("reason"),
        ip=ip,
        user_agent=request.headers.get("user-agent"),
    )
    await sess.commit()
    return result


@router.post("/tickets/{ticket_id}/resolve")
async def resolve_ticket(
    ticket_id: uuid.UUID,
    request: Request,
    body: dict[str, Any] = Body(...),
    sess: AsyncSession = Depends(get_db),
    _: None = Depends(requires_permission("support_ticket", "resolve")),
) -> Any:
    admin_user_id = uuid.UUID(get_admin_user_id(request))
    ip = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip() or (
        request.client.host if request.client else None
    )

    async with await _support_client() as client:
        resp = await client.post(
            f"/support/tickets/{ticket_id}/resolve",
            json=body,
            headers={"X-Service-Auth": "admin-svc"},
        )
    if resp.status_code not in (200, 201):
        raise HTTPException(status_code=resp.status_code, detail=resp.text)

    result = resp.json()
    await audit_write(
        sess,
        admin_user_id=admin_user_id,
        action_type="ticket.resolve",
        target_kind="support_ticket",
        target_id=str(ticket_id),
        payload_after={"resolution_note": body.get("resolution_note", "")[:500]},
        ip=ip,
        user_agent=request.headers.get("user-agent"),
    )
    await sess.commit()
    return result
