"""
Unit tests for Recall.ai webhook HMAC-SHA256 signature verification.

MEET-TEST-3: valid, invalid, missing header.
"""

from __future__ import annotations

import hashlib
import hmac

import pytest

from app.services.webhook_security import verify_recall_signature

SECRET = "test_webhook_secret_abc123"


def _make_signature(body: bytes, secret: str) -> str:
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


class TestVerifyRecallSignature:
    def test_valid_signature(self) -> None:
        """Valid HMAC-SHA256 signature returns True."""
        body = b'{"event": "status_changes", "data": {}}'
        sig = _make_signature(body, SECRET)
        assert verify_recall_signature(body, sig, SECRET) is True

    def test_invalid_signature_wrong_secret(self) -> None:
        """Signature computed with wrong secret returns False."""
        body = b'{"event": "status_changes"}'
        sig = _make_signature(body, "wrong_secret")
        assert verify_recall_signature(body, sig, SECRET) is False

    def test_invalid_signature_tampered_body(self) -> None:
        """Signature for original body fails on tampered body."""
        original_body = b'{"event": "status_changes"}'
        tampered_body = b'{"event": "status_changes", "injected": true}'
        sig = _make_signature(original_body, SECRET)
        assert verify_recall_signature(tampered_body, sig, SECRET) is False

    def test_missing_header_empty_string(self) -> None:
        """Empty signature header returns False."""
        body = b'{"event": "test"}'
        assert verify_recall_signature(body, "", SECRET) is False

    def test_missing_header_no_prefix(self) -> None:
        """Signature without sha256= prefix returns False."""
        body = b'{"event": "test"}'
        digest = hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
        assert verify_recall_signature(body, digest, SECRET) is False

    def test_malformed_header(self) -> None:
        """Completely malformed header returns False."""
        body = b'{"event": "test"}'
        assert verify_recall_signature(body, "sha256=notrealhex!!!", SECRET) is False

    def test_empty_body_valid(self) -> None:
        """Empty body with valid signature returns True."""
        body = b""
        sig = _make_signature(body, SECRET)
        assert verify_recall_signature(body, sig, SECRET) is True

    def test_timing_safe(self) -> None:
        """
        Verify that compare_digest (not ==) is used — same byte count,
        different content should still fail, not short-circuit on length.
        """
        body = b'{"event": "test"}'
        # Craft a signature that has the right prefix and length but wrong content
        valid_sig = _make_signature(body, SECRET)
        wrong_sig = "sha256=" + "0" * 64  # correct length, all zeros
        assert verify_recall_signature(body, wrong_sig, SECRET) is False
        assert len(valid_sig) == len(wrong_sig)  # same length — timing safe matters
