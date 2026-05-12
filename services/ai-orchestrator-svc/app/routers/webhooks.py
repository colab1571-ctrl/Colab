"""
POST /webhooks/replicate — Replicate prediction webhook handler.

Security: HMAC-SHA256 signature verification.
Idempotency: Redis key replicate:{prediction_id} with 24h TTL.
On success: download artifact, moderation scan, watermark, S3 upload, credit confirm, notify.
On failure: credit refund, notify.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_ai_settings
from app.db import get_db
from app.models import AIInteraction, MockupAsset, MockupConsent
from app.services.billing_client import commit_reservation, release_reservation
from app.services.moderation_client import file_moderation_case, scan_image
from app.services.replicate_client import verify_webhook_signature
from app.services.s3_client import upload_asset
from app.watermark.audio import apply_audio_watermark
from app.watermark.image import apply_image_watermark

router = APIRouter(tags=["webhooks"])
logger = logging.getLogger(__name__)

IDEMPOTENCY_TTL = 86400  # 24h


@router.post("/webhooks/replicate", status_code=200)
async def replicate_webhook(request: Request) -> dict[str, str]:
    settings = get_ai_settings()
    raw_body = await request.body()

    # 1. Verify HMAC signature
    sig_header = request.headers.get("Replicate-Signature")
    if not verify_webhook_signature(raw_body, sig_header):
        logger.warning("Replicate webhook signature verification failed")
        raise HTTPException(status_code=403, detail="Invalid signature")

    payload: dict[str, Any] = await request.json() if raw_body else {}
    prediction_id = payload.get("id", "")
    if not prediction_id:
        raise HTTPException(status_code=400, detail="Missing prediction id")

    # 2. Idempotency check
    redis = request.app.state.redis
    idem_key = f"replicate:{prediction_id}"
    already_processed = await redis.get(idem_key)
    if already_processed:
        logger.info("Replicate webhook: prediction %s already processed (idempotent)", prediction_id)
        return {"status": "already_processed"}

    # 3. Look up AIInteraction by prediction_id
    db: AsyncSession = request.app.state.db_session_factory()
    async with db:
        interaction_result = await db.execute(
            select(AIInteraction).where(AIInteraction.replicate_prediction_id == prediction_id)
        )
        interaction = interaction_result.scalars().first()

        asset_result = await db.execute(
            select(MockupAsset).where(MockupAsset.replicate_prediction_id == prediction_id)
        )
        asset = asset_result.scalars().first()

        if not interaction:
            logger.warning("Replicate webhook: unknown prediction_id %s", prediction_id)
            await redis.setex(idem_key, IDEMPOTENCY_TTL, "1")
            return {"status": "unknown_prediction"}

        status = payload.get("status", "")
        http = request.app.state.http

        # 4. Handle failure
        if status == "failed":
            await _handle_failure(
                interaction, asset, payload.get("error", "Replicate prediction failed"), db, http
            )
            await redis.setex(idem_key, IDEMPOTENCY_TTL, "1")
            return {"status": "failure_handled"}

        # 5. Handle success
        if status == "succeeded":
            output = payload.get("output")
            if not output:
                await _handle_failure(interaction, asset, "No output in Replicate response", db, http)
                await redis.setex(idem_key, IDEMPOTENCY_TTL, "1")
                return {"status": "failure_handled"}

            # output may be a list (image) or single URL (audio)
            artifact_url = output[0] if isinstance(output, list) else output

            try:
                await _handle_success(interaction, asset, artifact_url, db, http)
            except Exception as exc:
                logger.error("Webhook success handler failed: %s", exc)
                await _handle_failure(interaction, asset, str(exc), db, http)

        # 6. Set idempotency key
        await redis.setex(idem_key, IDEMPOTENCY_TTL, "1")
        return {"status": "ok"}


async def _handle_success(
    interaction: AIInteraction,
    asset: MockupAsset | None,
    artifact_url: str,
    db: AsyncSession,
    http: httpx.AsyncClient,
) -> None:
    settings = get_ai_settings()

    # Download artifact from Replicate
    resp = await http.get(artifact_url, timeout=30.0)
    resp.raise_for_status()
    artifact_bytes = resp.content
    content_type = resp.headers.get("content-type", "image/jpeg")

    kind = asset.kind if asset else ("audio" if "audio" in artifact_url else "image")
    now = datetime.now(timezone.utc)

    # Determine user context for watermark
    user_a_name = "User A"
    user_b_name = "User B"
    user_a_id = str(interaction.user_id)
    user_b_id = str(interaction.user_id)

    if asset and asset.mockup_consent_id:
        consent_result = await db.execute(
            select(MockupConsent).where(MockupConsent.id == asset.mockup_consent_id)
        )
        consent = consent_result.scalars().first()
        if consent:
            user_a_id = str(consent.requested_by)

    # Moderation scan (image only — Rekognition)
    if kind == "image":
        mod_score = await scan_image(artifact_bytes, http)
        if mod_score >= settings.moderation_block_threshold:
            if asset:
                asset.moderation_score = mod_score
                asset.moderation_status = "blocked"
                asset.active = False
            interaction.status = "moderation_blocked"
            await db.commit()
            if asset:
                await file_moderation_case(asset.id, "mockup_asset", "auto", http)
            if interaction.billing_reservation_id:
                await release_reservation(interaction.billing_reservation_id, "moderation_block", http)
            logger.warning("Mockup %s blocked by moderation (score=%.3f)", asset and asset.id, mod_score)
            return
    else:
        mod_score = 0.0

    # Apply watermark
    ts = now.isoformat()
    if kind == "image":
        watermarked_bytes, watermark_meta = apply_image_watermark(
            artifact_bytes, user_a_name, user_b_name, ts
        )
        s3_content_type = "image/jpeg"
        file_ext = "jpg"
    else:
        asset_uuid = asset.id if asset else uuid.uuid4()
        watermarked_bytes, watermark_meta = apply_audio_watermark(
            artifact_bytes,
            asset_uuid,
            uuid.UUID(user_a_id),
            uuid.UUID(user_b_id),
            ts,
        )
        s3_content_type = "audio/mpeg"
        file_ext = "mp3"

    # S3 upload
    collab_id = str(interaction.collab_id or uuid.uuid4())
    asset_id = str(asset.id) if asset else str(uuid.uuid4())
    s3_key = f"mockups/{collab_id}/{asset_id}/{kind}.{file_ext}"

    file_size = await upload_asset(watermarked_bytes, s3_key, s3_content_type)

    # Determine lifespan
    lifespan_days = 1
    if asset and asset.mockup_consent_id:
        consent_result = await db.execute(
            select(MockupConsent).where(MockupConsent.id == asset.mockup_consent_id)
        )
        consent_obj = consent_result.scalars().first()
        if consent_obj:
            lifespan_days = consent_obj.lifespan_days

    expires_at = now + timedelta(days=lifespan_days)

    # Update MockupAsset
    if asset:
        asset.s3_key = s3_key
        asset.watermark_meta = watermark_meta
        asset.moderation_score = mod_score
        asset.moderation_status = "passed"
        asset.generated_at = now
        asset.expires_at = expires_at
        asset.active = True
        asset.file_size_bytes = file_size

    # Update AIInteraction
    interaction.status = "completed"
    interaction.completed_at = now

    await db.commit()

    # Confirm credit charge
    if interaction.billing_reservation_id:
        await commit_reservation(interaction.billing_reservation_id, http)

    logger.info(
        "Mockup generation completed: prediction=%s asset=%s s3_key=%s",
        interaction.replicate_prediction_id,
        asset and asset.id,
        s3_key,
    )


async def _handle_failure(
    interaction: AIInteraction,
    asset: MockupAsset | None,
    reason: str,
    db: AsyncSession,
    http: httpx.AsyncClient,
) -> None:
    interaction.status = "failed"
    interaction.failure_reason = reason
    if asset:
        asset.active = False
    await db.commit()

    if interaction.billing_reservation_id:
        await release_reservation(interaction.billing_reservation_id, reason[:100], http)

    logger.warning(
        "Replicate prediction failed for interaction %s: %s",
        interaction.id,
        reason,
    )
