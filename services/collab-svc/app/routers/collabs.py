"""
collab-svc REST API — Collaboration CRUD, status transitions, feedback, export.

Routes:
  GET    /collabs
  GET    /collabs/{id}
  PATCH  /collabs/{id}
  POST   /collabs/{id}/status
  POST   /collabs/{id}/feedback
  POST   /collabs/{id}/export
  GET    /collabs/exports/{export_id}
  GET    /me/history/requests/sent
  GET    /me/history/requests/received
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.domain.state_machine import InvalidTransitionError
from app.models import Collaboration, CollabExport, CollabStatusEvent
from app.schemas import (
    CollabDetailOut,
    CollabListResponse,
    CollabPatchRequest,
    ExportRequestResponse,
    ExportStatusResponse,
    FeedbackOut,
    FeedbackRequest,
    ParticipantStub,
    StatusEventOut,
    StatusTransitionRequest,
    StatusTransitionResponse,
)
from app.services.billing_client import check_chat_export_entitlement
from app.services.collab_service import (
    get_collab,
    list_collabs,
    patch_collab,
    transition_status,
    upsert_feedback,
)
from app.services.export_service import get_signed_urls
from app.services.invite_client import get_received_requests, get_sent_requests
from app.workers.archive_tasks import archive_finalize
from app.workers.events import emit_event
from app.workers.export_tasks import collab_export_generate

router = APIRouter(tags=["collabs"])


# ---------------------------------------------------------------------------
# Auth dependency (profile_id injected by gateway via X-Profile-Id header)
# ---------------------------------------------------------------------------


def get_current_profile_id(request: Request) -> uuid.UUID:
    pid = request.headers.get("X-Profile-Id") or request.headers.get("x-profile-id")
    if not pid:
        raise HTTPException(status_code=401, detail="Missing X-Profile-Id")
    try:
        return uuid.UUID(pid)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid X-Profile-Id")


# ---------------------------------------------------------------------------
# GET /collabs
# ---------------------------------------------------------------------------


@router.get("/collabs", response_model=CollabListResponse)
async def list_collabs_endpoint(
    status: str | None = Query(None, description="active|past|all"),
    q: str | None = Query(None, description="Full-text search query"),
    cursor: str | None = Query(None),
    limit: int = Query(20, ge=1, le=50),
    include_archived: bool = Query(False),
    profile_id: uuid.UUID = Depends(get_current_profile_id),
    db: AsyncSession = Depends(get_db),
) -> CollabListResponse:
    collabs, next_cursor = await list_collabs(
        db=db,
        profile_id=profile_id,
        status_filter=status,
        q=q,
        cursor=cursor,
        limit=limit,
        include_archived=include_archived,
    )

    items = []
    for c in collabs:
        partner_id = c.profile_id_b if c.profile_id_a == profile_id else c.profile_id_a
        items.append(
            {
                "id": c.id,
                "title": c.title,
                "status": c.status,
                "is_read_only": c.is_read_only,
                "last_activity_at": c.last_activity_at,
                "archived_at": c.archived_at,
                "partner": ParticipantStub(
                    profile_id=partner_id,
                    display_name="",  # Resolved client-side from profile-svc
                ),
                "created_at": c.created_at,
            }
        )

    return CollabListResponse(
        data=items,
        next_cursor=next_cursor,
        total_count=len(items),  # Approximate; exact count is a separate COUNT query
    )


# ---------------------------------------------------------------------------
# GET /collabs/{collab_id}
# ---------------------------------------------------------------------------


@router.get("/collabs/{collab_id}", response_model=CollabDetailOut)
async def get_collab_endpoint(
    collab_id: uuid.UUID,
    profile_id: uuid.UUID = Depends(get_current_profile_id),
    db: AsyncSession = Depends(get_db),
) -> CollabDetailOut:
    collab = await get_collab(db, collab_id, profile_id)
    if collab is None:
        raise HTTPException(status_code=404, detail="Collaboration not found")

    # Load status events
    ev_result = await db.execute(
        select(CollabStatusEvent)
        .where(CollabStatusEvent.collab_id == collab_id)
        .order_by(CollabStatusEvent.created_at)
    )
    events = ev_result.scalars().all()

    from app.models import CollabFeedback as FeedbackModel

    fb_result = await db.execute(
        select(FeedbackModel).where(FeedbackModel.collab_id == collab_id)
    )
    feedbacks = fb_result.scalars().all()

    participants = [
        ParticipantStub(profile_id=collab.profile_id_a, display_name=""),
        ParticipantStub(profile_id=collab.profile_id_b, display_name=""),
    ]

    return CollabDetailOut(
        id=collab.id,
        title=collab.title,
        description=collab.description,
        status=collab.status,
        is_read_only=collab.is_read_only,
        last_activity_at=collab.last_activity_at,
        nudge_sent_at=collab.nudge_sent_at,
        archive_at=collab.archive_at,
        archived_at=collab.archived_at,
        completed_at=collab.completed_at,
        created_at=collab.created_at,
        participants=participants,
        status_history=[
            StatusEventOut(
                id=e.id,
                prev_status=e.prev_status,
                new_status=e.new_status,
                actor_profile_id=e.actor_profile_id,
                note=e.note,
                created_at=e.created_at,
            )
            for e in events
        ],
        feedback=[
            FeedbackOut(
                id=f.id,
                collab_id=f.collab_id,
                from_profile_id=f.from_profile_id,
                to_profile_id=f.to_profile_id,
                target=f.target,
                rating=f.rating,
                tags=f.tags or [],
                comment=f.comment,
                created_at=f.created_at,
            )
            for f in feedbacks
        ],
    )


# ---------------------------------------------------------------------------
# PATCH /collabs/{collab_id}
# ---------------------------------------------------------------------------


@router.patch("/collabs/{collab_id}")
async def patch_collab_endpoint(
    collab_id: uuid.UUID,
    body: CollabPatchRequest,
    profile_id: uuid.UUID = Depends(get_current_profile_id),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    collab = await get_collab(db, collab_id, profile_id)
    if collab is None:
        raise HTTPException(status_code=404, detail="Collaboration not found")
    if collab.is_read_only:
        raise HTTPException(
            status_code=403,
            detail={"error_code": "COLLAB_READ_ONLY"},
        )
    if collab.archived_at is not None:
        raise HTTPException(
            status_code=403,
            detail={"error_code": "COLLAB_ARCHIVED"},
        )
    updated = await patch_collab(db, collab, body.title, body.description)
    return {"id": str(updated.id), "title": updated.title, "description": updated.description}


# ---------------------------------------------------------------------------
# POST /collabs/{collab_id}/status
# ---------------------------------------------------------------------------


@router.post("/collabs/{collab_id}/status", response_model=StatusTransitionResponse)
async def transition_status_endpoint(
    collab_id: uuid.UUID,
    body: StatusTransitionRequest,
    profile_id: uuid.UUID = Depends(get_current_profile_id),
    db: AsyncSession = Depends(get_db),
) -> StatusTransitionResponse:
    collab = await get_collab(db, collab_id, profile_id)
    if collab is None:
        raise HTTPException(status_code=404, detail="Collaboration not found")
    if collab.is_read_only:
        raise HTTPException(
            status_code=403,
            detail={"error_code": "COLLAB_READ_ONLY"},
        )
    if collab.archived_at is not None:
        raise HTTPException(
            status_code=403,
            detail={"error_code": "COLLAB_ARCHIVED"},
        )

    try:
        event = await transition_status(
            db=db,
            collab=collab,
            new_status=body.new_status,
            actor_profile_id=profile_id,
            note=body.note,
        )
    except InvalidTransitionError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "error_code": "INVALID_TRANSITION",
                "message": str(exc),
            },
        )

    # Emit status changed event
    await emit_event(
        "collab.status_changed",
        {
            "collab_id": str(collab_id),
            "prev_status": event.prev_status,
            "new_status": event.new_status,
            "actor_profile_id": str(profile_id),
        },
    )

    # If terminal, enqueue archive finalize
    if body.new_status in ("completed", "didnt_work_out"):
        archive_finalize.delay(str(collab_id), body.new_status)

    return StatusTransitionResponse(
        id=collab.id,
        status=collab.status,
        status_event=StatusEventOut(
            id=event.id,
            prev_status=event.prev_status,
            new_status=event.new_status,
            actor_profile_id=event.actor_profile_id,
            note=event.note,
            created_at=event.created_at,
        ),
    )


# ---------------------------------------------------------------------------
# POST /collabs/{collab_id}/feedback
# ---------------------------------------------------------------------------


@router.post("/collabs/{collab_id}/feedback", response_model=FeedbackOut)
async def submit_feedback_endpoint(
    collab_id: uuid.UUID,
    body: FeedbackRequest,
    profile_id: uuid.UUID = Depends(get_current_profile_id),
    db: AsyncSession = Depends(get_db),
) -> FeedbackOut:
    collab = await get_collab(db, collab_id, profile_id)
    if collab is None:
        raise HTTPException(status_code=404, detail="Collaboration not found")
    if collab.status not in ("completed", "didnt_work_out"):
        raise HTTPException(
            status_code=403,
            detail={"error_code": "FEEDBACK_REQUIRES_TERMINAL_STATE"},
        )

    feedback = await upsert_feedback(db, collab, profile_id, body)

    await emit_event(
        "collab.feedback_submitted",
        {
            "collab_id": str(collab_id),
            "from_profile_id": str(profile_id),
            "target": body.target,
            "rating": body.rating,
        },
    )

    return FeedbackOut(
        id=feedback.id,
        collab_id=feedback.collab_id,
        from_profile_id=feedback.from_profile_id,
        to_profile_id=feedback.to_profile_id,
        target=feedback.target,
        rating=feedback.rating,
        tags=feedback.tags or [],
        comment=feedback.comment,
        created_at=feedback.created_at,
    )


# ---------------------------------------------------------------------------
# POST /collabs/{collab_id}/export
# ---------------------------------------------------------------------------


@router.post("/collabs/{collab_id}/export", status_code=202)
async def request_export_endpoint(
    collab_id: uuid.UUID,
    profile_id: uuid.UUID = Depends(get_current_profile_id),
    db: AsyncSession = Depends(get_db),
) -> ExportRequestResponse:
    collab = await get_collab(db, collab_id, profile_id)
    if collab is None:
        raise HTTPException(status_code=404, detail="Collaboration not found")

    # Premium check
    has_entitlement = await check_chat_export_entitlement(profile_id)
    if not has_entitlement:
        raise HTTPException(
            status_code=403,
            detail={"error_code": "EXPORT_REQUIRES_PREMIUM"},
        )

    # Create CollabExport row
    export = CollabExport(
        collab_id=collab_id,
        requested_by=profile_id,
        status="pending",
    )
    db.add(export)
    await db.commit()
    await db.refresh(export)

    # Enqueue Celery task
    collab_export_generate.delay(str(export.id))

    return ExportRequestResponse(
        export_id=export.id,
        status=export.status,
        requested_at=export.requested_at,
    )


# ---------------------------------------------------------------------------
# GET /collabs/exports/{export_id}
# ---------------------------------------------------------------------------


@router.get("/collabs/exports/{export_id}", response_model=ExportStatusResponse)
async def get_export_status_endpoint(
    export_id: uuid.UUID,
    profile_id: uuid.UUID = Depends(get_current_profile_id),
    db: AsyncSession = Depends(get_db),
) -> ExportStatusResponse:
    result = await db.execute(
        select(CollabExport).where(
            CollabExport.id == export_id,
            CollabExport.requested_by == profile_id,
        )
    )
    export = result.scalars().first()
    if export is None:
        raise HTTPException(status_code=404, detail="Export not found")

    pdf_url, zip_url = None, None
    if export.status == "ready":
        pdf_url, zip_url = get_signed_urls(export)

    return ExportStatusResponse(
        export_id=export.id,
        collab_id=export.collab_id,
        status=export.status,
        pdf_url=pdf_url,
        zip_url=zip_url,
        expires_at=export.expires_at,
        requested_at=export.requested_at,
        completed_at=export.completed_at,
    )


# ---------------------------------------------------------------------------
# History proxy routes
# ---------------------------------------------------------------------------


@router.get("/me/history/requests/sent")
async def history_requests_sent(
    status: str | None = Query(None),
    cursor: str | None = Query(None),
    limit: int = Query(20, ge=1, le=50),
    profile_id: uuid.UUID = Depends(get_current_profile_id),
) -> dict[str, Any]:
    return await get_sent_requests(
        profile_id=profile_id,
        status=status,
        cursor=cursor,
        limit=limit,
    )


@router.get("/me/history/requests/received")
async def history_requests_received(
    status: str | None = Query(None),
    cursor: str | None = Query(None),
    limit: int = Query(20, ge=1, le=50),
    profile_id: uuid.UUID = Depends(get_current_profile_id),
) -> dict[str, Any]:
    return await get_received_requests(
        profile_id=profile_id,
        status=status,
        cursor=cursor,
        limit=limit,
    )
