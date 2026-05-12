"""
identity-svc — Persona webhook handler.

POST /webhooks/persona/inquiry

- HMAC-SHA256 signature verified before any processing.
- Idempotency: event_id unique in persona_webhook_events table.
- Fast path: return 200 immediately; heavy work is synchronous but
  bounded by one DB write + one event publish.
- Under-18 face age signal flips status to needs_review.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.identity_verification import IdentityVerification, PersonaWebhookEvent
from app.services import persona
from colab_common.db import get_session
from colab_common.errors import AuthError
from colab_common.events import enqueue_outbox

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/persona/inquiry")
async def persona_webhook(request: Request) -> dict[str, str]:
    """
    Receive and process Persona inquiry webhooks.

    Security:
    - HMAC signature verified with constant-time compare.
    - Timestamp checked within ±300s.
    - Idempotent: duplicate event_id → 200 no-op.
    """
    raw_body = await request.body()
    sig_header = request.headers.get("Persona-Signature", "")

    # HMAC verification — raises AuthError on failure
    try:
        persona.verify_webhook_signature(raw_body, sig_header)
    except AuthError as exc:
        raise exc

    payload = persona.extract_webhook_data(raw_body)

    # Extract event ID for idempotency
    event_id: str = payload.get("data", {}).get("id", "") or payload.get("id", "")
    event_name: str = payload.get("data", {}).get("type", "")
    inquiry_id: str = (
        payload.get("data", {}).get("relationships", {}).get("inquiry", {}).get("data", {}).get("id", "")
        or payload.get("data", {}).get("id", "")
    )

    # Determine reference_id (user_id) from inquiry attributes
    ref_id: str = payload.get("data", {}).get("attributes", {}).get("reference-id", "")

    # Get DB session (bypass FastAPI dependency injection for webhook handler)
    from colab_common.db import _get_session_factory

    factory = _get_session_factory()
    async with factory() as db:
        async with db.begin():
            await _process_webhook(db, event_id, event_name, inquiry_id, ref_id, payload)

    return {"status": "ok"}


async def _process_webhook(
    db: AsyncSession,
    event_id: str,
    event_name: str,
    inquiry_id: str,
    ref_id: str,
    payload: dict[str, Any],
) -> None:
    """Process webhook and emit event. Idempotent — duplicate event_id is a no-op."""
    # Idempotency check: try to insert the event log
    try:
        webhook_event = PersonaWebhookEvent(
            event_id=event_id or str(uuid.uuid4()),
            event_name=event_name,
            inquiry_id=inquiry_id,
            raw_payload=payload,
        )
        db.add(webhook_event)
        await db.flush()
    except IntegrityError:
        # Duplicate event — Persona at-least-once delivery
        await db.rollback()
        return

    if not ref_id:
        # Cannot correlate without reference-id
        return

    # Determine status from webhook
    inquiry_status = persona.get_inquiry_status(payload)
    face_age = persona.get_face_age_signal(payload)

    # Under-18 age signal overrides approved → needs_review per master §0
    if inquiry_status == "approved" and persona.is_underage_signal(face_age):
        inquiry_status = "needs_review"

    # Update or create IdentityVerification record
    try:
        user_uuid = uuid.UUID(ref_id)
    except ValueError:
        return

    iv = await db.scalar(
        select(IdentityVerification).where(IdentityVerification.user_id == user_uuid)
    )

    now = datetime.now(UTC)
    if iv is None:
        iv = IdentityVerification(
            user_id=user_uuid,
            persona_inquiry_id=inquiry_id,
            status=inquiry_status,
            face_age_signal=face_age,
            decision_at=now,
            raw_payload=payload,
        )
        db.add(iv)
    else:
        iv.status = inquiry_status
        iv.face_age_signal = face_age
        iv.decision_at = now
        iv.raw_payload = payload
        if inquiry_id:
            iv.persona_inquiry_id = inquiry_id

    # Emit domain event
    event_map = {
        "approved": "identity.verified",
        "declined": "identity.declined",
        "needs_review": "identity.needs_review",
    }
    event_to_emit = event_map.get(inquiry_status)
    if event_to_emit:
        await enqueue_outbox(
            db,
            event_to_emit,
            {
                "user_id": ref_id,
                "persona_inquiry_id": inquiry_id,
                "status": inquiry_status,
                "face_age_signal": face_age,
            },
            dedupe_key=f"{event_to_emit}:{inquiry_id}",
        )
