"""
Internal moderation-svc client.

Calls moderation-svc to scan generated assets before delivery.
Text: OpenAI moderation endpoint (via moderation-svc).
Image: AWS Rekognition content moderation (via moderation-svc).
"""

from __future__ import annotations

import logging
import uuid

import httpx

from app.config import get_ai_settings

logger = logging.getLogger(__name__)


async def scan_text(text: str, http: httpx.AsyncClient) -> float:
    """
    Scan text through moderation-svc. Returns moderation score.
    """
    settings = get_ai_settings()
    try:
        resp = await http.post(
            f"{settings.moderation_svc_url}/internal/scan/text",
            json={"text": text},
            timeout=3.0,
        )
        resp.raise_for_status()
        return resp.json().get("score", 0.0)
    except Exception as exc:
        logger.warning("Text moderation scan failed: %s — passing through", exc)
        return 0.0


async def scan_image(image_bytes: bytes, http: httpx.AsyncClient) -> float:
    """
    Scan image bytes through moderation-svc (Rekognition). Returns max severity score.
    """
    settings = get_ai_settings()
    try:
        resp = await http.post(
            f"{settings.moderation_svc_url}/internal/scan/image",
            content=image_bytes,
            headers={"Content-Type": "image/png"},
            timeout=5.0,
        )
        resp.raise_for_status()
        return resp.json().get("score", 0.0)
    except Exception as exc:
        logger.warning("Image moderation scan failed: %s — passing through", exc)
        return 0.0


async def file_moderation_case(
    subject_id: uuid.UUID,
    subject_type: str,
    kind: str,
    http: httpx.AsyncClient,
) -> None:
    """File a ModerationCase when output is blocked."""
    settings = get_ai_settings()
    try:
        await http.post(
            f"{settings.moderation_svc_url}/internal/cases",
            json={
                "subject_id": str(subject_id),
                "subject_type": subject_type,
                "kind": kind,
                "source": "ai_orchestrator",
            },
            timeout=3.0,
        )
    except Exception as exc:
        logger.warning("Failed to file moderation case for %s: %s", subject_id, exc)
