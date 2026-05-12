"""
identity-svc — FastAPI application entrypoint.

Implements:
  POST /identity/inquiry/start
  GET  /identity/verification
  POST /webhooks/persona/inquiry (HMAC-signed)
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from colab_common.telemetry import init as telemetry_init

telemetry_init("identity-svc")

from fastapi import FastAPI  # noqa: E402

from app.routers import identity, webhook  # noqa: E402
from colab_common.errors import register_handlers  # noqa: E402
from colab_common.settings import get_settings  # noqa: E402
from colab_common.telemetry import RequestIDMiddleware  # noqa: E402

settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    yield


app = FastAPI(
    title="Colab Identity Service",
    version="1.0.0",
    description="Persona-driven selfie/liveness verification + IdentityVerification state.",
    lifespan=lifespan,
    docs_url="/docs" if settings.is_development else None,
    redoc_url="/redoc" if settings.is_development else None,
)

register_handlers(app)
app.add_middleware(RequestIDMiddleware)

app.include_router(identity.router)
app.include_router(webhook.router)


@app.get("/healthz", include_in_schema=False)
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/version", include_in_schema=False)
async def version() -> dict[str, str]:
    import os

    return {
        "service": "identity-svc",
        "version": "1.0.0",
        "git_sha": os.environ.get("GIT_SHA", "dev"),
    }
