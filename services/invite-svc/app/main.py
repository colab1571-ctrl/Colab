"""
invite-svc — FastAPI application entrypoint.

Implements Vibe Check FRs:
  - Send Vibe Check (FR-B-8): 250-char synopsis, pre-send moderation
  - Free 5/wk quota via Redis Sorted Set + Lua (FR-B-8)
  - Premium unlimited via billing-svc entitlements (FR-B-8)
  - Accept/reject/cancel lifecycle (FR-B-9)
  - 30-day TTL → archived (FR-B-10)
  - Mutual accept → match.created event (FR-B-13)
  - Block table CRUD + reciprocal enforcement
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from colab_common.telemetry import RequestIDMiddleware
from colab_common.telemetry import init as telemetry_init

telemetry_init("invite-svc")

import aio_pika  # noqa: E402
import redis.asyncio as aioredis  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.routers.blocks import router as blocks_router  # noqa: E402
from app.routers.events import start_consumer  # noqa: E402
from app.routers.invites import router as invites_router  # noqa: E402

settings = get_settings()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    # Redis client
    redis = aioredis.from_url(settings.redis_url, decode_responses=False)
    _app.state.redis = redis

    # RabbitMQ connection + channel (shared, persistent)
    amqp_connection = await aio_pika.connect_robust(settings.rabbitmq_url)
    amqp_channel = await amqp_connection.channel()
    _app.state.amqp_channel = amqp_channel
    _app.state.amqp_connection = amqp_connection

    # Event consumer (entitlement.changed invalidation)
    consumer_task = asyncio.create_task(
        start_consumer(settings.rabbitmq_url, redis),
        name="invite-svc-event-consumer",
    )
    logger.info("invite-svc started; event consumer running")

    try:
        yield
    finally:
        consumer_task.cancel()
        try:
            await consumer_task
        except asyncio.CancelledError:
            pass

        await amqp_connection.close()
        await redis.aclose()


app = FastAPI(
    title="Colab Invite Service",
    version="1.0.0",
    description=(
        "Vibe Check invite lifecycle: send, accept, reject, cancel, "
        "30-day TTL archival, mutual match emission, block management."
    ),
    lifespan=lifespan,
    docs_url="/docs" if settings.is_development else None,
    redoc_url="/redoc" if settings.is_development else None,
)

# Auth middleware would be injected here in production (JWT → request.state.profile_id)
# For now: colab_common.auth middleware is assumed wired by the API gateway
app.add_middleware(RequestIDMiddleware)

# Routers
app.include_router(invites_router)
app.include_router(blocks_router)


@app.get("/healthz", include_in_schema=False)
async def healthz() -> dict[str, str]:
    return {"status": "ok", "service": "invite-svc"}


@app.get("/version", include_in_schema=False)
async def version() -> dict[str, str]:
    import os
    return {
        "service": "invite-svc",
        "version": "1.0.0",
        "git_sha": os.environ.get("GIT_SHA", "dev"),
    }
