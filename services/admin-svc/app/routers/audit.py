"""
admin-svc — Audit log viewer endpoint.

super_admin sees all rows; other roles see own actions only.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import AdminAuditLog
from app.rbac import requires_permission, get_admin_user_id, get_admin_roles

router = APIRouter(prefix="/admin/v1", tags=["audit"])


@router.get("/audit")
async def get_audit_log(
    request: Request,
    actor: str | None = Query(None),
    action_type: str | None = Query(None),
    target_kind: str | None = Query(None),
    target_id: str | None = Query(None),
    from_date: str | None = Query(None, alias="from"),
    to_date: str | None = Query(None, alias="to"),
    limit: int = Query(50, le=500),
    cursor: str | None = Query(None),
    sess: AsyncSession = Depends(get_db),
    _: None = Depends(requires_permission("audit_log", "read_own")),
) -> Any:
    """
    Audit log viewer.

    super_admin: all rows. Other roles: own actions only.
    """
    roles = get_admin_roles(request)
    admin_user_id = get_admin_user_id(request)
    is_super = "super_admin" in roles

    q = select(AdminAuditLog).order_by(AdminAuditLog.created_at.desc())

    # Non-super-admins can only see their own rows
    if not is_super:
        q = q.where(AdminAuditLog.admin_user_id == admin_user_id)
    elif actor:
        q = q.where(AdminAuditLog.admin_user_id == actor)

    if action_type:
        q = q.where(AdminAuditLog.action_type == action_type)
    if target_kind:
        q = q.where(AdminAuditLog.target_kind == target_kind)
    if target_id:
        q = q.where(AdminAuditLog.target_id == target_id)

    import datetime
    if from_date:
        q = q.where(
            AdminAuditLog.created_at >= datetime.datetime.fromisoformat(from_date)
        )
    if to_date:
        q = q.where(
            AdminAuditLog.created_at <= datetime.datetime.fromisoformat(to_date)
        )

    q = q.limit(limit)

    result = await sess.execute(q)
    rows = result.scalars().all()

    return [
        {
            "id": str(r.id),
            "admin_user_id": str(r.admin_user_id),
            "action_type": r.action_type,
            "target_kind": r.target_kind,
            "target_id": r.target_id,
            "payload_before": r.payload_before,
            "payload_after": r.payload_after,
            "reason": r.reason,
            "ip": str(r.ip) if r.ip else None,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]
