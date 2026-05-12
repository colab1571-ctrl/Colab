"""
gateway-svc — Colab API Gateway
================================

IMPORTANT: Import telemetry.init() before FastAPI to avoid double-instrumentation.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

# 1. Init telemetry BEFORE FastAPI import
from colab_common.telemetry import init as telemetry_init

telemetry_init("gateway-svc")

from fastapi import FastAPI, Request  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

from colab_common.errors import register_handlers  # noqa: E402
from colab_common.idempotency import IdempotencyMiddleware  # noqa: E402
from colab_common.rate_limit import RateLimitMiddleware  # noqa: E402
from colab_common.telemetry import RequestIDMiddleware  # noqa: E402

from app.config import settings  # noqa: E402
from app.middleware import AuthMiddleware, StructlogMiddleware  # noqa: E402
from app.proxy import close_http_client, proxy_request  # noqa: E402
from app.routers.health import router as health_router  # noqa: E402


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    yield
    await close_http_client()


app = FastAPI(
    title="Colab Gateway Service",
    version="0.1.0",
    description="API Gateway — routing, auth pre-check, rate-limit, CORS",
    lifespan=lifespan,
    docs_url="/docs" if settings.is_development else None,
    redoc_url="/redoc" if settings.is_development else None,
)

# ---------------------------------------------------------------------------
# Register error handlers
# ---------------------------------------------------------------------------
register_handlers(app)

# ---------------------------------------------------------------------------
# Middleware stack (applied inside-out; first added = outermost = first hit)
# ---------------------------------------------------------------------------

# 1. Request ID (outermost)
app.add_middleware(RequestIDMiddleware)

# 2. CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        f"https://{settings.app_domain}",
        f"https://{settings.marketing_domain}",
        f"https://{settings.admin_domain}",
        # Local dev
        "http://localhost:3000",
        "http://localhost:3001",
        "http://localhost:3002",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-Id", "X-RateLimit-Remaining"],
)

# 3. Structlog binding
app.add_middleware(StructlogMiddleware)

# 4. Auth
app.add_middleware(AuthMiddleware)

# 5. Rate limit (global; per-route limits handled in proxy_request)
app.add_middleware(RateLimitMiddleware, global_capacity=120)

# 6. Idempotency
app.add_middleware(IdempotencyMiddleware)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
app.include_router(health_router)

# ---------------------------------------------------------------------------
# Catch-all proxy route — must be last
# ---------------------------------------------------------------------------


@app.api_route(
    "/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
    include_in_schema=False,
)
async def catch_all(request: Request) -> object:
    return await proxy_request(request)
