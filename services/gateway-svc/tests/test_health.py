"""Tests for gateway-svc health endpoints."""

import os

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("ENV", "local")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/1")


@pytest.fixture(scope="module")
def client() -> TestClient:
    from app.main import app

    return TestClient(app, raise_server_exceptions=False)


def test_healthz_returns_200(client: TestClient) -> None:
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_version_endpoint(client: TestClient) -> None:
    resp = client.get("/version")
    assert resp.status_code == 200
    data = resp.json()
    assert "service" in data
    assert data["service"] == "gateway-svc"


def test_flags_endpoint(client: TestClient) -> None:
    resp = client.get("/v1/flags")
    assert resp.status_code == 200
    data = resp.json()
    assert "ai_mockups_enabled" in data
    assert isinstance(data["region_allowlist"], list)


def test_request_id_in_response_headers(client: TestClient) -> None:
    resp = client.get("/healthz")
    assert "x-request-id" in resp.headers


def test_unknown_path_returns_404_or_503(client: TestClient) -> None:
    resp = client.get("/v1/nonexistent-service/foo")
    # 404 = no route found; 503 = route found but upstream not configured (expected in test)
    assert resp.status_code in (404, 503)
