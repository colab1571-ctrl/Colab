"""
support-svc — FastAPI application entry point.

Endpoints:
  GET  /v1/support/faq              list FAQ articles (public)
  GET  /v1/support/faq/{slug}       single article (public)
  POST /v1/support/chatbot          AI chatbot w/ FAQ retrieval (SSE)
  POST /v1/support/tickets          create ticket
  GET  /v1/support/tickets          list user tickets
  GET  /v1/support/tickets/{id}     ticket detail
  POST /v1/support/tickets/{id}/reply   add reply
  POST /v1/support/tickets/{id}/csat    submit CSAT
  GET  /v1/support/status           outage status (public)
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from colab_common.telemetry import init as telemetry_init

telemetry_init("support-svc")

from fastapi import FastAPI  # noqa: E402
from colab_common.errors import register_handlers  # noqa: E402
from colab_common.settings import get_settings  # noqa: E402
from colab_common.telemetry import RequestIDMiddleware  # noqa: E402

from app.routers.faq import router as faq_router  # noqa: E402
from app.routers.chatbot import router as chatbot_router  # noqa: E402
from app.routers.tickets import router as tickets_router  # noqa: E402
from app.routers.status import router as status_router  # noqa: E402

settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    # Register beat schedule on startup so tasks are visible to workers
    import app.workers.beat_schedule  # noqa: F401
    yield


app = FastAPI(
    title="Colab Support Service",
    version="0.1.0",
    description=(
        "FAQ retrieval via pgvector, AI chatbot (GPT-4o, bounded to FAQ + ticket creation), "
        "support ticket management with SLA timers, CSAT, and live status page."
    ),
    lifespan=lifespan,
    docs_url="/docs" if settings.is_development else None,
    redoc_url="/redoc" if settings.is_development else None,
)

register_handlers(app)
app.add_middleware(RequestIDMiddleware)

app.include_router(faq_router)
app.include_router(chatbot_router)
app.include_router(tickets_router)
app.include_router(status_router)


@app.get("/healthz", include_in_schema=False)
async def healthz() -> dict[str, str]:
    return {"status": "ok", "service": "support-svc"}
