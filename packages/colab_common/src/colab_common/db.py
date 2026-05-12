"""
colab_common.db — SQLAlchemy 2.0 async engine + session factory + Alembic env template.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from colab_common.settings import get_settings

# ---------------------------------------------------------------------------
# Declarative base — import this in each service's models
# ---------------------------------------------------------------------------


class Base(DeclarativeBase):
    """Base class for all ORM models across the platform."""

    pass


# ---------------------------------------------------------------------------
# Engine factory
# ---------------------------------------------------------------------------


def engine_factory(
    url: str | None = None,
    *,
    echo: bool = False,
    pool_size: int | None = None,
    max_overflow: int | None = None,
    **kwargs: Any,
) -> AsyncEngine:
    """
    Create an async SQLAlchemy engine.

    If url is None, reads from Settings.db.url.
    Sets statement_cache_size=0 for PgBouncer / RDS Proxy compatibility.
    """
    settings = get_settings()
    resolved_url = url or settings.db.url

    # Ensure async driver prefix
    if resolved_url.startswith("postgresql://"):
        resolved_url = resolved_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    connect_args: dict[str, Any] = {
        # PgBouncer / RDS Proxy compatibility
        "statement_cache_size": 0,
    }

    engine = create_async_engine(
        resolved_url,
        echo=echo or settings.is_development,
        pool_size=pool_size or settings.db.pool_min,
        max_overflow=max_overflow or (settings.db.pool_max - settings.db.pool_min),
        connect_args=connect_args,
        **kwargs,
    )

    # Inject current_user_id GUC for audit triggers (RLS hook stub)
    @event.listens_for(engine.sync_engine, "connect")
    def set_search_path(dbapi_connection: Any, connection_record: Any) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("SET search_path TO public")
        cursor.close()

    return engine


# ---------------------------------------------------------------------------
# Session factory
# ---------------------------------------------------------------------------


def make_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Return an async session factory for the given engine."""
    return async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,  # Avoid implicit IO after commit in FastAPI
        autoflush=True,
        autocommit=False,
    )


# Module-level lazily-initialized factory (services can override)
_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = engine_factory()
    return _engine


def _get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = make_session_factory(_get_engine())
    return _session_factory


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------


# Module-level async session factory (lazy-initialized); alias expected by some services
def async_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the module-level session factory (creates it on first call)."""
    return _get_session_factory()


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that yields a transactional async session.

    Usage:
        @router.get("/things")
        async def list_things(session: AsyncSession = Depends(get_session)):
            ...
    """
    factory = _get_session_factory()
    async with factory() as session:
        async with session.begin():
            yield session


@contextlib.asynccontextmanager
async def session_scope() -> AsyncGenerator[AsyncSession, None]:
    """
    Context manager for use outside FastAPI (e.g., background tasks).
    """
    factory = _get_session_factory()
    async with factory() as session:
        async with session.begin():
            yield session


# ---------------------------------------------------------------------------
# RLS helper — sets current_user_id GUC before each statement
# ---------------------------------------------------------------------------


async def set_rls_user(session: AsyncSession, user_id: str | None) -> None:
    """
    Set the PostgreSQL session variable `app.current_user_id` for RLS audit triggers.
    Call this early in the request lifecycle once the user is known.
    """
    value = user_id or ""
    await session.execute(text(f"SET LOCAL app.current_user_id = '{value}'"))
