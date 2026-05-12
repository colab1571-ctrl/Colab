"""
Declarative routing table for gateway-svc.
Each entry maps a URL prefix to an upstream service name + auth/rate-limit policy.

upstream_prefix: the path prefix the upstream service actually expects.
  e.g. gateway receives /v1/auth/signup/email
       upstream_prefix="/auth" → upstream gets /auth/signup/email
  If upstream_prefix is None, defaults to stripping the leading /v1 segment
  so /v1/... → /...
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RoutePolicy:
    prefix: str
    upstream: str
    auth_required: bool = True
    # Rate limit: (capacity, refill_per_sec). None = no explicit route-level limit.
    rate_limit: tuple[int, float] | None = None
    # Paths under this prefix that are public (no auth)
    public_paths: list[str] = field(default_factory=list)
    # The path prefix the upstream service expects. Replaces `prefix` in forwarded path.
    # None = just strip the leading /v1 segment.
    upstream_prefix: str | None = None


ROUTES: list[RoutePolicy] = [
    RoutePolicy(
        prefix="/v1/auth",
        upstream="auth",
        upstream_prefix="/auth",      # auth-svc uses /auth/signup/..., /auth/login/...
        auth_required=False,           # auth-svc handles its own auth
        public_paths=["/v1/auth/sign-in", "/v1/auth/sign-up", "/v1/auth/verify", "/v1/auth/refresh"],
        rate_limit=(10, 10 / 60),      # 10/min per IP
    ),
    RoutePolicy(
        prefix="/v1/profile",
        upstream="profile",
        upstream_prefix="/api/v1/profile",  # profile-svc uses /api/v1/profile/...
        rate_limit=(60, 1.0),
    ),
    RoutePolicy(prefix="/v1/identity",   upstream="identity",     rate_limit=(30, 0.5)),
    RoutePolicy(
        prefix="/v1/feed",
        upstream="discovery",
        upstream_prefix="/feed",       # discovery-svc uses /feed
        rate_limit=(120, 2.0),
    ),
    RoutePolicy(prefix="/v1/match",      upstream="matching",     rate_limit=(60, 1.0)),
    RoutePolicy(prefix="/v1/invite",     upstream="invite",       rate_limit=(60, 1.0)),
    RoutePolicy(prefix="/v1/collab",     upstream="collab",       rate_limit=(60, 1.0)),
    RoutePolicy(prefix="/v1/chat",       upstream="chat",         rate_limit=(240, 4.0)),
    RoutePolicy(prefix="/v1/media",      upstream="media",        rate_limit=(30, 0.5)),
    RoutePolicy(prefix="/v1/ai",         upstream="ai",           rate_limit=(30, 0.5)),
    RoutePolicy(prefix="/v1/moderation", upstream="moderation",   rate_limit=None),
    RoutePolicy(prefix="/v1/notification", upstream="notification", rate_limit=None),
    RoutePolicy(
        prefix="/v1/billing",
        upstream="billing",
        public_paths=["/v1/billing/webhooks/stripe", "/v1/billing/webhooks/revenuecat"],
        rate_limit=None,
    ),
    RoutePolicy(prefix="/v1/support",    upstream="support",      rate_limit=None),
    RoutePolicy(prefix="/v1/admin",      upstream="admin",        rate_limit=None),
    RoutePolicy(prefix="/v1/geo",        upstream="geo",          rate_limit=(60, 1.0)),
    RoutePolicy(prefix="/v1/meeting",    upstream="meeting",      rate_limit=(30, 0.5)),
    RoutePolicy(prefix="/v1/analytics",  upstream="analytics",    rate_limit=None),
    # P1: hello-svc end-to-end test
    RoutePolicy(prefix="/v1/hello",      upstream="hello",        auth_required=False, rate_limit=None),
]


def find_route(path: str) -> RoutePolicy | None:
    """Find the matching RoutePolicy for a request path. First match wins."""
    for route in ROUTES:
        if path.startswith(route.prefix):
            return route
    return None
