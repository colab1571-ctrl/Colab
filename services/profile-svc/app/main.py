"""
profile-svc — FastAPI application entrypoint.

Implements all profile FRs:
  - Profile CRUD (FR-A-4)
  - Portfolio upload via presigned S3 (FR-A-6)
  - AI profile review pipeline (FR-A-10)
  - Valid Profile Badge state machine (FR-A-11)
  - Personality quiz (FR-A-8)
  - External OAuth links: IG/YouTube/Spotify (FR-A-5)
  - Profile health score (40/30/30 weights)
  - Nightly Celery Beat + event consumer
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from colab_common.errors import register_handlers
from colab_common.settings import get_settings as get_common_settings
from colab_common.telemetry import RequestIDMiddleware
from colab_common.telemetry import init as telemetry_init

telemetry_init("profile-svc")

from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.routers.badge import router as badge_router  # noqa: E402
from app.routers.events import start_consumer  # noqa: E402
from app.routers.internal import router as internal_router  # noqa: E402
from app.routers.oauth import router as oauth_router  # noqa: E402
from app.routers.portfolio import router as portfolio_router  # noqa: E402
from app.routers.profile import router as profile_router  # noqa: E402
from app.routers.vocations import router as vocations_router, taxonomy_router  # noqa: E402

settings = get_settings()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    # Start RabbitMQ event consumer in background
    consumer_task = asyncio.create_task(
        start_consumer(settings.rabbitmq_url),
        name="profile-svc-event-consumer",
    )
    logger.info("profile-svc started; event consumer running")
    try:
        yield
    finally:
        consumer_task.cancel()
        try:
            await consumer_task
        except asyncio.CancelledError:
            pass


app = FastAPI(
    title="Colab Profile Service",
    version="1.0.0",
    description=(
        "Profile CRUD, portfolio management, vocations, personality quiz, "
        "OAuth provider linking, AI profile review, Valid Profile Badge state machine."
    ),
    lifespan=lifespan,
    docs_url="/docs" if settings.is_development else None,
    redoc_url="/redoc" if settings.is_development else None,
)

register_handlers(app)
app.add_middleware(RequestIDMiddleware)

# Routers
app.include_router(profile_router)
app.include_router(portfolio_router)
app.include_router(vocations_router)
app.include_router(taxonomy_router)
app.include_router(badge_router)
app.include_router(oauth_router)
app.include_router(internal_router)


@app.get("/healthz", include_in_schema=False)
async def healthz() -> dict[str, str]:
    return {"status": "ok", "service": "profile-svc"}


@app.get("/version", include_in_schema=False)
async def version() -> dict[str, str]:
    import os
    return {
        "service": "profile-svc",
        "version": "1.0.0",
        "git_sha": os.environ.get("GIT_SHA", "dev"),
    }
