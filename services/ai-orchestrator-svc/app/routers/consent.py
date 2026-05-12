"""
Mockup consent flow and mockup asset listing.

POST /collabs/{id}/mockup/consent  — create (party A) or approve (party B)
GET  /collabs/{id}/mockups         — list mockup assets for a collab
POST /ai/mockups/{asset_id}/screenshot-event — audit screenshot detection
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_ai_settings
from app.db import get_db
from app.models import AIInteraction, MockupAsset, MockupConsent, MockupScreenshotAudit
from app.schemas.consent import (
    ConsentApprovedResponse,
    ConsentCreatedResponse,
    ConsentRequest,
    MockupAssetOut,
    MockupListResponse,
    ScreenshotEventRequest,
)
from app.services.billing_client import (
    InsufficientCreditsError as BillingInsufficientCreditsError,
    check_entitlement,
    release_reservation,
    reserve_credits,
)
from app.services.s3_client import generate_signed_url

router = APIRouter(tags=["mockup-consent"])
logger = logging.getLogger(__name__)


def _get_http(request: Request) -> httpx.AsyncClient:
    return request.app.state.http


def _get_user_id(request: Request) -> uuid.UUID:
    user_id_str = request.headers.get("X-User-Id", "")
    try:
        return uuid.UUID(user_id_str)
    except ValueError:
        raise HTTPException(status_code=401, detail="Missing or invalid X-User-Id")


async def _get_collab_participants(
    collab_id: uuid.UUID, http: httpx.AsyncClient
) -> list[uuid.UUID]:
    """Fetch participant user IDs for a collaboration."""
    settings = get_ai_settings()
    try:
        resp = await http.get(
            f"{settings.collab_svc_url}/internal/collabs/{collab_id}/participants",
            timeout=5.0,
        )
        if resp.status_code == 404:
            return []
        resp.raise_for_status()
        data = resp.json()
        return [uuid.UUID(p) for p in data.get("participant_ids", [])]
    except Exception as exc:
        logger.warning("Failed to fetch collab participants: %s", exc)
        return []


# ---------------------------------------------------------------------------
# POST /collabs/{id}/mockup/consent
# ---------------------------------------------------------------------------

@router.post("/collabs/{collab_id}/mockup/consent", status_code=201)
async def mockup_consent(
    collab_id: uuid.UUID,
    body: ConsentRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Any:
    settings = get_ai_settings()
    http = _get_http(request)
    user_id = _get_user_id(request)

    # Verify user is participant
    participants = await _get_collab_participants(collab_id, http)
    if participants and user_id not in participants:
        raise HTTPException(status_code=404, detail="Collab not found or user not a participant")

    # Check for existing active/pending consent
    existing_result = await db.execute(
        select(MockupConsent).where(
            MockupConsent.collab_id == collab_id,
            MockupConsent.status.in_(["pending_b", "approved"]),
        )
    )
    existing = existing_result.scalars().first()

    # --- Party B accepts ---
    if existing and existing.status == "pending_b" and existing.requested_by != user_id:
        existing.party_b_consented_at = datetime.now(timezone.utc)
        existing.status = "approved"
        await db.flush()

        # Entitlement + credit check at approval time
        try:
            entitlement = await check_entitlement(user_id, http)
            tier = entitlement.get("tier", "premium")
        except Exception:
            raise HTTPException(status_code=402, detail="Premium required to generate mockups")

        kind = existing.generation_kind
        cost = (
            settings.credit_mockup_image_pro if tier == "pro" else settings.credit_mockup_image_basic
        )

        interaction = AIInteraction(
            user_id=user_id,
            collab_id=collab_id,
            command="mockup_image" if kind == "image" else "mockup_audio",
            args_json={"brief": existing.brief, "kind": kind, "consent_id": str(existing.id)},
            cost_credits=cost,
            status="queued",
        )
        db.add(interaction)
        await db.flush()

        try:
            reservation_id = await reserve_credits(user_id, cost, interaction.id, http)
            interaction.billing_reservation_id = reservation_id
        except BillingInsufficientCreditsError:
            interaction.status = "rejected_insufficient_credits"
            await db.commit()
            raise HTTPException(status_code=402, detail="Insufficient credits to generate mockup")

        asset = MockupAsset(
            mockup_consent_id=existing.id,
            replicate_prediction_id="pending",
            kind="image" if kind == "image" else "audio",
            s3_key="",
            watermark_meta={},
        )
        db.add(asset)
        await db.flush()

        interaction.mockup_asset_id = asset.id
        await db.commit()

        webhook_url = settings.replicate_webhook_url
        if kind == "image":
            from app.workers.generation_tasks import enqueue_image_prediction
            enqueue_image_prediction.delay(
                str(interaction.id), str(asset.id),
                existing.brief, tier, webhook_url,
            )
        else:
            from app.workers.generation_tasks import enqueue_audio_prediction
            enqueue_audio_prediction.delay(
                str(interaction.id), str(asset.id),
                existing.brief, tier, webhook_url,
            )

        return ConsentApprovedResponse(
            consent_id=existing.id,
            status="approved",
            ai_interaction_id=interaction.id,
            estimated_seconds=60 if kind == "image" else 45,
        )

    # --- Party A conflict ---
    if existing and existing.requested_by == user_id:
        raise HTTPException(
            status_code=409,
            detail={"message": "Consent already exists", "status": existing.status},
        )

    # --- Party A creates new consent ---
    now = datetime.now(timezone.utc)
    consent = MockupConsent(
        collab_id=collab_id,
        requested_by=user_id,
        party_a_consented_at=now,
        lifespan_days=body.lifespan_days,
        brief=body.brief,
        status="pending_b",
        generation_kind=body.kind,
        expires_consent_at=now + timedelta(hours=48),
    )
    db.add(consent)
    await db.commit()

    return ConsentCreatedResponse(
        consent_id=consent.id,
        status="pending_b",
        message="Waiting for your collaborator to consent.",
    )


# ---------------------------------------------------------------------------
# GET /collabs/{id}/mockups
# ---------------------------------------------------------------------------

@router.get("/collabs/{collab_id}/mockups", response_model=MockupListResponse)
async def list_mockups(
    collab_id: uuid.UUID,
    include_expired: bool = False,
    request: Request = None,
    db: AsyncSession = Depends(get_db),
) -> MockupListResponse:
    http = _get_http(request)
    user_id = _get_user_id(request)

    # Verify participation
    participants = await _get_collab_participants(collab_id, http)
    if participants and user_id not in participants:
        raise HTTPException(status_code=404, detail="Collab not found or user not a participant")

    consents_result = await db.execute(
        select(MockupConsent.id).where(MockupConsent.collab_id == collab_id)
    )
    consent_ids = [r for (r,) in consents_result.all()]

    query = select(MockupAsset).where(MockupAsset.mockup_consent_id.in_(consent_ids))
    if not include_expired:
        query = query.where(MockupAsset.active.is_(True))

    assets_result = await db.execute(query)
    assets = assets_result.scalars().all()

    out = []
    for asset in assets:
        try:
            signed_url, signed_expires = generate_signed_url(asset.s3_key)
        except Exception:
            signed_url = ""
            signed_expires = datetime.now(timezone.utc)

        out.append(
            MockupAssetOut(
                id=asset.id,
                consent_id=asset.mockup_consent_id,
                kind=asset.kind,
                active=asset.active,
                generated_at=asset.generated_at,
                expires_at=asset.expires_at,
                signed_url=signed_url,
                signed_url_expires_at=signed_expires,
            )
        )

    return MockupListResponse(mockups=out)


# ---------------------------------------------------------------------------
# POST /ai/mockups/{asset_id}/screenshot-event
# ---------------------------------------------------------------------------

@router.post("/ai/mockups/{asset_id}/screenshot-event", status_code=204)
async def screenshot_event(
    asset_id: uuid.UUID,
    body: ScreenshotEventRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> None:
    user_id = _get_user_id(request)

    asset_result = await db.execute(
        select(MockupAsset).where(MockupAsset.id == asset_id)
    )
    asset = asset_result.scalars().first()
    if not asset:
        # Fire-and-forget; client swallows 404
        return

    audit = MockupScreenshotAudit(
        mockup_asset_id=asset_id,
        user_id=user_id,
        platform=body.platform,
        detected_at=body.detected_at,
        raw_event={"platform": body.platform, "detected_at": body.detected_at.isoformat()},
    )
    db.add(audit)
    await db.commit()

    logger.info(
        "Audit: user_id=%s screenshot of mockup asset_id=%s at %s platform=%s",
        user_id,
        asset_id,
        body.detected_at.isoformat(),
        body.platform,
    )
