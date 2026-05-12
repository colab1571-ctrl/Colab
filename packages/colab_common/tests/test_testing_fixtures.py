"""Tests for colab_common.testing (self-test of the testing helpers)."""

import time

import jwt
import pytest

from colab_common.testing import AuthUserFactory, mint_jwt


def test_mint_jwt_returns_valid_token() -> None:
    token = mint_jwt(user_id="u1", email="u1@test.com", roles=["user"])
    payload = jwt.decode(token, "test-secret", algorithms=["HS256"])
    assert payload["sub"] == "u1"
    assert payload["email"] == "u1@test.com"
    assert "user" in payload["roles"]


def test_mint_jwt_expiry() -> None:
    token = mint_jwt(ttl_seconds=3600)
    payload = jwt.decode(token, "test-secret", algorithms=["HS256"])
    now = int(time.time())
    assert payload["exp"] > now
    assert payload["exp"] <= now + 3601


def test_auth_user_factory_default_role() -> None:
    factory = AuthUserFactory()
    token = factory()
    payload = jwt.decode(token, "test-secret", algorithms=["HS256"])
    assert "user" in payload["roles"]


def test_auth_user_factory_admin_role() -> None:
    factory = AuthUserFactory()
    token = factory(role="admin")
    payload = jwt.decode(token, "test-secret", algorithms=["HS256"])
    assert "admin" in payload["roles"]
    assert "moderator" in payload["roles"]


def test_auth_user_factory_moderator_role() -> None:
    factory = AuthUserFactory()
    token = factory(role="moderator")
    payload = jwt.decode(token, "test-secret", algorithms=["HS256"])
    assert "moderator" in payload["roles"]
    assert "admin" not in payload["roles"]
