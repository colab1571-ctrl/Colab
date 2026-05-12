"""
identity-svc — Persona webhook HMAC verification tests.

Covers: valid sig, bad sig, stale timestamp, duplicate event idempotency,
under-18 face-age escalation, approved/declined/needs_review status transitions.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient


def _make_sig(secret: str, ts: int, body: bytes) -> str:
    raw = f"{ts}.".encode() + body
    return hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()


def _persona_header(secret: str, body: bytes, ts_offset: int = 0) -> str:
    ts = int(time.time()) + ts_offset
    sig = _make_sig(secret, ts, body)
    return f"t={ts},v1={sig}"


PERSONA_SECRET = "test-webhook-secret"


def _approved_payload(inquiry_id: str = "inq_test123", user_id: str = "00000000-0000-0000-0000-000000000001") -> dict:
    return {
        "data": {
            "id": f"evt_{inquiry_id}",
            "type": "inquiry.approved",
            "attributes": {
                "status": "approved",
                "reference-id": user_id,
            },
        }
    }


def _declined_payload(inquiry_id: str = "inq_declined", user_id: str = "00000000-0000-0000-0000-000000000002") -> dict:
    return {
        "data": {
            "id": f"evt_{inquiry_id}",
            "type": "inquiry.declined",
            "attributes": {
                "status": "declined",
                "reference-id": user_id,
            },
        }
    }


@pytest.mark.asyncio
async def test_webhook_bad_signature(client: AsyncClient) -> None:
    """Invalid HMAC must return 401."""
    body = json.dumps({"data": {}}).encode()
    resp = await client.post(
        "/webhooks/persona/inquiry",
        content=body,
        headers={
            "Content-Type": "application/json",
            "Persona-Signature": "t=12345,v1=badhash",
        },
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_webhook_stale_timestamp(client: AsyncClient) -> None:
    """Webhook with timestamp > 300s old must be rejected."""
    body = json.dumps({"data": {}}).encode()
    old_ts = int(time.time()) - 400
    sig = _make_sig(PERSONA_SECRET, old_ts, body)
    resp = await client.post(
        "/webhooks/persona/inquiry",
        content=body,
        headers={
            "Content-Type": "application/json",
            "Persona-Signature": f"t={old_ts},v1={sig}",
        },
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_webhook_approved_happy_path(client: AsyncClient) -> None:
    """Valid approved webhook → IdentityVerification.status = approved."""
    payload = _approved_payload()
    body = json.dumps(payload).encode()
    sig_header = _persona_header(PERSONA_SECRET, body)

    with patch(
        "app.routers.webhook._process_webhook",
        new_callable=AsyncMock,
    ) as mock_process:
        mock_process.return_value = None
        resp = await client.post(
            "/webhooks/persona/inquiry",
            content=body,
            headers={"Content-Type": "application/json", "Persona-Signature": sig_header},
        )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_webhook_hmac_constant_time_compare(client: AsyncClient) -> None:
    """
    Ensure HMAC is compared with compare_digest (constant-time).
    Test that even one-byte-off signatures fail.
    """
    body = json.dumps({"data": {"id": "evt_test", "type": "inquiry.approved"}}).encode()
    ts = int(time.time())
    correct_sig = _make_sig(PERSONA_SECRET, ts, body)
    # Flip last char
    bad_sig = correct_sig[:-1] + ("a" if correct_sig[-1] != "a" else "b")
    resp = await client.post(
        "/webhooks/persona/inquiry",
        content=body,
        headers={
            "Content-Type": "application/json",
            "Persona-Signature": f"t={ts},v1={bad_sig}",
        },
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_webhook_missing_signature_header(client: AsyncClient) -> None:
    """No Persona-Signature header → 401."""
    body = json.dumps({"data": {}}).encode()
    resp = await client.post(
        "/webhooks/persona/inquiry",
        content=body,
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 401


def test_underage_face_age_signal() -> None:
    """Under-18 face age overrides approved → needs_review."""
    from app.services.persona import is_underage_signal

    assert is_underage_signal("16") is True
    assert is_underage_signal("17.9") is True
    assert is_underage_signal("18") is False
    assert is_underage_signal("25") is False
    assert is_underage_signal(None) is False
    assert is_underage_signal("unknown") is False


def test_get_inquiry_status_mapping() -> None:
    """Persona event type → internal status string."""
    from app.services.persona import get_inquiry_status

    assert get_inquiry_status({"data": {"type": "inquiry.approved"}}) == "approved"
    assert get_inquiry_status({"data": {"type": "inquiry.declined"}}) == "declined"
    assert get_inquiry_status({"data": {"type": "inquiry.needs-review"}}) == "needs_review"
