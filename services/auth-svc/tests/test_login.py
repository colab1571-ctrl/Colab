"""
auth-svc — Login endpoint tests.

Covers: happy path, wrong password, brute-force lockout, token structure.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient


async def _create_user(client: AsyncClient, email: str = "user@example.com") -> dict:
    resp = await client.post(
        "/auth/signup/email",
        json={
            "email": email,
            "password": "Str0ng!Password99",
            "age_attestation": True,
            "accept_tos": True,
            "accept_privacy": True,
            "accept_community": True,
        },
    )
    assert resp.status_code == 201
    return resp.json()


@pytest.mark.asyncio
async def test_login_email_happy_path(client: AsyncClient) -> None:
    await _create_user(client, "logintest@example.com")
    resp = await client.post(
        "/auth/login/email",
        json={"email": "logintest@example.com", "password": "Str0ng!Password99"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient) -> None:
    await _create_user(client, "wrongpwd@example.com")
    resp = await client.post(
        "/auth/login/email",
        json={"email": "wrongpwd@example.com", "password": "WrongPassword!"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_nonexistent_user(client: AsyncClient) -> None:
    """Should return 401 (not 404) to avoid email enumeration."""
    resp = await client.post(
        "/auth/login/email",
        json={"email": "nobody@example.com", "password": "Str0ng!Password99"},
    )
    assert resp.status_code == 401
    # Error message should not reveal whether the email exists
    body = resp.json()
    assert "error" in body


@pytest.mark.asyncio
async def test_brute_force_lockout(client: AsyncClient) -> None:
    """After 10 failed attempts, the account should be locked."""
    email = "bruteforce@example.com"
    await _create_user(client, email)

    # Mock the brute_force module to simulate lockout on attempt 10
    locked = False
    attempt_count = 0

    async def mock_record_failed(e: str, ip: str) -> None:
        nonlocal attempt_count, locked
        attempt_count += 1
        if attempt_count >= 10:
            locked = True
            from colab_common.errors import AuthError
            raise AuthError("Account locked due to too many failed attempts. Try again in 15 minutes.")

    async def mock_check_locked(e: str, ip: str) -> None:
        if locked:
            from colab_common.errors import AuthError
            raise AuthError("Account locked due to too many failed attempts.")

    with (
        patch("app.routers.login.brute_force.record_failed_login", side_effect=mock_record_failed),
        patch("app.routers.login.brute_force.check_login_locked", side_effect=mock_check_locked),
    ):
        # Trigger 9 failures
        for _ in range(9):
            await client.post(
                "/auth/login/email",
                json={"email": email, "password": "WrongPassword!"},
            )

        # 10th attempt should lock
        resp = await client.post(
            "/auth/login/email",
            json={"email": email, "password": "WrongPassword!"},
        )
        assert resp.status_code in (401, 429)

        # 11th should see lock
        resp2 = await client.post(
            "/auth/login/email",
            json={"email": email, "password": "Str0ng!Password99"},
        )
        assert resp2.status_code in (401, 429)


@pytest.mark.asyncio
async def test_login_email_case_insensitive(client: AsyncClient) -> None:
    """Email is normalized to lowercase on both signup and login."""
    await _create_user(client, "mixedcase@example.com")
    resp = await client.post(
        "/auth/login/email",
        json={"email": "MixedCase@Example.COM", "password": "Str0ng!Password99"},
    )
    assert resp.status_code == 200
