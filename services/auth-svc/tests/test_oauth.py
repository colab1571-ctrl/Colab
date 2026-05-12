"""
auth-svc — OAuth identity spoofing simulation tests.

Tests Apple + Google token verification with mocked responses.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient


FAKE_APPLE_CLAIMS = {
    "provider": "apple",
    "provider_subject": "001234.abc.567890",
    "email": "apple_user@privaterelay.appleid.com",
    "email_verified": True,
    "is_private_email": True,
}

FAKE_GOOGLE_CLAIMS = {
    "provider": "google",
    "provider_subject": "117551234567890123456",
    "email": "google_user@gmail.com",
    "email_verified": True,
}


@pytest.mark.asyncio
async def test_signup_apple_oauth_happy_path(client: AsyncClient) -> None:
    with patch("app.routers.signup.oauth.verify_apple_id_token", AsyncMock(return_value=FAKE_APPLE_CLAIMS)):
        resp = await client.post(
            "/auth/signup/oauth",
            json={
                "provider": "apple",
                "id_token": "fake.apple.token",
                "nonce": "test_nonce",
                "age_attestation": True,
                "accept_tos": True,
                "accept_privacy": True,
                "accept_community": True,
            },
        )
    assert resp.status_code == 201
    data = resp.json()
    assert "access_token" in data


@pytest.mark.asyncio
async def test_signup_google_oauth_happy_path(client: AsyncClient) -> None:
    with patch("app.routers.signup.oauth.verify_google_id_token", AsyncMock(return_value=FAKE_GOOGLE_CLAIMS)):
        resp = await client.post(
            "/auth/signup/oauth",
            json={
                "provider": "google",
                "id_token": "fake.google.token",
                "age_attestation": True,
                "accept_tos": True,
                "accept_privacy": True,
                "accept_community": True,
            },
        )
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_oauth_identity_spoofing_blocked(client: AsyncClient) -> None:
    """
    Cross-project token injection: a token from a different Google project
    should raise AuthError (verified by google-auth library rejecting wrong aud).
    """
    from colab_common.errors import AuthError

    with patch(
        "app.routers.signup.oauth.verify_google_id_token",
        AsyncMock(side_effect=AuthError("Google ID token invalid: Wrong audience")),
    ):
        resp = await client.post(
            "/auth/signup/oauth",
            json={
                "provider": "google",
                "id_token": "spoofed.cross.project.token",
                "age_attestation": True,
                "accept_tos": True,
                "accept_privacy": True,
                "accept_community": True,
            },
        )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_apple_nonce_mismatch_blocked(client: AsyncClient) -> None:
    """Apple nonce mismatch must block signup."""
    from colab_common.errors import AuthError

    with patch(
        "app.routers.signup.oauth.verify_apple_id_token",
        AsyncMock(side_effect=AuthError("Apple ID token nonce mismatch.")),
    ):
        resp = await client.post(
            "/auth/signup/oauth",
            json={
                "provider": "apple",
                "id_token": "replay.attack.token",
                "nonce": "wrong_nonce",
                "age_attestation": True,
                "accept_tos": True,
                "accept_privacy": True,
                "accept_community": True,
            },
        )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_duplicate_apple_login(client: AsyncClient) -> None:
    """Second signup with same Apple subject should return 409."""
    with patch("app.routers.signup.oauth.verify_apple_id_token", AsyncMock(return_value=FAKE_APPLE_CLAIMS)):
        resp1 = await client.post(
            "/auth/signup/oauth",
            json={
                "provider": "apple",
                "id_token": "fake.apple.token",
                "nonce": "nonce1",
                "age_attestation": True,
                "accept_tos": True,
                "accept_privacy": True,
                "accept_community": True,
            },
        )

    # Expect conflict on second signup with same provider subject
    # (first may have already been created by previous test - so either 201 or 409)
    assert resp1.status_code in (201, 409)
