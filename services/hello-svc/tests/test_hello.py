"""Tests for hello-svc."""

import os

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("ENV", "local")
os.environ.setdefault("BRAND_NAME", "Colab")


@pytest.fixture(scope="module")
def client() -> TestClient:
    from app.main import app

    return TestClient(app)


def test_healthz(client: TestClient) -> None:
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_hello_returns_200(client: TestClient) -> None:
    resp = client.get("/hello")
    assert resp.status_code == 200
    data = resp.json()
    assert "msg" in data
    assert "Colab" in data["msg"]


def test_hello_includes_env(client: TestClient) -> None:
    resp = client.get("/hello")
    data = resp.json()
    assert data["env"] == "local"


def test_hello_includes_request_id(client: TestClient) -> None:
    resp = client.get("/hello", headers={"X-Request-Id": "test-req-id"})
    data = resp.json()
    assert data["request_id"] == "test-req-id"


def test_hello_secret_present_false_by_default(client: TestClient) -> None:
    resp = client.get("/hello")
    data = resp.json()
    assert data["secret_present"] is False


def test_hello_secret_present_true_when_env_set(client: TestClient) -> None:
    os.environ["HELLO_SECRET"] = "my-test-secret"
    resp = client.get("/hello")
    data = resp.json()
    assert data["secret_present"] is True
    # Never return the actual secret value
    assert "my-test-secret" not in str(data)
    del os.environ["HELLO_SECRET"]


def test_request_id_in_response_header(client: TestClient) -> None:
    resp = client.get("/hello")
    assert "x-request-id" in resp.headers
