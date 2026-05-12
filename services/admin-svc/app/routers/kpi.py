"""
admin-svc — KPI rollup read endpoint.

Proxies to analytics-svc for rollup data.
"""

from __future__ import annotations

from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.config import get_settings
from app.rbac import requires_permission

router = APIRouter(prefix="/admin/v1", tags=["kpi"])


@router.get("/kpi/rollups")
async def get_kpi_rollups(
    request: Request,
    key: str | None = Query(None),
    from_date: str | None = Query(None, alias="from"),
    to_date: str | None = Query(None, alias="to"),
    dims: str | None = Query(None),
    _: None = Depends(requires_permission("kpi_rollup", "read")),
) -> Any:
    """Return KPI rollup rows for the given key/date range."""
    settings = get_settings()
    params: dict[str, Any] = {}
    if key:
        params["key"] = key
    if from_date:
        params["from"] = from_date
    if to_date:
        params["to"] = to_date
    if dims:
        params["dims"] = dims

    async with httpx.AsyncClient(
        base_url=settings.analytics_svc_url, timeout=10.0
    ) as client:
        resp = await client.get(
            "/analytics/v1/kpi/rollups",
            params=params,
            headers={"X-Service-Auth": "admin-svc"},
        )
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()
