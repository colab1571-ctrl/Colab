"""
billing-svc — Test fixtures and helpers.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.billing import (
    CreditTransaction,
    CreditWallet,
    Customer,
    DunningCase,
    EntitlementSnapshot,
    Subscription,
    WebhookEventLedger,
)
from colab_common.db import Base


DATABASE_URL = "postgresql+asyncpg://colab:colab@localhost:5432/billing_test"


@pytest.fixture(scope="session")
def event_loop_policy():
    import asyncio
    return asyncio.DefaultEventLoopPolicy()


@pytest_asyncio.fixture
async def db_engine():
    engine = create_async_engine(DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def db(db_engine):
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
        await session.rollback()


@pytest.fixture
def mock_redis():
    redis = MagicMock()
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock(return_value=True)
    redis.delete = AsyncMock(return_value=1)
    return redis


@pytest.fixture
def mock_amqp():
    channel = MagicMock()
    exchange = MagicMock()
    exchange.publish = AsyncMock()
    channel.default_exchange = exchange
    return channel


@pytest.fixture
def mock_settings():
    settings = MagicMock()
    settings.stripe_webhook_secret = "whsec_test_secret"
    settings.revenuecat_webhook_secret = "rc_test_secret"
    return settings


@pytest.fixture
def sample_user_id() -> uuid.UUID:
    return uuid.UUID("00000000-0000-0000-0000-000000000001")


@pytest.fixture
def sample_subscription(sample_user_id) -> dict[str, Any]:
    """A sample active Stripe subscription dict."""
    now = datetime.now(UTC)
    return {
        "id": "sub_test123",
        "customer": "cus_test123",
        "status": "active",
        "current_period_start": int(now.timestamp()),
        "current_period_end": int((now + timedelta(days=30)).timestamp()),
        "cancel_at_period_end": False,
        "trial_end": None,
        "items": {
            "data": [
                {
                    "price": {
                        "id": "price_premium_month",
                        "product": "prod_premium",
                        "recurring": {"interval": "month"},
                    }
                }
            ]
        },
    }


def make_stripe_event(
    event_type: str,
    data_object: dict[str, Any],
    event_id: str | None = None,
) -> dict[str, Any]:
    return {
        "id": event_id or f"evt_{uuid.uuid4().hex[:16]}",
        "type": event_type,
        "created": int(datetime.now(UTC).timestamp()),
        "data": {"object": data_object},
        "livemode": False,
    }


def make_rc_event(
    event_type: str,
    user_id: uuid.UUID,
    product_id: str = "colab_premium_monthly",
    expiration_ms: int | None = None,
) -> dict[str, Any]:
    now_ms = int(datetime.now(UTC).timestamp() * 1000)
    exp_ms = expiration_ms or (now_ms + 30 * 24 * 3600 * 1000)
    return {
        "event": {
            "id": f"rc_{uuid.uuid4().hex[:16]}",
            "type": event_type,
            "app_user_id": str(user_id),
            "product_id": product_id,
            "store": "APP_STORE",
            "original_transaction_id": f"apple_{uuid.uuid4().hex[:16]}",
            "purchased_at_ms": now_ms,
            "expiration_at_ms": exp_ms,
            "event_timestamp_ms": now_ms,
        }
    }
