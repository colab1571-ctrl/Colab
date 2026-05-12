"""
chat-svc — FastAPI application entry point.

Services:
- WebSocket gateway: wss://{domain}/chat/{room_id}
- REST API: rooms, messages, read receipts
- Internal audit endpoint
- RabbitMQ consumers: match.created, block.created, block.removed
- Redis pub/sub fanout for cross-pod broadcasting
"""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from colab_common.telemetry import init as telemetry_init

telemetry_init("chat-svc")

import uuid  # noqa: E402

import redis.asyncio as aioredis  # noqa: E402
from fastapi import Depends, FastAPI, WebSocket  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from colab_common.errors import register_handlers  # noqa: E402
from colab_common.settings import get_settings  # noqa: E402
from colab_common.telemetry import RequestIDMiddleware  # noqa: E402

from app.config import get_chat_settings  # noqa: E402
from app.db import get_db  # noqa: E402
from app.routers.rooms import router as rooms_router  # noqa: E402
from app.routers.rooms import internal_router  # noqa: E402
from app.ws.connection_manager import AsyncConnectionManager  # noqa: E402
from app.ws.handler import handle_room_ws  # noqa: E402
from app.ws.presence import AsyncPresenceManager  # noqa: E402

settings = get_settings()
chat_settings = get_chat_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    # Redis client
    redis_client = aioredis.from_url(
        chat_settings.redis_url,
        decode_responses=True,
        max_connections=50,
    )
    presence = AsyncPresenceManager(redis_client)
    conn_mgr = AsyncConnectionManager()

    _app.state.presence = presence
    _app.state.conn_mgr = conn_mgr
    _app.state.redis = redis_client

    # Start RabbitMQ consumers in background (graceful — don't block startup if MQ unavailable)
    consumer_task = None
    try:
        from app.workers.event_consumers import start_consumers
        consumer_task = asyncio.ensure_future(start_consumers(presence))
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("RabbitMQ consumer startup failed: %s", exc)

    yield

    if consumer_task:
        consumer_task.cancel()
    await redis_client.aclose()


app = FastAPI(
    title="Colab Chat Service",
    version="0.1.0",
    description=(
        "WebSocket-backed 1:1 real-time chat, message persistence, "
        "presence, read receipts, moderation integration."
    ),
    lifespan=lifespan,
    docs_url="/docs" if os.environ.get("ENV", "local") in ("local", "dev") else None,
    redoc_url="/redoc" if os.environ.get("ENV", "local") in ("local", "dev") else None,
)

register_handlers(app)
app.add_middleware(RequestIDMiddleware)

# REST routers
app.include_router(rooms_router)
app.include_router(internal_router)


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------


@app.websocket("/chat/{room_id}")
async def ws_chat(
    websocket: WebSocket,
    room_id: uuid.UUID,
    token: str = "",
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    WebSocket endpoint: wss://api.<domain>/chat/{room_id}?token=<jwt>

    Token validation is performed by API Gateway Lambda authorizer before
    the upgrade reaches this handler. The profile_id is injected via the
    X-Profile-Id header by the authorizer / gateway.
    """
    profile_id_str = websocket.headers.get("X-Profile-Id") or websocket.query_params.get("profile_id", "")
    if not profile_id_str:
        await websocket.close(code=4001)
        return
    try:
        profile_id = uuid.UUID(profile_id_str)
    except ValueError:
        await websocket.close(code=4001)
        return

    await handle_room_ws(
        ws=websocket,
        room_id=room_id,
        profile_id=profile_id,
        db=db,
        presence=websocket.app.state.presence,
        conn_mgr=websocket.app.state.conn_mgr,
    )


@app.get("/healthz", include_in_schema=False)
async def healthz() -> dict[str, str]:
    return {"status": "ok", "service": "chat-svc"}
