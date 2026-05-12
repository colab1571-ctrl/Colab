"""
admin-svc — Append-only audit log writer.

Every admin mutation MUST go through audit.write() or the @audited decorator.
If the write fails, the request fails (no skip path).
"""

from __future__ import annotations

import functools
import uuid
from typing import Any, Callable

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AdminAuditLog


async def write(
    session: AsyncSession,
    *,
    admin_user_id: uuid.UUID,
    action_type: str,
    target_kind: str,
    target_id: str,
    payload_before: dict[str, Any] | None = None,
    payload_after: dict[str, Any] | None = None,
    reason: str | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
) -> AdminAuditLog:
    """
    Insert an immutable audit row.

    Raises on DB failure — callers should let the exception propagate so the
    enclosing transaction rolls back the mutation too.
    """
    row = AdminAuditLog(
        id=uuid.uuid4(),
        admin_user_id=admin_user_id,
        action_type=action_type,
        target_kind=target_kind,
        target_id=str(target_id),
        payload_before=payload_before,
        payload_after=payload_after,
        reason=reason,
        ip=ip,
        user_agent=user_agent,
    )
    session.add(row)
    await session.flush()  # write within caller's transaction
    return row


def _extract_request_meta(request: Request) -> tuple[str | None, str | None]:
    """Return (client_ip, user_agent) from the request."""
    forwarded = request.headers.get("x-forwarded-for")
    ip = forwarded.split(",")[0].strip() if forwarded else (
        request.client.host if request.client else None
    )
    ua = request.headers.get("user-agent")
    return ip, ua


def audited(
    action_type: str,
    target_kind: str,
    *,
    target_id_param: str = "id",
) -> Callable:
    """
    Decorator for FastAPI route functions that performs an audit write
    around the endpoint body.

    Usage::

        @router.post("/cases/{id}/action")
        @audited("case.action", "moderation_case")
        async def case_action(id: uuid.UUID, body: ..., request: Request, sess: AsyncSession = Depends(get_db)):
            ...

    The decorated function must accept `request: Request` and `sess: AsyncSession`.
    The `target_id` is taken from the route path parameter named by `target_id_param`.
    """

    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            request: Request = kwargs["request"]
            session: AsyncSession = kwargs["sess"]
            admin_user_id_str = request.headers.get("X-Admin-User-Id", "")
            try:
                admin_user_id = uuid.UUID(admin_user_id_str)
            except ValueError:
                admin_user_id = uuid.UUID(int=0)  # sentinel — middleware validates before this

            target_id = str(kwargs.get(target_id_param, "unknown"))
            ip, ua = _extract_request_meta(request)

            result = await fn(*args, **kwargs)

            await write(
                session,
                admin_user_id=admin_user_id,
                action_type=action_type,
                target_kind=target_kind,
                target_id=target_id,
                payload_after=result if isinstance(result, dict) else None,
                ip=ip,
                user_agent=ua,
            )
            await session.commit()
            return result

        return wrapper

    return decorator
