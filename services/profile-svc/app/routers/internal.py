"""
profile-svc — Internal service-to-service endpoints (gateway-scoped, service auth).

GET  /internal/profile/{id}/embedding
GET  /internal/profile/by-user/{user_id}/summary
POST /webhooks/replicate
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import Profile
from app.models.profile import WebhookReceipt
from app.schemas.profile import ProfileEmbeddingResponse, ProfileSummaryInternal

router = APIRouter(tags=["internal"], include_in_schema=False)


def _require_internal(request: Request) -> None:
    """Verify internal caller. In prod: mTLS + gateway header."""
    service = request.headers.get("X-Internal-Service", "")
    import os
    if not service and os.environ.get("ENV", "local") not in ("local", "dev"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Internal endpoint")


@router.get("/internal/profile/{profile_id}/embedding", response_model=ProfileEmbeddingResponse)
async def get_profile_embedding(
    profile_id: uuid.UUID,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> ProfileEmbeddingResponse:
    """Return 1536-d embedding vector for matching-svc."""
    _require_internal(request)
    profile = await session.get(Profile, profile_id)
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")

    return ProfileEmbeddingResponse(
        profile_id=profile.id,
        embedding=list(profile.embedding) if profile.embedding is not None else None,
        dimensions=len(profile.embedding) if profile.embedding is not None else None,
    )


@router.get("/internal/profile/by-user/{user_id}/summary", response_model=ProfileSummaryInternal)
async def get_profile_summary_by_user(
    user_id: uuid.UUID,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> ProfileSummaryInternal:
    """Return profile summary for discovery-svc and notification-svc."""
    _require_internal(request)
    result = await session.execute(select(Profile).where(Profile.user_id == user_id))
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")

    return ProfileSummaryInternal(
        id=profile.id,
        user_id=profile.user_id,
        badge_state=profile.badge_state,
        profile_health_score=profile.profile_health_score,
        display_name=profile.display_name,
    )


@router.post("/webhooks/replicate", status_code=200)
async def replicate_webhook(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> dict:
    """Idempotent Replicate webhook handler for embedding async jobs."""
    body = await request.json()
    prediction_id = body.get("id", "")
    status_val = body.get("status", "")

    # Compute payload hash for idempotency
    payload_hash = hashlib.sha256(str(body).encode()).hexdigest()[:64]

    # Check for duplicate
    existing = await session.execute(
        select(WebhookReceipt).where(
            WebhookReceipt.provider == "replicate",
            WebhookReceipt.external_id == prediction_id,
        )
    )
    if existing.scalar_one_or_none():
        return {"status": "duplicate", "prediction_id": prediction_id}

    # Persist receipt
    receipt = WebhookReceipt(
        provider="replicate",
        external_id=prediction_id,
        payload_hash=payload_hash,
    )
    session.add(receipt)
    await session.commit()

    # Handle completed embeddings
    if status_val == "succeeded" and body.get("output"):
        profile_id = body.get("input", {}).get("profile_id")
        if profile_id:
            from app.workers.embedding_tasks import generate_profile_embedding
            generate_profile_embedding.delay(profile_id)

    return {"status": "ok", "prediction_id": prediction_id}
