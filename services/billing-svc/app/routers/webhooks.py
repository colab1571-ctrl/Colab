"""
billing-svc — Webhook ingestion endpoints.

POST /webhooks/stripe    — Stripe signed events
POST /webhooks/revenuecat — RevenueCat bearer-token events

Pipeline:
  1. Verify signature
  2. Insert into WebhookEventLedger (idempotency gate)
  3. Enqueue Celery task for async processing
  4. Return 200 within <5s
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Header, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.webhooks import (
    dispatch_rc_event,
    dispatch_stripe_event,
    insert_ledger_event,
    verify_revenuecat_signature,
    verify_stripe_signature,
)
from colab_common.db import get_session
from colab_common.errors import AuthError
from colab_common.settings import get_settings

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

logger = logging.getLogger(__name__)


def _get_redis(request: Request):  # type: ignore[return]
    return request.app.state.redis


def _get_amqp(request: Request):  # type: ignore[return]
    return request.app.state.amqp_channel


@router.post("/stripe")
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(..., alias="Stripe-Signature"),
) -> JSONResponse:
    """
    Receive and process Stripe webhooks.
    Returns 200 on accept (including duplicates); 400 on signature failure.
    """
    settings = get_settings()
    raw_body = await request.body()

    try:
        event = verify_stripe_signature(
            raw_body=raw_body,
            sig_header=stripe_signature,
            webhook_secret=settings.stripe_webhook_secret,
        )
    except AuthError as exc:
        logger.warning("Stripe signature verification failed: %s", exc)
        return JSONResponse(status_code=400, content={"error": str(exc)})

    event_id = event.get("id", "")
    event_type = event.get("type", "")
    created_ts = event.get("created", 0)
    event_ts = datetime.fromtimestamp(created_ts, tz=UTC)

    from colab_common.db import async_session_factory
    async with async_session_factory() as db:
        try:
            ledger_id, is_new = await insert_ledger_event(
                db=db,
                provider="stripe",
                provider_event_id=event_id,
                event_type=event_type,
                event_timestamp=event_ts,
                payload=event,
                signature_valid=True,
            )
            if not is_new:
                return JSONResponse(status_code=200, content={"status": "duplicate"})

            await dispatch_stripe_event(
                db=db,
                ledger_id=ledger_id,
                event=event,
                amqp_channel=_get_amqp(request),
                redis=_get_redis(request),
                settings=settings,
            )
        except Exception as exc:
            logger.error("Stripe webhook processing error: %s", exc, exc_info=True)
            await db.rollback()
            # Return 500 so Stripe retries (we'll dedup on retry)
            return JSONResponse(status_code=500, content={"error": "internal processing error"})

    return JSONResponse(status_code=200, content={"status": "ok"})


@router.post("/revenuecat")
async def revenuecat_webhook(
    request: Request,
    authorization: str = Header(..., alias="Authorization"),
) -> JSONResponse:
    """
    Receive and process RevenueCat webhooks.
    Returns 200 on accept; 401 on auth failure.
    """
    settings = get_settings()

    if not verify_revenuecat_signature(authorization, settings.revenuecat_webhook_secret):
        logger.warning("RevenueCat webhook signature verification failed")
        return JSONResponse(status_code=401, content={"error": "unauthorized"})

    import json as json_lib
    try:
        payload: dict[str, Any] = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "invalid JSON"})

    # RC event id and type extraction
    inner_event = payload.get("event", payload)
    event_id = inner_event.get("id", str(id(payload)))  # RC events have an id field
    event_type = inner_event.get("type", "UNKNOWN")
    event_ts_ms = inner_event.get("event_timestamp_ms", 0)
    event_ts = datetime.fromtimestamp(event_ts_ms / 1000 if event_ts_ms else 0, tz=UTC)

    from colab_common.db import async_session_factory
    async with async_session_factory() as db:
        try:
            ledger_id, is_new = await insert_ledger_event(
                db=db,
                provider="revenuecat",
                provider_event_id=event_id,
                event_type=event_type,
                event_timestamp=event_ts,
                payload=payload,
                signature_valid=True,
            )
            if not is_new:
                return JSONResponse(status_code=200, content={"status": "duplicate"})

            await dispatch_rc_event(
                db=db,
                ledger_id=ledger_id,
                event=payload,
                amqp_channel=_get_amqp(request),
                redis=_get_redis(request),
                settings=settings,
            )
        except Exception as exc:
            logger.error("RevenueCat webhook processing error: %s", exc, exc_info=True)
            await db.rollback()
            return JSONResponse(status_code=500, content={"error": "internal processing error"})

    return JSONResponse(status_code=200, content={"status": "ok"})
