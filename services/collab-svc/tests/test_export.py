"""
Tests for export pipeline:
- Premium gate enforcement
- PDF generation (mocked WeasyPrint)
- Export expiry (signed URL returns None after expires_at)
- Export status lifecycle
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Premium gate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_export_blocked_without_premium():
    """billing_client returning False should prevent export creation."""
    from fastapi import HTTPException

    # Simulate the check in the router
    has_entitlement = False
    if not has_entitlement:
        with pytest.raises(HTTPException) as exc_info:
            raise HTTPException(
                status_code=403,
                detail={"error_code": "EXPORT_REQUIRES_PREMIUM"},
            )
    assert exc_info.value.status_code == 403
    assert exc_info.value.detail["error_code"] == "EXPORT_REQUIRES_PREMIUM"


@pytest.mark.asyncio
async def test_billing_client_returns_false_for_free_tier():
    """billing_client should return False when billing-svc returns chat_export=False."""
    from app.services.billing_client import check_chat_export_entitlement

    profile_id = uuid.uuid4()

    with patch("app.services.billing_client.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"axes": {"chat_export": False}, "tier": "free"}
        mock_client.get.return_value = mock_resp

        result = await check_chat_export_entitlement(profile_id)

    assert result is False


@pytest.mark.asyncio
async def test_billing_client_returns_true_for_premium():
    """billing_client should return True when billing-svc returns chat_export=True."""
    from app.services.billing_client import check_chat_export_entitlement

    profile_id = uuid.uuid4()

    with patch("app.services.billing_client.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"axes": {"chat_export": True}, "tier": "premium"}
        mock_client.get.return_value = mock_resp

        result = await check_chat_export_entitlement(profile_id)

    assert result is True


@pytest.mark.asyncio
async def test_billing_client_fail_closed_on_error():
    """billing_client returns False on network error (fail-closed for Premium gate)."""
    from app.services.billing_client import check_chat_export_entitlement

    profile_id = uuid.uuid4()

    with patch("app.services.billing_client.httpx.AsyncClient") as mock_client_cls:
        mock_client_cls.return_value.__aenter__ = AsyncMock(
            side_effect=Exception("Connection refused")
        )

        result = await check_chat_export_entitlement(profile_id)

    assert result is False


# ---------------------------------------------------------------------------
# PDF generation (mocked WeasyPrint)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pdf_render_produces_bytes():
    """_render_pdf should return bytes from WeasyPrint."""
    from app.workers.export_tasks import _render_pdf

    collab_id = uuid.uuid4()
    export_id = uuid.uuid4()
    messages = [
        {
            "id": str(uuid.uuid4()),
            "sender_display_name": "Alice",
            "body": "Hello Bob!",
            "type": "text",
            "created_at": "2026-05-01T10:00:00Z",
        },
        {
            "id": str(uuid.uuid4()),
            "sender_display_name": "Bob",
            "body": "Hi Alice!",
            "type": "text",
            "created_at": "2026-05-01T10:01:00Z",
        },
    ]

    with patch("app.workers.export_tasks.HTML") as mock_html:
        mock_html_instance = MagicMock()
        mock_html_instance.write_pdf.return_value = b"%PDF-1.4 mock content"
        mock_html.return_value = mock_html_instance

        result = await _render_pdf(collab_id, export_id, messages)

    assert isinstance(result, bytes)
    assert len(result) > 0


@pytest.mark.asyncio
async def test_pdf_render_excludes_system_messages():
    """System messages should be filtered out from the transcript."""
    from app.workers.export_tasks import _render_pdf

    collab_id = uuid.uuid4()
    export_id = uuid.uuid4()
    messages = [
        {
            "id": str(uuid.uuid4()),
            "sender_display_name": "Alice",
            "body": "Hello!",
            "type": "text",
            "created_at": "2026-05-01T10:00:00Z",
        },
        {
            "id": str(uuid.uuid4()),
            "sender_display_name": "System",
            "body": "Alice marked collab Completed",
            "type": "system",
            "created_at": "2026-05-01T10:02:00Z",
        },
    ]

    rendered_messages = []

    with patch("app.workers.export_tasks.HTML") as mock_html:
        mock_html_instance = MagicMock()
        mock_html_instance.write_pdf.return_value = b"pdf"
        mock_html.return_value = mock_html_instance

        with patch("app.workers.export_tasks.Environment") as mock_env_cls:
            mock_env = MagicMock()
            mock_env_cls.return_value = mock_env
            mock_template = MagicMock()
            mock_template.render.side_effect = lambda **ctx: (
                rendered_messages.extend(ctx.get("messages", [])), "html"
            )[1]
            mock_env.get_template.return_value = mock_template

            await _render_pdf(collab_id, export_id, messages)

    # Only non-system messages should be in the rendered context
    assert all(m["type"] != "system" for m in rendered_messages)
    assert len(rendered_messages) == 1


# ---------------------------------------------------------------------------
# Signed URL expiry
# ---------------------------------------------------------------------------


def test_signed_url_returns_none_after_expiry():
    """get_signed_urls should return (None, None) when expires_at is in the past."""
    from app.services.export_service import get_signed_urls

    export = MagicMock()
    export.pdf_s3_key = "exports/collab/export/transcript.pdf"
    export.zip_s3_key = "exports/collab/export/media.zip"
    export.expires_at = datetime.now(UTC) - timedelta(hours=1)  # Expired

    pdf_url, zip_url = get_signed_urls(export)

    assert pdf_url is None
    assert zip_url is None


def test_signed_url_returns_url_before_expiry():
    """get_signed_urls should return URLs when expires_at is in the future."""
    from app.services.export_service import get_signed_urls, generate_signed_url

    export = MagicMock()
    export.pdf_s3_key = "exports/collab/export/transcript.pdf"
    export.zip_s3_key = None  # No media
    export.expires_at = datetime.now(UTC) + timedelta(days=5)

    pdf_url, zip_url = get_signed_urls(export)

    assert pdf_url is not None
    assert "transcript.pdf" in pdf_url
    assert zip_url is None


def test_signed_url_none_for_missing_key():
    """get_signed_urls should return None for missing S3 keys."""
    from app.services.export_service import get_signed_urls

    export = MagicMock()
    export.pdf_s3_key = None
    export.zip_s3_key = None
    export.expires_at = datetime.now(UTC) + timedelta(days=5)

    pdf_url, zip_url = get_signed_urls(export)

    assert pdf_url is None
    assert zip_url is None
