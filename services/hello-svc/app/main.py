"""
hello-svc — Minimal sample service proving the gateway pattern end-to-end.

Demonstrates:
- colab_common.telemetry init
- colab_common.errors handler
- request_id propagation
- Reading a test secret from env (via ExternalSecret in Helm)
- Structured JSON logging via structlog
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

# Init telemetry before FastAPI import
from colab_common.telemetry import init as telemetry_init

telemetry_init("hello-svc")

from fastapi import FastAPI, Request  # noqa: E402

from colab_common.errors import register_handlers  # noqa: E402
from colab_common.settings import get_settings  # noqa: E402
from colab_common.telemetry import RequestIDMiddleware, request_id_var  # noqa: E402

settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    yield


app = FastAPI(
    title="Colab Hello Service",
    version="0.1.0",
    description="Sample service proving the colab_common pattern end-to-end.",
    lifespan=lifespan,
    docs_url="/docs" if settings.is_development else None,
)

register_handlers(app)
app.add_middleware(RequestIDMiddleware)


@app.get("/healthz", include_in_schema=False)
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/hello")
async def hello(request: Request) -> dict[str, object]:
    """
    Returns a greeting with env info and request_id.
    Reads HELLO_SECRET from env (set via ExternalSecret in Helm).
    Includes secret_present flag (never the actual value).
    """
    secret = os.environ.get("HELLO_SECRET", "")
    return {
        "msg": f"Hello, {settings.brand_name}",
        "env": settings.env,
        "request_id": request_id_var.get(""),
        "service": "hello-svc",
        "secret_present": bool(secret),
    }
