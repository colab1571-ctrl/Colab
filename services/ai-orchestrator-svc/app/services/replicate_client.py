"""
Replicate client — async prediction creation with webhook delivery.

Webhook verification: HMAC-SHA256 using Replicate-Signature header.
Idempotency: Redis key replicate:{prediction_id} with 24h TTL.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import uuid
from typing import Any

import httpx

from app.config import get_ai_settings

logger = logging.getLogger(__name__)

REPLICATE_API_URL = "https://api.replicate.com/v1"


def verify_webhook_signature(raw_body: bytes, signature_header: str | None) -> bool:
    """
    Verify Replicate webhook signature.
    Header format: sha256=<hex_digest>
    """
    settings = get_ai_settings()
    if not signature_header:
        logger.warning("Missing Replicate-Signature header")
        return False
    try:
        scheme, received_hex = signature_header.split("=", 1)
        if scheme != "sha256":
            return False
    except ValueError:
        return False

    expected_hex = hmac.new(
        settings.replicate_webhook_secret.encode(),
        raw_body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected_hex, received_hex)


async def create_image_prediction(
    prompt: str,
    tier: str,  # "basic" | "pro"
    webhook_url: str,
    http: httpx.AsyncClient,
) -> str:
    """
    Create a Replicate image prediction (SDXL for basic, FLUX-1.1-pro for pro).
    Returns prediction_id.
    """
    settings = get_ai_settings()
    model = (
        settings.replicate_model_image_pro
        if tier == "pro"
        else settings.replicate_model_image_basic
    )
    negative_prompt = "nude, explicit, gore, violence, real faces, text overlays, watermarks"
    steps = 50 if tier == "pro" else 30

    payload: dict[str, Any] = {
        "version": model,
        "input": {
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "width": 1024,
            "height": 1024,
            "num_inference_steps": steps,
            "guidance_scale": 7.0,
        },
        "webhook": webhook_url,
        "webhook_events_filter": ["completed"],
    }

    resp = await http.post(
        f"{REPLICATE_API_URL}/predictions",
        json=payload,
        headers={
            "Authorization": f"Token {settings.replicate_api_token}",
            "Content-Type": "application/json",
        },
        timeout=15.0,
    )
    resp.raise_for_status()
    return resp.json()["id"]


async def create_audio_prediction(
    prompt: str,
    tier: str,  # "basic" | "pro"
    webhook_url: str,
    http: httpx.AsyncClient,
) -> str:
    """
    Create a Replicate audio prediction (MusicGen for basic, Stable Audio for pro).
    Returns prediction_id.
    """
    settings = get_ai_settings()
    model = (
        settings.replicate_model_audio_pro
        if tier == "pro"
        else settings.replicate_model_audio_basic
    )
    duration = 20 if tier == "pro" else 10

    payload: dict[str, Any] = {
        "version": model,
        "input": {
            "prompt": prompt,
            "duration": duration,
            "output_format": "mp3",
        },
        "webhook": webhook_url,
        "webhook_events_filter": ["completed"],
    }

    resp = await http.post(
        f"{REPLICATE_API_URL}/predictions",
        json=payload,
        headers={
            "Authorization": f"Token {settings.replicate_api_token}",
            "Content-Type": "application/json",
        },
        timeout=15.0,
    )
    resp.raise_for_status()
    return resp.json()["id"]


async def get_prediction(prediction_id: str, http: httpx.AsyncClient) -> dict[str, Any]:
    """Poll a Replicate prediction for status."""
    settings = get_ai_settings()
    resp = await http.get(
        f"{REPLICATE_API_URL}/predictions/{prediction_id}",
        headers={"Authorization": f"Token {settings.replicate_api_token}"},
        timeout=10.0,
    )
    resp.raise_for_status()
    return resp.json()
