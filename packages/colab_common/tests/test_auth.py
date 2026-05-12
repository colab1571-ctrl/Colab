"""Tests for colab_common.auth."""

import time

import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from colab_common.auth import AuthUser, mint_jwt, mint_service_token, require_role, require_user
from colab_common.errors import AuthError, ForbiddenError, register_handlers
from colab_common.testing import mint_jwt


def _make_token(
    user_id: str = "u1",
    roles: list[str] | None = None,
    tier: str = "free",
    expired: bool = False,
    secret: str = "test-secret",
) -> str:
    now = int(time.time())
    exp = now - 10 if expired else now + 3600
    payload = {
        "sub": user_id,
        "email": f"{user_id}@test.com",
        "roles": roles or ["user"],
        "tier": tier,
        "iat": now,
        "exp": exp,
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def _make_app() -> FastAPI:
    from colab_common.settings import get_settings

    get_settings.cache_clear()  # type: ignore[attr-defined]
    app = FastAPI()
    register_handlers(app)

    @app.get("/me")
    async def me_endpoint(user: AuthUser = require_user) -> dict[str, str]:  # type: ignore[assignment]
        return {"user_id": user.user_id, "tier": user.tier}

    @app.get("/admin-only")
    async def admin_endpoint(user: AuthUser = require_role("admin")) -> dict[str, str]:  # type: ignore[assignment]
        return {"user_id": user.user_id}

    return app


@pytest.fixture
def app_client() -> TestClient:
    return TestClient(_make_app(), raise_server_exceptions=False)


def test_require_user_with_valid_token(app_client: TestClient) -> None:
    token = _make_token()
    resp = app_client.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["user_id"] == "u1"


def test_require_user_without_token_returns_401(app_client: TestClient) -> None:
    resp = app_client.get("/me")
    assert resp.status_code == 401


def test_require_user_expired_token_returns_401(app_client: TestClient) -> None:
    token = _make_token(expired=True)
    resp = app_client.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


def test_require_role_admin_allowed(app_client: TestClient) -> None:
    token = _make_token(roles=["admin", "user"])
    resp = app_client.get("/admin-only", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200


def test_require_role_user_forbidden(app_client: TestClient) -> None:
    token = _make_token(roles=["user"])
    resp = app_client.get("/admin-only", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403


def test_auth_user_is_admin() -> None:
    u = AuthUser(user_id="x", email="x@t.com", roles=["admin"])
    assert u.is_admin is True
    assert u.is_moderator is True


def test_auth_user_is_moderator() -> None:
    u = AuthUser(user_id="x", email="x@t.com", roles=["moderator"])
    assert u.is_moderator is True
    assert u.is_admin is False


def test_mint_service_token_decodes() -> None:
    token = mint_service_token(source_service="gateway-svc", target_service="hello-svc")
    payload = jwt.decode(token, "test-secret", algorithms=["HS256"], options={"verify_aud": False})
    assert payload["sub"] == "svc:gateway-svc"
    assert payload["roles"] == ["service"]
