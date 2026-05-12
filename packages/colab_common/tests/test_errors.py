"""Tests for colab_common.errors."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from colab_common.errors import (
    AppError,
    AuthError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    RateLimitError,
    ValidationError,
    register_handlers,
)


def _make_test_app() -> FastAPI:
    app = FastAPI()
    register_handlers(app)

    @app.get("/ok")
    async def ok_endpoint() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/auth-error")
    async def auth_error_endpoint() -> None:
        raise AuthError()

    @app.get("/not-found")
    async def not_found_endpoint() -> None:
        raise NotFoundError("User")

    @app.get("/rate-limit")
    async def rate_limit_endpoint() -> None:
        raise RateLimitError(retry_after=30)

    @app.get("/conflict")
    async def conflict_endpoint() -> None:
        raise ConflictError("Username taken.")

    return app


@pytest.fixture
def test_client() -> TestClient:
    app = _make_test_app()
    return TestClient(app, raise_server_exceptions=False)


def test_ok_endpoint(test_client: TestClient) -> None:
    resp = test_client.get("/ok")
    assert resp.status_code == 200


def test_auth_error_returns_401(test_client: TestClient) -> None:
    resp = test_client.get("/auth-error")
    assert resp.status_code == 401
    body = resp.json()
    assert body["error"]["code"] == "UNAUTHORIZED"


def test_not_found_returns_404(test_client: TestClient) -> None:
    resp = test_client.get("/not-found")
    assert resp.status_code == 404
    body = resp.json()
    assert body["error"]["code"] == "NOT_FOUND"
    assert "User" in body["error"]["message"]


def test_rate_limit_returns_429_with_retry_after(test_client: TestClient) -> None:
    resp = test_client.get("/rate-limit")
    assert resp.status_code == 429
    assert resp.headers.get("Retry-After") == "30"
    body = resp.json()
    assert body["error"]["code"] == "RATE_LIMIT_EXCEEDED"
    assert body["error"]["details"]["retry_after_seconds"] == 30


def test_conflict_returns_409(test_client: TestClient) -> None:
    resp = test_client.get("/conflict")
    assert resp.status_code == 409


def test_app_error_to_dict_includes_request_id() -> None:
    err = NotFoundError("Profile")
    d = err.to_dict(request_id="abc-123")
    assert d["error"]["request_id"] == "abc-123"
    assert d["error"]["code"] == "NOT_FOUND"


def test_error_hierarchy() -> None:
    assert issubclass(AuthError, AppError)
    assert issubclass(NotFoundError, AppError)
    assert issubclass(RateLimitError, AppError)
    assert issubclass(ValidationError, AppError)
    assert issubclass(ForbiddenError, AppError)
    assert issubclass(ConflictError, AppError)
