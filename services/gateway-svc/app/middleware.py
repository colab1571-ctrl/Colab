"""
gateway-svc middleware stack.

Order (top of stack = first applied):
1. RequestIDMiddleware      (colab_common.telemetry)
2. CORSMiddleware           (starlette built-in)
3. StructlogMiddleware      (binds request_id + user_id)
4. AuthMiddleware           (decodes JWT; skips public paths + health)
5. RateLimitMiddleware      (global bucket; per-route in router)
6. IdempotencyMiddleware    (mutating verbs only)
7. Router / proxy

These are added in reverse order to the FastAPI app (outermost first in add_middleware).
"""

from __future__ import annotations

import logging
from typing import Any

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from colab_common.auth import _decode_token, _extract_user
from colab_common.errors import AuthError
from colab_common.settings import get_settings
from colab_common.telemetry import request_id_var

from app.routes import find_route

logger = structlog.get_logger(__name__)

# Paths that always bypass auth
AUTH_BYPASS_PATHS = {
    "/healthz",
    "/ready",
    "/readyz",
    "/openapi.json",
    "/version",
    "/v1/flags",
    "/docs",
    "/redoc",
}


class AuthMiddleware(BaseHTTPMiddleware):
    """
    Decodes JWT from Authorization header or colab-session cookie.
    Skips: health endpoints, /openapi.json, and paths in AUTH_BYPASS_PATHS.
    For public-listed paths in route policy: skips auth but still allows it if present.

    P1: Accepts any well-formed JWT. Tightens in P2a with JWKS rotation.
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        path = request.url.path

        # Always bypass for infrastructure paths
        if path in AUTH_BYPASS_PATHS:
            return await call_next(request)

        # Find route policy
        route = find_route(path)

        # Determine if this is a public path
        is_public_path = route is not None and (
            not route.auth_required or path in (route.public_paths or [])
        )

        # Try to extract token (best-effort for public paths)
        auth_header = request.headers.get("Authorization", "")
        cookie_token = request.cookies.get("colab-session")
        raw_token = (
            auth_header[7:] if auth_header.startswith("Bearer ") else cookie_token
        )

        if raw_token:
            try:
                payload = _decode_token(raw_token)
                user = _extract_user(payload)
                request.state.user = user
            except AuthError:
                if not is_public_path:
                    raise
                # Public path — ignore invalid token
        elif not is_public_path and route is not None:
            raise AuthError("Authorization required.")

        return await call_next(request)


class StructlogMiddleware(BaseHTTPMiddleware):
    """Binds request_id and user_id to structlog context for this request."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        request_id = request_id_var.get("")
        user = getattr(request.state, "user", None)
        user_id = user.user_id if user else "anonymous"

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            user_id=user_id,
            method=request.method,
            path=request.url.path,
        )

        response: Response = await call_next(request)
        logger.info(
            "request",
            status_code=response.status_code,
        )
        return response
