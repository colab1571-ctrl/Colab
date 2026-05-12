"""
Tests: webhook idempotency, replay attacks, signature verification.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.webhooks import (
    verify_revenuecat_signature,
    verify_stripe_signature,
)
from colab_common.errors import AuthError


# ---------------------------------------------------------------------------
# Signature verification tests
# ---------------------------------------------------------------------------


class TestStripeSignatureVerification:
    def test_invalid_secret_raises_auth_error(self):
        """Bad secret should raise AuthError, not crash."""
        raw_body = b'{"id": "evt_test", "type": "invoice.paid"}'
        with pytest.raises(AuthError):
            verify_stripe_signature(raw_body, "t=1234,v1=bad_sig", "whsec_wrong")

    def test_malformed_body_raises_auth_error(self):
        with pytest.raises(AuthError):
            verify_stripe_signature(b"not-json", "t=1,v1=abc", "whsec_secret")

    def test_valid_stripe_event_accepted(self):
        """Construct a valid Stripe HMAC signature and verify it passes."""
        import stripe

        secret = "whsec_test_secret_for_tests"
        payload = json.dumps({
            "id": "evt_test_001",
            "type": "invoice.paid",
            "created": int(time.time()),
            "data": {"object": {}},
        })
        raw_body = payload.encode()
        timestamp = str(int(time.time()))

        # Build valid signature per Stripe spec
        signed_payload = f"{timestamp}.{payload}"
        sig = hmac.new(
            secret.encode(), signed_payload.encode(), hashlib.sha256
        ).hexdigest()
        sig_header = f"t={timestamp},v1={sig}"

        with patch("stripe.Webhook.construct_event") as mock_construct:
            mock_construct.return_value = json.loads(payload)
            event = verify_stripe_signature(raw_body, sig_header, secret)
            assert event["id"] == "evt_test_001"


class TestRevenueCatSignatureVerification:
    def test_correct_bearer_passes(self):
        assert verify_revenuecat_signature("rc_webhook_secret", "rc_webhook_secret") is True

    def test_wrong_bearer_fails(self):
        assert verify_revenuecat_signature("rc_wrong_secret", "rc_correct_secret") is False

    def test_constant_time_compare_partial_match(self):
        """Partial match should not pass (timing attack guard)."""
        assert verify_revenuecat_signature("rc_webhook_secret_EXTRA", "rc_webhook_secret") is False

    def test_empty_bearer_fails(self):
        assert verify_revenuecat_signature("", "rc_webhook_secret") is False


# ---------------------------------------------------------------------------
# Ledger idempotency tests
# ---------------------------------------------------------------------------


class TestWebhookLedgerIdempotency:
    @pytest.mark.asyncio
    async def test_duplicate_event_returns_not_new(self, db):
        """Same provider_event_id inserted twice → second is not new."""
        from app.services.webhooks import insert_ledger_event

        event_id = f"evt_{uuid.uuid4().hex[:16]}"
        now = datetime.now(UTC)
        payload = {"id": event_id, "type": "test.event"}

        ledger_id1, is_new1 = await insert_ledger_event(
            db=db,
            provider="stripe",
            provider_event_id=event_id,
            event_type="test.event",
            event_timestamp=now,
            payload=payload,
            signature_valid=True,
        )
        await db.flush()

        ledger_id2, is_new2 = await insert_ledger_event(
            db=db,
            provider="stripe",
            provider_event_id=event_id,
            event_type="test.event",
            event_timestamp=now,
            payload=payload,
            signature_valid=True,
        )

        assert is_new1 is True
        assert is_new2 is False
        assert ledger_id1 is not None
        assert ledger_id2 is None

    @pytest.mark.asyncio
    async def test_same_event_different_provider_both_new(self, db):
        """Same event_id on different providers are distinct."""
        from app.services.webhooks import insert_ledger_event

        event_id = f"evt_{uuid.uuid4().hex[:16]}"
        now = datetime.now(UTC)
        payload = {"id": event_id, "type": "test.event"}

        _, is_new_stripe = await insert_ledger_event(
            db, "stripe", event_id, "test.event", now, payload, True
        )
        await db.flush()
        _, is_new_rc = await insert_ledger_event(
            db, "revenuecat", event_id, "INITIAL_PURCHASE", now, payload, True
        )

        assert is_new_stripe is True
        assert is_new_rc is True

    @pytest.mark.asyncio
    async def test_100x_replay_single_entry(self, db):
        """Replaying same event 100 times creates exactly one ledger row."""
        from sqlalchemy import select, func
        from app.models.billing import WebhookEventLedger
        from app.services.webhooks import insert_ledger_event

        event_id = f"evt_replay_{uuid.uuid4().hex[:8]}"
        now = datetime.now(UTC)
        payload = {"id": event_id, "type": "invoice.paid"}

        new_count = 0
        for _ in range(100):
            _, is_new = await insert_ledger_event(
                db, "stripe", event_id, "invoice.paid", now, payload, True
            )
            if is_new:
                new_count += 1
                await db.flush()

        assert new_count == 1

        # Verify DB has exactly one row
        count_result = await db.execute(
            select(func.count()).where(
                WebhookEventLedger.provider_event_id == event_id
            )
        )
        assert count_result.scalar() == 1
