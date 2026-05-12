"""Tests for colab_common.telemetry."""

import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from colab_common.telemetry import RequestIDMiddleware, request_id_var


def _make_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestIDMiddleware)

    @app.get("/ping")
    async def ping() -> dict[str, str]:
        return {"request_id": request_id_var.get("")}

    return app


@pytest.fixture
def app_client() -> TestClient:
    return TestClient(_make_app())


def test_request_id_injected_in_response(app_client: TestClient) -> None:
    resp = app_client.get("/ping")
    assert resp.status_code == 200
    assert "X-Request-Id" in resp.headers
    rid = resp.headers["X-Request-Id"]
    # UUID4 format
    uuid.UUID(rid)  # raises ValueError if not valid UUID


def test_incoming_request_id_honoured(app_client: TestClient) -> None:
    custom_id = "my-custom-request-id-123"
    resp = app_client.get("/ping", headers={"X-Request-Id": custom_id})
    assert resp.headers.get("X-Request-Id") == custom_id
    # The endpoint also returns it from the ContextVar
    assert resp.json()["request_id"] == custom_id


def test_request_id_propagated_to_handler(app_client: TestClient) -> None:
    resp = app_client.get("/ping")
    rid_from_header = resp.headers["X-Request-Id"]
    rid_from_body = resp.json()["request_id"]
    assert rid_from_header == rid_from_body
