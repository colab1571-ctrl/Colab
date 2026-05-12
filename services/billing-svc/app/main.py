"""
billing-svc — FastAPI application entrypoint.

Implements billing endpoints per spec 013:
  - Entitlements (Redis-cached, event-invalidated)
  - Subscriptions (Stripe web + RevenueCat mobile)
  - Credit wallet (pessimistic reserve/commit/release)
  - Dunning state machine (Celery Beat)
  - Refunds (14d auto-approve + mobile routing)
  - Webhooks: Stripe (HMAC) + RevenueCat (bearer)
  - Internal service-to-service endpoints
  - Admin endpoints
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import aio_pika
import redis.asyncio as aioredis
import stripe

from colab_common.telemetry import init as telemetry_init

telemetry_init("billing-svc")

from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

from app.routers import admin, billing, internal, webhooks  # noqa: E402
from colab_common.errors import register_handlers  # noqa: E402
from colab_common.idempotency import IdempotencyMiddleware  # noqa: E402
from colab_common.settings import get_settings  # noqa: E402
from colab_common.telemetry import RequestIDMiddleware  # noqa: E402

logger = logging.getLogger(__name__)
settings = get_settings()

# Configure Stripe SDK
stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "")
stripe.api_version = os.environ.get("STRIPE_API_VERSION", "2025-10-29")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # Redis connection
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    app.state.redis = aioredis.from_url(redis_url, decode_responses=True)

    # RabbitMQ connection
    amqp_url = os.environ.get("AMQP_URL", "amqp://guest:guest@localhost/")
    connection = await aio_pika.connect_robust(amqp_url)
    channel = await connection.channel()
    app.state.amqp_channel = channel
    app.state.amqp_connection = connection

    logger.info("billing-svc started — Stripe API version: %s", stripe.api_version)
    yield

    await connection.close()
    await app.state.redis.aclose()


app = FastAPI(
    title="Colab Billing Service",
    version="1.0.0",
    description="Subscriptions, entitlements, credits, dunning, refunds, tax.",
    lifespan=lifespan,
    docs_url="/docs" if os.environ.get("ENV", "production") != "production" else None,
    redoc_url="/redoc" if os.environ.get("ENV", "production") != "production" else None,
)

register_handlers(app)
app.add_middleware(RequestIDMiddleware)
app.add_middleware(IdempotencyMiddleware)

# Routers
app.include_router(billing.router)
app.include_router(webhooks.router)
app.include_router(internal.router)
app.include_router(admin.router)


@app.get("/healthz", include_in_schema=False)
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/version", include_in_schema=False)
async def version() -> dict[str, str]:
    return {
        "service": "billing-svc",
        "version": "1.0.0",
        "git_sha": os.environ.get("GIT_SHA", "dev"),
        "stripe_api_version": stripe.api_version,
    }
