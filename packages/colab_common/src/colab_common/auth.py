"""
colab_common.auth — JWT verification, role enforcement, service-to-service auth.

P1 note: Accepts any well-formed JWT with HS256 or RS256. Full JWKS rotation
wired to auth-svc in P2a. Service-to-service signing uses HS256 shared secret
in P1; upgrades to RS256+IRSA in P3/P4 (per plan §13 risk 4).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from colab_common.errors import AuthError, ForbiddenError
from colab_common.settings import get_settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Auth data model
# ---------------------------------------------------------------------------


@dataclass
class AuthUser:
    """Parsed JWT claims. Passed as request.state.user."""

    user_id: str
    email: str
    roles: list[str] = field(default_factory=list)
    tier: str = "free"  # "free" | "premium" | "premium_pro"
    raw_claims: dict[str, Any] = field(default_factory=dict)

    @property
    def is_admin(self) -> bool:
        return "admin" in self.roles

    @property
    def is_moderator(self) -> bool:
        return "moderator" in self.roles or self.is_admin


# ---------------------------------------------------------------------------
# JWT decode
# ---------------------------------------------------------------------------

_bearer = HTTPBearer(auto_error=False)


def _decode_token(token: str) -> dict[str, Any]:
    """
    Decode and verify a JWT. In P1, accepts HS256 (shared secret) and RS256 (future).
    In P2a this will pull JWKS from auth-svc and verify RS256 signatures properly.
    """
    settings = get_settings()
    try:
        # Try HS256 first (P1 shared secret)
        payload: dict[str, Any] = jwt.decode(
            token,
            settings.jwt.secret,
            algorithms=["HS256", "RS256"],
            options={
                "verify_exp": True,
                # P1: skip audience + issuer checks; tightened in P2a
                "verify_aud": False,
                "verify_iss": False,
            },
        )
        return payload
    except jwt.ExpiredSignatureError as exc:
        raise AuthError("Token has expired.") from exc
    except jwt.InvalidTokenError as exc:
        raise AuthError(f"Invalid token: {exc}") from exc


def _extract_user(payload: dict[str, Any]) -> AuthUser:
    user_id = payload.get("sub", "")
    email = payload.get("email", "")
    roles = payload.get("roles", [])
    tier = payload.get("tier", "free")
    if not user_id:
        raise AuthError("Token missing 'sub' claim.")
    return AuthUser(
        user_id=user_id,
        email=email,
        roles=roles if isinstance(roles, list) else [roles],
        tier=str(tier),
        raw_claims=payload,
    )


# ---------------------------------------------------------------------------
# FastAPI dependencies
# ---------------------------------------------------------------------------


def _get_token_from_request(request: Request) -> str | None:
    """Extract Bearer token from Authorization header or colab-session cookie."""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:]
    # Cookie fallback for web browsers
    cookie = request.cookies.get("colab-session")
    return cookie or None


async def require_user(request: Request) -> AuthUser:
    """
    FastAPI dependency: require a valid JWT. Returns AuthUser.
    Raises AuthError (401) if token is missing or invalid.
    """
    # If middleware already parsed the user, return it
    user: AuthUser | None = getattr(request.state, "user", None)
    if user is not None:
        return user

    token = _get_token_from_request(request)
    if not token:
        raise AuthError("Authorization header required.")

    payload = _decode_token(token)
    auth_user = _extract_user(payload)
    request.state.user = auth_user
    return auth_user


def require_role(*roles: str) -> Any:
    """
    FastAPI dependency factory: require one of the specified roles.

    Usage:
        @router.delete("/admin/users/{id}")
        async def delete_user(user: AuthUser = Depends(require_role("admin"))):
            ...
    """

    async def _dependency(user: AuthUser = Depends(require_user)) -> AuthUser:
        if not any(r in user.roles for r in roles):
            raise ForbiddenError(
                f"Required role(s): {', '.join(roles)}. Your roles: {', '.join(user.roles) or 'none'}."
            )
        return user

    return _dependency


# ---------------------------------------------------------------------------
# Service-to-service token signing (P1: HS256 shared secret)
# ---------------------------------------------------------------------------


def mint_service_token(
    *,
    source_service: str,
    target_service: str,
    ttl_seconds: int = 60,
) -> str:
    """
    Mint a short-lived service-to-service JWT.
    In P3/P4 this upgrades to RS256 + IRSA private key.
    """
    import time

    settings = get_settings()
    now = int(time.time())
    payload = {
        "sub": f"svc:{source_service}",
        "aud": target_service,
        "iss": source_service,
        "iat": now,
        "exp": now + ttl_seconds,
        "roles": ["service"],
        "tier": "internal",
    }
    return jwt.encode(payload, settings.jwt.secret, algorithm="HS256")
