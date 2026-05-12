"""
admin-svc — Casbin RBAC enforcement.

Policy is seeded from infra/casbin/policy.csv into the casbin_rule table.
Enforcer is initialized once at startup; super_admin can reload at runtime.
"""

from __future__ import annotations

import logging
from typing import Callable

import casbin
import casbin_sqlalchemy_adapter
from fastapi import HTTPException, Request, status

from app.config import get_settings

logger = logging.getLogger(__name__)

# Module-level enforcer (initialized in lifespan)
_enforcer: casbin.Enforcer | None = None

RBAC_MODEL = """
[request_definition]
r = sub, obj, act

[policy_definition]
p = sub, obj, act

[role_definition]
g = _, _

[policy_effect]
e = some(where (p.eft == allow))

[matchers]
m = g(r.sub, p.sub) && r.obj == p.obj && r.act == p.act
"""


def init_enforcer(database_url_sync: str) -> casbin.Enforcer:
    """Initialize Casbin enforcer with SQLAlchemy adapter. Call from lifespan."""
    global _enforcer
    adapter = casbin_sqlalchemy_adapter.Adapter(database_url_sync)
    model = casbin.Model()
    model.load_model_from_text(RBAC_MODEL)
    _enforcer = casbin.Enforcer(model, adapter)
    logger.info("Casbin enforcer initialized.")
    return _enforcer


def get_enforcer() -> casbin.Enforcer:
    if _enforcer is None:
        raise RuntimeError("Casbin enforcer not initialized — call init_enforcer() first.")
    return _enforcer


def reload_policy() -> None:
    """Hot-reload policy from DB. Called by super_admin after policy edits."""
    get_enforcer().load_policy()
    logger.info("Casbin policy reloaded.")


def requires_permission(obj: str, act: str) -> Callable:
    """
    FastAPI dependency that enforces Casbin permission.

    Usage::

        @router.get("/queue/moderation")
        async def get_queue(
            _: None = Depends(requires_permission("moderation_queue", "read"))
        ):
    """

    def dependency(request: Request) -> None:
        roles = request.headers.get("X-Admin-Roles", "").split(",")
        roles = [r.strip() for r in roles if r.strip()]
        enforcer = get_enforcer()
        allowed = any(
            enforcer.enforce(role, obj, act)
            for role in roles
        )
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Forbidden: {obj}:{act} requires elevated role.",
            )

    return dependency


def get_admin_user_id(request: Request) -> str:
    """Extract admin user_id from verified header (set by admin-svc auth middleware)."""
    uid = request.headers.get("X-Admin-User-Id", "")
    if not uid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Admin identity missing.")
    return uid


def get_admin_roles(request: Request) -> list[str]:
    """Extract admin roles from verified header."""
    raw = request.headers.get("X-Admin-Roles", "")
    return [r.strip() for r in raw.split(",") if r.strip()]
