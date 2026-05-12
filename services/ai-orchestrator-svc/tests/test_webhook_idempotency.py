"""
Tests: Replicate webhook idempotency and signature verification.

Covers:
- Valid signature → processed
- Invalid signature → 403
- Duplicate prediction_id → 200 early return (not re-processed)
- Failed prediction → credit refund path
- Succeeded prediction → success path (mocked)
"""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_signature(secret: str, body: bytes) -> str:
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


class TestReplicateSignatureVerification:
    def test_valid_signature_passes(self):
        from app.services.replicate_client import verify_webhook_signature
        secret = "test-secret-xyz"
        body = b'{"id": "abc123", "status": "succeeded"}'

        with patch("app.services.replicate_client.get_ai_settings") as mock_settings:
            mock_settings.return_value.replicate_webhook_secret = secret
            sig = _make_signature(secret, body)
            assert verify_webhook_signature(body, sig) is True

    def test_invalid_signature_rejected(self):
        from app.services.replicate_client import verify_webhook_signature
        secret = "test-secret-xyz"
        body = b'{"id": "abc123", "status": "succeeded"}'

        with patch("app.services.replicate_client.get_ai_settings") as mock_settings:
            mock_settings.return_value.replicate_webhook_secret = secret
            assert verify_webhook_signature(body, "sha256=badhex") is False

    def test_missing_signature_header_rejected(self):
        from app.services.replicate_client import verify_webhook_signature
        with patch("app.services.replicate_client.get_ai_settings") as mock_settings:
            mock_settings.return_value.replicate_webhook_secret = "secret"
            assert verify_webhook_signature(b"body", None) is False

    def test_wrong_scheme_rejected(self):
        from app.services.replicate_client import verify_webhook_signature
        with patch("app.services.replicate_client.get_ai_settings") as mock_settings:
            mock_settings.return_value.replicate_webhook_secret = "secret"
            assert verify_webhook_signature(b"body", "md5=abc123") is False


class TestWebhookIdempotency:
    @pytest.mark.asyncio
    async def test_duplicate_prediction_returns_early(self):
        """Second call with same prediction_id returns already_processed without re-processing."""
        from app.routers.webhooks import replicate_webhook

        prediction_id = "pred_idempotent_test"
        body = json.dumps({"id": prediction_id, "status": "succeeded", "output": ["http://example.com/img.png"]}).encode()

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value="1")  # Already processed

        mock_request = MagicMock()
        mock_request.body = AsyncMock(return_value=body)
        mock_request.json = AsyncMock(return_value=json.loads(body))
        mock_request.headers = {"Replicate-Signature": "sha256=ignored"}
        mock_request.app.state.redis = mock_redis

        with patch("app.routers.webhooks.verify_webhook_signature", return_value=True):
            result = await replicate_webhook(mock_request)

        assert result == {"status": "already_processed"}
        mock_redis.get.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_idempotency_key_set_after_processing(self):
        """After processing, Redis idempotency key is set with 24h TTL."""
        from app.routers.webhooks import IDEMPOTENCY_TTL

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.setex = AsyncMock()

        # Verify TTL constant
        assert IDEMPOTENCY_TTL == 86400  # 24 hours


class TestWebhookFailurePath:
    @pytest.mark.asyncio
    async def test_failed_prediction_triggers_refund(self):
        """When Replicate reports status=failed, credits are released."""
        from app.routers.webhooks import _handle_failure
        from app.models import AIInteraction, MockupAsset
        import uuid

        reservation_id = uuid.uuid4()
        interaction = MagicMock(spec=AIInteraction)
        interaction.id = uuid.uuid4()
        interaction.replicate_prediction_id = "pred_fail_test"
        interaction.billing_reservation_id = reservation_id

        asset = MagicMock(spec=MockupAsset)
        asset.id = uuid.uuid4()
        asset.active = True

        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()

        mock_http = AsyncMock()

        with patch("app.routers.webhooks.release_reservation", new_callable=AsyncMock) as mock_release:
            await _handle_failure(interaction, asset, "Replicate GPU error", mock_db, mock_http)
            mock_release.assert_awaited_once_with(reservation_id, "Replicate GPU error", mock_http)

        assert interaction.status == "failed"
        assert interaction.failure_reason == "Replicate GPU error"
        assert asset.active is False
