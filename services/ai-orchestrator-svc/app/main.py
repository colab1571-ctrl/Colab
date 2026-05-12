"""
ai-orchestrator-svc — FastAPI application entry point.

Services:
- POST /ai/chat/{room_id}/command — 5 in-chat AI commands (Premium-only)
- POST /collabs/{id}/mockup/consent — bilateral AI Collab Preview consent
- GET  /collabs/{id}/mockups — list mockup assets (participant-only)
- POST /webhooks/replicate — Replicate prediction webhook (HMAC-signed)
- POST /ai/mockups/{asset_id}/screenshot-event — iOS screenshot audit
- Celery workers + Beat for lifespan expiry
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from colab_common.telemetry import init as telemetry_init

telemetry_init("ai-orchestrator-svc")

import httpx  # noqa: E402
import redis.asyncio as aioredis  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker  # noqa: E402

from colab_common.errors import register_handlers  # noqa: E402
from colab_common.telemetry import RequestIDMiddleware  # noqa: E402

from app.config import get_ai_settings  # noqa: E402
from app.db import _get_engine  # noqa: E402
from app.routers.commands import router as commands_router  # noqa: E402
from app.routers.consent import router as consent_router  # noqa: E402
from app.routers.webhooks import router as webhooks_router  # noqa: E402

logger = logging.getLogger(__name__)
settings = get_ai_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # HTTP client for internal service calls
    app.state.http = httpx.AsyncClient(
        timeout=httpx.Timeout(10.0, connect=5.0),
        limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
    )

    # Redis
    app.state.redis = aioredis.from_url(
        settings.redis_url,
        decode_responses=True,
        max_connections=20,
    )

    # DB session factory (for webhook handler — not using FastAPI Depends)
    from sqlalchemy.ext.asyncio import AsyncSession
    app.state.db_session_factory = async_sessionmaker(
        _get_engine(),
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )

    logger.info("ai-orchestrator-svc started")
    yield

    await app.state.http.aclose()
    await app.state.redis.aclose()
    logger.info("ai-orchestrator-svc shutdown")


app = FastAPI(
    title="Colab AI Orchestrator Service",
    version="0.1.0",
    description=(
        "Premium-gated AI surfaces: 5 in-chat commands, AI Collab Preview mockup generation, "
        "Replicate webhook orchestration, credit-wallet metering, screenshot audit."
    ),
    lifespan=lifespan,
    docs_url="/docs" if os.environ.get("ENV", "local") in ("local", "dev") else None,
    redoc_url="/redoc" if os.environ.get("ENV", "local") in ("local", "dev") else None,
)

register_handlers(app)
app.add_middleware(RequestIDMiddleware)

# Routers
app.include_router(commands_router)
app.include_router(consent_router)
app.include_router(webhooks_router)


@app.get("/healthz", include_in_schema=False)
async def healthz() -> dict[str, str]:
    return {"status": "ok", "service": "ai-orchestrator-svc"}
