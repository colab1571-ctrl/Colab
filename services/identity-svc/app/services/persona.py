"""
identity-svc — Persona API client + webhook HMAC verification.

Persona API: https://withpersona.com/api/v1/
Webhook signature: Persona-Signature: t=<ts>,v1=<hmac-sha256>
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from typing import Any

import httpx

from colab_common.errors import AuthError, ServiceUnavailableError

PERSONA_API_BASE = "https://withpersona.com/api/v1"
PERSONA_API_VERSION = "2023-01-05"
# Max clock skew accepted on webhook timestamps (seconds)
WEBHOOK_TIMESTAMP_TOLERANCE = 300


def _get_api_key() -> str:
    key = os.environ.get("PERSONA_API_KEY", "")
    if not key:
        raise ServiceUnavailableError("Persona API key not configured.")
    return key


def _get_template_id() -> str:
    return os.environ.get("PERSONA_TEMPLATE_ID", "tmpl_placeholder")


def _get_webhook_secret() -> str:
    return os.environ.get("PERSONA_WEBHOOK_SECRET", "")


async def create_inquiry(user_id: str) -> str:
    """
    Create a Persona inquiry and return the inquiry_id.
    Reference-id is set to user_id for correlation.
    """
    headers = {
        "Authorization": f"Bearer {_get_api_key()}",
        "Persona-Version": PERSONA_API_VERSION,
        "Content-Type": "application/json",
    }
    body = {
        "data": {
            "attributes": {
                "inquiry-template-id": _get_template_id(),
                "reference-id": user_id,
            }
        }
    }
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(f"{PERSONA_API_BASE}/inquiries", headers=headers, json=body)
        if resp.status_code not in (200, 201):
            raise ServiceUnavailableError(f"Persona API error: {resp.status_code}")
        data = resp.json()
    return data["data"]["id"]


async def get_session_token(inquiry_id: str) -> str:
    """
    Generate a one-time session token for the Persona SDK.
    Returns the session token string.
    """
    headers = {
        "Authorization": f"Bearer {_get_api_key()}",
        "Persona-Version": PERSONA_API_VERSION,
    }
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            f"{PERSONA_API_BASE}/inquiries/{inquiry_id}/generate-one-time-link",
            headers=headers,
        )
        if resp.status_code not in (200, 201):
            raise ServiceUnavailableError(f"Persona session token error: {resp.status_code}")
        data = resp.json()
    # The one-time link contains the session token as query param; extract or return full URL
    link: str = data.get("data", {}).get("attributes", {}).get("one-time-link", "")
    return link


def verify_webhook_signature(raw_body: bytes, signature_header: str) -> None:
    """
    Verify Persona-Signature header.
    Format: t=<timestamp>,v1=<hmac-sha256>

    Raises AuthError if signature is invalid or timestamp is stale.
    """
    secret = _get_webhook_secret()
    if not secret:
        raise AuthError("Persona webhook secret not configured.")

    parts = dict(item.split("=", 1) for item in signature_header.split(",") if "=" in item)
    ts_str = parts.get("t", "")
    v1 = parts.get("v1", "")

    if not ts_str or not v1:
        raise AuthError("Malformed Persona-Signature header.")

    try:
        ts = int(ts_str)
    except ValueError as exc:
        raise AuthError("Invalid timestamp in Persona-Signature.") from exc

    now = int(time.time())
    if abs(now - ts) > WEBHOOK_TIMESTAMP_TOLERANCE:
        raise AuthError(
            f"Persona webhook timestamp too old or in the future: {abs(now - ts)}s drift."
        )

    expected = hmac.new(
        secret.encode("utf-8"),
        f"{ts_str}.".encode("utf-8") + raw_body,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected, v1):
        raise AuthError("Persona webhook signature verification failed.")


def extract_webhook_data(raw_body: bytes) -> dict[str, Any]:
    """Parse webhook JSON payload."""
    try:
        return json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise AuthError("Invalid Persona webhook JSON.") from exc


def get_inquiry_status(payload: dict[str, Any]) -> str:
    """Extract inquiry status from Persona webhook payload."""
    event_name: str = payload.get("data", {}).get("type", "")
    if event_name == "inquiry.approved":
        return "approved"
    elif event_name == "inquiry.declined":
        return "declined"
    elif event_name == "inquiry.needs-review":
        return "needs_review"
    # Fall through to attributes-level status
    attrs = payload.get("data", {}).get("attributes", {})
    return str(attrs.get("status", "pending"))


def get_face_age_signal(payload: dict[str, Any]) -> str | None:
    """
    Extract face age signal from Persona inquiry webhook payload.
    Returns string age estimate or None.
    Under-18 signals (< 18) trigger needs_review per master §0.
    """
    fields = (
        payload.get("data", {})
        .get("relationships", {})
        .get("template", {})
    )
    # Age signal may be in verification fields
    verifications = payload.get("included", [])
    for v in verifications:
        if v.get("type") == "verification/government-id":
            attrs = v.get("attributes", {})
            age = attrs.get("age-estimate-signal") or attrs.get("age")
            if age is not None:
                return str(age)
    return None


def is_underage_signal(face_age_signal: str | None) -> bool:
    """Return True if the age signal suggests under 18."""
    if face_age_signal is None:
        return False
    try:
        age = float(face_age_signal)
        return age < 18
    except (ValueError, TypeError):
        return False
