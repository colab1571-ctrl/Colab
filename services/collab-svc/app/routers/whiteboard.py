"""
collab-svc REST + WebSocket API — Whiteboard (tldraw + Y.js).

Routes:
  WS   /whiteboard/{collab_id}/ws
  GET  /whiteboard/{collab_id}/snapshot
  POST /whiteboard/{collab_id}/export
  GET  /whiteboard/exports/{export_id}
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request, WebSocket, WebSocketDisconnect

from app.db import get_db
from app.routers.collabs import get_current_profile_id
from app.schemas_tools import (
    WhiteboardExportReadyOut,
    WhiteboardExportRequestOut,
    WhiteboardSnapshotOut,
)
from app.services import collab_service
from app.services.chat_client import check_whiteboard_export_entitlement
from app.services.whiteboard_service import (
    create_export_record,
    get_export,
    get_export_signed_url,
    get_latest_snapshot,
)
from app.services.whiteboard_ws import (
    WS_CLOSE_NOT_PARTICIPANT,
    WS_CLOSE_READONLY,
    handle_whiteboard_ws,
)
from app.workers.events import emit_event
from app.workers.whiteboard_tasks import whiteboard_export_generate
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(tags=["whiteboard"])

SNAPSHOT_URL_TTL_MINUTES = 5

# Re-export close code reference
WS_CLOSE_READONLY = 4009  # noqa: F811


# ---------------------------------------------------------------------------
# Auth helper (WebSocket tokens come in via query param)
# ---------------------------------------------------------------------------


def _parse_token_from_query(token: str | None) -> uuid.UUID | None:
    """
    In production the gateway decodes the Bearer JWT and sets X-Profile-Id.
    For the WS path, the client passes ?token=<jwt> which the gateway forwards
    as X-Profile-Id after validation. Here we accept it as a query param stub.
    """
    if token is None:
        return None
    try:
        return uuid.UUID(token)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# WS /whiteboard/{collab_id}/ws
# ---------------------------------------------------------------------------


@router.websocket("/whiteboard/{collab_id}/ws")
async def whiteboard_ws_endpoint(
    websocket: WebSocket,
    collab_id: uuid.UUID,
    token: str | None = Query(None),
) -> None:
    """
    Y.js op stream. Raw binary frames (y-sync v1 protocol).
    Auth: ?token=<profile_id> (stub; real auth done by gateway JWT decode).
    """
    # Resolve actor profile from query token or header
    actor_profile_id = _parse_token_from_query(token)
    pid_header = websocket.headers.get("x-profile-id")
    if actor_profile_id is None and pid_header:
        try:
            actor_profile_id = uuid.UUID(pid_header)
        except ValueError:
            pass

    if actor_profile_id is None:
        await websocket.close(code=4003)
        return

    # Participant check — use a fresh DB session
    from app.db import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        collab = await collab_service.get_collab(db, collab_id, actor_profile_id)

    if collab is None:
        await websocket.close(code=WS_CLOSE_NOT_PARTICIPANT)
        return

    if collab.is_read_only:
        await websocket.close(code=WS_CLOSE_READONLY)
        return

    await handle_whiteboard_ws(websocket, collab_id, actor_profile_id)


# ---------------------------------------------------------------------------
# GET /whiteboard/{collab_id}/snapshot
# ---------------------------------------------------------------------------


@router.get("/whiteboard/{collab_id}/snapshot", response_model=WhiteboardSnapshotOut)
async def get_snapshot_endpoint(
    collab_id: uuid.UUID,
    profile_id: uuid.UUID = Depends(get_current_profile_id),
    db: AsyncSession = Depends(get_db),
) -> WhiteboardSnapshotOut:
    collab = await collab_service.get_collab(db, collab_id, profile_id)
    if collab is None:
        raise HTTPException(status_code=403, detail="Not a participant in this collaboration")

    snapshot = await get_latest_snapshot(db, collab_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="No snapshot yet — board is empty")

    from app.config import get_collab_settings

    settings = get_collab_settings()
    expires_at = datetime.now(UTC) + timedelta(minutes=SNAPSHOT_URL_TTL_MINUTES)
    url = f"https://{settings.cloudfront_domain}/{snapshot.s3_key}"

    return WhiteboardSnapshotOut(
        collab_id=snapshot.collab_id,
        version=snapshot.version,
        s3_key=snapshot.s3_key,
        url=url,
        url_expires_at=expires_at,
        created_at=snapshot.created_at,
    )


# ---------------------------------------------------------------------------
# POST /whiteboard/{collab_id}/export
# ---------------------------------------------------------------------------


@router.post(
    "/whiteboard/{collab_id}/export",
    response_model=WhiteboardExportRequestOut,
    status_code=202,
)
async def request_whiteboard_export_endpoint(
    collab_id: uuid.UUID,
    fmt: str = Query("png", alias="format", pattern="^(png|pdf)$"),
    resolution: str = Query("basic", pattern="^(basic|hi)$"),
    profile_id: uuid.UUID = Depends(get_current_profile_id),
    db: AsyncSession = Depends(get_db),
) -> WhiteboardExportRequestOut:
    collab = await collab_service.get_collab(db, collab_id, profile_id)
    if collab is None:
        raise HTTPException(status_code=403, detail="Not a participant in this collaboration")

    # Premium gate for hi-res
    if resolution == "hi":
        has_entitlement = await check_whiteboard_export_entitlement(profile_id)
        if not has_entitlement:
            raise HTTPException(
                status_code=403,
                detail={"error_code": "ENTITLEMENT_REQUIRED", "message": "Hi-res export requires Premium"},
            )

    export = await create_export_record(
        db=db,
        collab_id=collab_id,
        requested_by=profile_id,
        fmt=fmt,
        resolution=resolution,
    )

    # Enqueue headless render worker
    whiteboard_export_generate.delay(str(export.id))

    return WhiteboardExportRequestOut(
        export_id=export.id,
        status=export.status,  # type: ignore[arg-type]
        poll_url=f"/whiteboard/exports/{export.id}",
    )


# ---------------------------------------------------------------------------
# GET /whiteboard/exports/{export_id}
# ---------------------------------------------------------------------------


@router.get("/whiteboard/exports/{export_id}", response_model=WhiteboardExportReadyOut)
async def get_whiteboard_export_endpoint(
    export_id: uuid.UUID,
    profile_id: uuid.UUID = Depends(get_current_profile_id),
    db: AsyncSession = Depends(get_db),
) -> WhiteboardExportReadyOut:
    export = await get_export(db, export_id, requested_by=profile_id)
    if export is None:
        raise HTTPException(status_code=404, detail="Export not found")

    url = get_export_signed_url(export) if export.status == "ready" else None
    mime = "image/png" if export.format == "png" else "application/pdf"

    return WhiteboardExportReadyOut(
        export_id=export.id,
        status=export.status,  # type: ignore[arg-type]
        url=url,
        url_expires_at=export.expires_at,
        mime_type=mime if url else None,
        resolution=export.resolution,
        error=export.error_detail,
    )
