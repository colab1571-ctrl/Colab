"""
analytics-svc — Event ingestion proxy.

Receives server-to-server events, writes to Postgres events mirror,
and forwards to PostHog Capture API.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import APIRouter, Body, HTTPException, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends

from app.config import get_settings
from app.db import get_db
from app.models import Event

router = APIRouter(prefix="/analytics/v1", tags=["events"])


@router.post("/events")
async def ingest_events(
    request: Request,
    body: list[dict[str, Any]] = Body(...),
    sess: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Ingest a batch of events.

    Writes to analytics.events (Postgres mirror) and forwards to PostHog.
    PostHog forward is best-effort; mirror write is always attempted.
    """
    settings = get_settings()

    # Write to Postgres mirror
    rows_written = 0
    for evt in body:
        ts_raw = evt.get("ts")
        if ts_raw:
            ts = datetime.fromisoformat(str(ts_raw))
        else:
            ts = datetime.now(tz=timezone.utc)

        user_id_raw = evt.get("user_id")
        user_id = uuid.UUID(str(user_id_raw)) if user_id_raw else None

        row = Event(
            id=uuid.uuid4(),
            event=evt["event"],
            ts=ts,
            user_id=user_id,
            session_id=evt.get("session_id"),
            props=evt.get("props"),
        )
        sess.add(row)
        rows_written += 1

    await sess.commit()

    # Forward to PostHog (best-effort; do not fail the request if PostHog is down)
    posthog_ok = False
    if settings.posthog_api_key:
        try:
            posthog_batch = [
                {
                    "api_key": settings.posthog_api_key,
                    "event": evt["event"],
                    "distinct_id": str(evt.get("user_id", "anonymous")),
                    "timestamp": evt.get("ts", datetime.now(tz=timezone.utc).isoformat()),
                    "properties": evt.get("props", {}),
                }
                for evt in body
            ]
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.post(
                    settings.posthog_ingest_url,
                    json={"batch": posthog_batch},
                )
            posthog_ok = resp.status_code == 200
        except Exception:
            pass  # logged externally; mirror write succeeded

    return {"accepted": rows_written, "posthog_forwarded": posthog_ok}


@router.get("/kpi/rollups")
async def get_kpi_rollups(
    request: Request,
    key: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    dims: str | None = None,
    sess: AsyncSession = Depends(get_db),
) -> Any:
    """Return KPI rollup rows for admin dashboard."""
    from sqlalchemy import select
    from app.models import KPIRollup

    q = select(KPIRollup).order_by(KPIRollup.key, KPIRollup.day.desc())

    if key:
        q = q.where(KPIRollup.key == key)
    if from_date:
        q = q.where(KPIRollup.day >= datetime.fromisoformat(from_date))
    if to_date:
        q = q.where(KPIRollup.day <= datetime.fromisoformat(to_date))

    result = await sess.execute(q)
    rows = result.scalars().all()

    return [
        {
            "day": r.day.date().isoformat(),
            "key": r.key,
            "dims": r.dims,
            "value": float(r.value) if r.value is not None else None,
            "count_n": r.count_n,
        }
        for r in rows
    ]


@router.get("/internal/users/{user_id}/last-active")
async def get_user_last_active(
    user_id: uuid.UUID,
    sess: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Return user's last active timestamp from event mirror."""
    result = await sess.execute(
        text("""
            SELECT MAX(ts) AS last_active
            FROM analytics.events
            WHERE user_id = :user_id AND event = 'app_active'
        """),
        {"user_id": str(user_id)},
    )
    row = result.one()
    return {"user_id": str(user_id), "last_active": row.last_active.isoformat() if row.last_active else None}
