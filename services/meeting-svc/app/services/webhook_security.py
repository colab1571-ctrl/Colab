"""
Recall.ai webhook HMAC-SHA256 signature verification.

Header: X-Recall-Signature: sha256=<hex>
Secret: stored in Secrets Manager → MEETING_RECALL_WEBHOOK_SECRET env var.

Used as FastAPI middleware and directly in the webhook endpoint handler.
"""

from __future__ import annotations

import hashlib
import hmac
import logging

from fastapi import HTTPException, Request

logger = logging.getLogger(__name__)


def verify_recall_signature(raw_body: bytes, signature_header: str, secret: str) -> bool:
    """
    Verify an HMAC-SHA256 Recall.ai webhook signature.

    Returns True if valid, False if invalid.
    Does NOT raise — callers decide how to handle failure.
    """
    if not signature_header:
        logger.warning("Recall webhook: missing X-Recall-Signature header")
        return False

    if not signature_header.startswith("sha256="):
        logger.warning("Recall webhook: malformed signature header: %s", signature_header)
        return False

    expected = hmac.new(
        secret.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()

    expected_header = f"sha256={expected}"
    is_valid = hmac.compare_digest(expected_header, signature_header)

    if not is_valid:
        logger.warning(
            "Recall webhook: invalid HMAC — got %s expected %s",
            signature_header[:20] + "...",
            expected_header[:20] + "...",
        )

    return is_valid


async def require_recall_signature(request: Request, secret: str) -> bytes:
    """
    FastAPI dependency: read raw body + verify HMAC.

    Returns raw body bytes (so the endpoint can pass to task).
    Raises 403 HTTPException on invalid signature.
    """
    raw_body = await request.body()
    sig_header = request.headers.get("X-Recall-Signature", "")

    if not verify_recall_signature(raw_body, sig_header, secret):
        logger.error(
            "Recall webhook signature verification failed — remote=%s",
            request.client.host if request.client else "unknown",
        )
        raise HTTPException(status_code=403, detail="Invalid webhook signature")

    return raw_body
