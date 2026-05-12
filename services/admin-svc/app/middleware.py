"""
admin-svc — Defense-in-depth IP allowlist middleware.

Primary enforcement is at AWS API Gateway resource policy level.
This middleware provides a belt-and-braces check at the application layer.
"""

from __future__ import annotations

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import get_settings


class IPAllowlistMiddleware(BaseHTTPMiddleware):
    """Reject requests from IPs not in the admin allowlist."""

    async def dispatch(self, request: Request, call_next):
        settings = get_settings()

        # Skip healthz
        if request.url.path in ("/healthz", "/readyz"):
            return await call_next(request)

        # Only enforce in production
        if not settings.is_production:
            return await call_next(request)

        allowlist = settings.admin_ip_allowlist
        if not allowlist:
            return await call_next(request)

        forwarded = request.headers.get("x-forwarded-for")
        client_ip = forwarded.split(",")[0].strip() if forwarded else (
            request.client.host if request.client else "unknown"
        )

        if client_ip not in allowlist:
            return Response(
                content='{"error": {"code": "FORBIDDEN", "message": "IP not in admin allowlist."}}',
                status_code=403,
                media_type="application/json",
            )

        return await call_next(request)
