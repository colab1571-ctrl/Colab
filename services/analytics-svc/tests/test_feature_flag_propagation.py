"""
analytics-svc / admin-svc integration — Feature flag live propagation test.

Verifies that a flag write in admin-svc propagates to PostHog within the
expected window (tested via mock — real propagation requires integration env).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestFeatureFlagPropagation:
    """
    Feature flag upsert should:
    1. Write to FeatureFlag table
    2. Call PostHog Personal API synchronously
    3. Fail the request (no DB commit) if PostHog call fails
    """

    @pytest.mark.asyncio
    async def test_flag_write_calls_posthog(self):
        """Successful flag write should mirror to PostHog."""
        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            # Import here so patch takes effect
            from app.routers.flags import _mirror_to_posthog

            with patch("app.routers.flags.get_settings") as mock_settings:
                settings = MagicMock()
                settings.posthog_api_key = "test-key"
                settings.posthog_project_id = "test-project"
                mock_settings.return_value = settings

                # Should not raise
                await _mirror_to_posthog("test.flag", "staging", True, 0)

            mock_client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_flag_write_fails_if_posthog_fails(self):
        """If PostHog mirror fails, HTTPException should be raised."""
        from fastapi import HTTPException

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "PostHog error"

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            from app.routers.flags import _mirror_to_posthog

            with patch("app.routers.flags.get_settings") as mock_settings:
                settings = MagicMock()
                settings.posthog_api_key = "test-key"
                settings.posthog_project_id = "test-project"
                mock_settings.return_value = settings

                with pytest.raises(HTTPException) as exc_info:
                    await _mirror_to_posthog("test.flag", "prod", True, 100)

                assert exc_info.value.status_code == 502

    def test_flag_not_mirrored_when_no_api_key(self):
        """If POSTHOG_API_KEY is not configured, mirror is skipped (dev/local)."""
        import asyncio
        from app.routers.flags import _mirror_to_posthog

        with patch("app.routers.flags.get_settings") as mock_settings:
            settings = MagicMock()
            settings.posthog_api_key = ""
            settings.posthog_project_id = ""
            mock_settings.return_value = settings

            # Should complete without making HTTP calls
            with patch("httpx.AsyncClient") as mock_client_cls:
                asyncio.run(_mirror_to_posthog("test.flag", "dev", True, 0))
                mock_client_cls.assert_not_called()
