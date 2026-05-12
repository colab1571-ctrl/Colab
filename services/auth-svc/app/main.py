"""
auth-svc — FastAPI application entrypoint.

Implements all auth endpoints per spec 003:
  - Signup: email, OAuth (Apple/Google), phone OTP
  - Login: email, OAuth, phone OTP
  - Email verification: magic-link + 6-digit OTP
  - Password reset
  - Token refresh + logout
  - Session management
  - Account management (email/phone change)
  - JWKS endpoint for token verification
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator, Any

from colab_common.telemetry import init as telemetry_init

telemetry_init("auth-svc")

from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

from app.routers import account, email_verify, login, password_reset, sessions, signup, token  # noqa: E402
from app.services.tokens import build_jwks  # noqa: E402
from colab_common.errors import register_handlers  # noqa: E402
from colab_common.idempotency import IdempotencyMiddleware  # noqa: E402
from colab_common.settings import get_settings  # noqa: E402
from colab_common.telemetry import RequestIDMiddleware  # noqa: E402

settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    yield


app = FastAPI(
    title="Colab Auth Service",
    version="1.0.0",
    description="Authentication + session management for the Colab platform.",
    lifespan=lifespan,
    docs_url="/docs" if settings.is_development else None,
    redoc_url="/redoc" if settings.is_development else None,
)

register_handlers(app)
app.add_middleware(RequestIDMiddleware)
app.add_middleware(IdempotencyMiddleware)

# Include routers
app.include_router(signup.router)
app.include_router(login.router)
app.include_router(email_verify.router)
app.include_router(password_reset.router)
app.include_router(token.router)
app.include_router(sessions.router)
app.include_router(account.router)


# ---------------------------------------------------------------------------
# JWKS endpoint — public key set for token verification by other services
# ---------------------------------------------------------------------------

@app.get("/.well-known/jwks.json", include_in_schema=False)
async def jwks() -> dict[str, Any]:
    """Public JWKS endpoint. Verifiers use this to validate RS256 access tokens."""
    return build_jwks()


@app.get("/healthz", include_in_schema=False)
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/version", include_in_schema=False)
async def version() -> dict[str, str]:
    import os

    return {
        "service": "auth-svc",
        "version": "1.0.0",
        "git_sha": os.environ.get("GIT_SHA", "dev"),
    }
