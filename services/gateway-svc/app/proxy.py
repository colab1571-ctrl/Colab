"""
HTTP reverse proxy logic for gateway-svc.
Routes requests to upstream services via httpx async client.
"""

from __future__ import annotations

import logging

import httpx
from fastapi import Request
from fastapi.responses import Response as FastAPIResponse

from app.config import UPSTREAM_URLS
from app.routes import find_route

logger = logging.getLogger(__name__)

# Shared async httpx client (connection pooling)
_http_client: httpx.AsyncClient | None = None

# Headers that should not be forwarded upstream
_HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "host",
}


def get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=5.0),
            limits=httpx.Limits(max_connections=200, max_keepalive_connections=50),
        )
    return _http_client


async def close_http_client() -> None:
    global _http_client
    if _http_client:
        await _http_client.aclose()
        _http_client = None


async def proxy_request(request: Request) -> FastAPIResponse:
    """
    Forward the incoming request to the appropriate upstream service.
    Strips hop-by-hop headers; forwards X-Request-Id and Authorization.
    """
    path = request.url.path
    route = find_route(path)

    if not route:
        return FastAPIResponse(
            content='{"error":{"code":"NOT_FOUND","message":"No route for this path."}}',
            status_code=404,
            media_type="application/json",
        )

    upstream_base = UPSTREAM_URLS.get(route.upstream)
    if not upstream_base:
        return FastAPIResponse(
            content='{"error":{"code":"SERVICE_UNAVAILABLE","message":"Upstream not configured."}}',
            status_code=503,
            media_type="application/json",
        )

    # Build upstream URL
    query = str(request.url.query)
    upstream_url = f"{upstream_base}{path}" + (f"?{query}" if query else "")

    # Forward headers (minus hop-by-hop + host)
    forward_headers: dict[str, str] = {}
    for name, value in request.headers.items():
        if name.lower() not in _HOP_BY_HOP_HEADERS:
            forward_headers[name] = value

    # Add gateway-stamped headers
    request_id = getattr(request.state, "request_id", "")
    if request_id:
        forward_headers["X-Request-Id"] = request_id

    # Service-to-service token (P1: pass-through user token; P3 mints fresh svc token)
    user = getattr(request.state, "user", None)
    if user:
        forward_headers["X-Gateway-User-Id"] = user.user_id
        forward_headers["X-Gateway-User-Tier"] = user.tier
        forward_headers["X-Gateway-User-Roles"] = ",".join(user.roles)

    body = await request.body()

    client = get_http_client()
    try:
        upstream_resp = await client.request(
            method=request.method,
            url=upstream_url,
            headers=forward_headers,
            content=body,
        )
    except httpx.ConnectError:
        logger.error("Upstream connection error", extra={"upstream": route.upstream, "url": upstream_url})
        return FastAPIResponse(
            content=f'{{"error":{{"code":"SERVICE_UNAVAILABLE","message":"{route.upstream} is unavailable."}}}}',
            status_code=503,
            media_type="application/json",
        )

    # Forward response (strip hop-by-hop)
    response_headers: dict[str, str] = {}
    for name, value in upstream_resp.headers.items():
        if name.lower() not in _HOP_BY_HOP_HEADERS:
            response_headers[name] = value

    return FastAPIResponse(
        content=upstream_resp.content,
        status_code=upstream_resp.status_code,
        headers=response_headers,
        media_type=upstream_resp.headers.get("content-type", "application/json"),
    )
