"""
Tests: entitlement resolution, precedence, cross-platform parity, Redis cache.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.entitlements import (
    AXIS_REGISTRY,
    SOURCE_PRIORITY,
    TIER_DEFAULTS,
    TIER_RANK,
    _higher_value,
    resolve_entitlements,
    get_cached_entitlements,
    invalidate_entitlement_cache,
)


class TestAxisHelpers:
    def test_higher_value_int_unlimited(self):
        assert _higher_value("invites_per_week", -1, 5) == -1
        assert _higher_value("invites_per_week", 5, -1) == -1

    def test_higher_value_int_normal(self):
        assert _higher_value("ai_credits_per_month", 200, 100) == 200

    def test_higher_value_bool_true_wins(self):
        assert _higher_value("ads_shown", True, False) is True
        assert _higher_value("ads_shown", False, True) is True

    def test_higher_value_enum_rank(self):
        assert _higher_value("mockup_fidelity", "advanced", "basic") == "advanced"
        assert _higher_value("mockup_fidelity", "off", "advanced") == "advanced"
        assert _higher_value("support_priority", "fastest", "fast") == "fastest"

    def test_all_13_axes_in_registry(self):
        expected = {
            "invites_per_week", "ai_credits_per_month", "ads_shown", "chat_export",
            "hide_from_non_premium", "picked_for_you_priority", "mockup_fidelity",
            "portfolio_pdf_export", "visibility_boost", "support_priority",
            "see_who_saved_you", "feed_profiles_per_day", "daily_save_cap",
        }
        assert set(AXIS_REGISTRY.keys()) == expected


class TestTierResolution:
    def test_free_is_lowest_rank(self):
        assert TIER_RANK["free"] < TIER_RANK["premium"] < TIER_RANK["pro"]

    def test_free_defaults_have_all_axes(self):
        for axis in AXIS_REGISTRY:
            assert axis in TIER_DEFAULTS["free"], f"Missing axis {axis} in free tier"

    def test_pro_defaults_have_all_axes(self):
        for axis in AXIS_REGISTRY:
            assert axis in TIER_DEFAULTS["pro"], f"Missing axis {axis} in pro tier"


class TestEntitlementResolution:
    @pytest.mark.asyncio
    async def test_no_subscription_returns_free_defaults(self, db, sample_user_id):
        resolved = await resolve_entitlements(db, sample_user_id)
        assert resolved.tier == "free"
        assert resolved.axes["invites_per_week"] == 5
        assert resolved.axes["ai_credits_per_month"] == 0
        assert resolved.axes["ads_shown"] is True

    @pytest.mark.asyncio
    async def test_active_premium_returns_premium_values(self, db, sample_user_id):
        from app.models.billing import Subscription
        from datetime import timedelta

        now = datetime.now(UTC)
        sub = Subscription(
            id=uuid.uuid4(),
            user_id=sample_user_id,
            source="stripe",
            gateway="stripe",
            tier="premium",
            status="active",
            store_product_id="price_premium_monthly",
            billing_period="month",
            current_period_start=now,
            current_period_end=now + timedelta(days=30),
            started_at=now,
        )
        db.add(sub)
        await db.flush()

        # Write snapshot rows
        from app.services.subscriptions import apply_entitlements_for_user
        await apply_entitlements_for_user(db, sample_user_id, sub)

        resolved = await resolve_entitlements(db, sample_user_id)
        assert resolved.tier == "premium"
        assert resolved.axes["invites_per_week"] == -1
        assert resolved.axes["ai_credits_per_month"] == 200
        assert resolved.axes["ads_shown"] is False

    @pytest.mark.asyncio
    async def test_grant_overrides_subscription_value(self, db, sample_user_id):
        from app.models.billing import EntitlementSnapshot, Subscription

        now = datetime.now(UTC)
        sub = Subscription(
            id=uuid.uuid4(),
            user_id=sample_user_id,
            source="stripe",
            gateway="stripe",
            tier="premium",
            status="active",
            store_product_id="price_premium_monthly",
            billing_period="month",
            current_period_start=now,
            current_period_end=now + timedelta(days=30),
            started_at=now,
        )
        db.add(sub)
        await db.flush()

        from app.services.subscriptions import apply_entitlements_for_user
        await apply_entitlements_for_user(db, sample_user_id, sub)

        # Add a grant for 2000 credits (overrides subscription's 200)
        grant = EntitlementSnapshot(
            id=uuid.uuid4(),
            user_id=sample_user_id,
            axis_key="ai_credits_per_month",
            value={"v": 2000},
            source="grant",
            source_ref=uuid.uuid4(),
            expires_at=None,
        )
        db.add(grant)
        await db.flush()

        resolved = await resolve_entitlements(db, sample_user_id)
        assert resolved.axes["ai_credits_per_month"] == 2000

    @pytest.mark.asyncio
    async def test_expired_grant_not_applied(self, db, sample_user_id):
        from app.models.billing import EntitlementSnapshot

        past = datetime.now(UTC) - timedelta(days=1)
        snap = EntitlementSnapshot(
            id=uuid.uuid4(),
            user_id=sample_user_id,
            axis_key="ai_credits_per_month",
            value={"v": 9999},
            source="grant",
            source_ref=uuid.uuid4(),
            expires_at=past,  # Already expired
        )
        db.add(snap)
        await db.flush()

        resolved = await resolve_entitlements(db, sample_user_id)
        # Should use free default, not the expired grant
        assert resolved.axes["ai_credits_per_month"] == 0


class TestCrossplatformParity:
    @pytest.mark.asyncio
    async def test_ios_plus_web_highest_tier_wins(self, db, sample_user_id):
        """User has iOS Premium + Web Pro → should get Pro entitlements."""
        from app.models.billing import Subscription

        now = datetime.now(UTC)
        ios_sub = Subscription(
            id=uuid.uuid4(),
            user_id=sample_user_id,
            source="revenuecat",
            gateway="apple",
            tier="premium",
            status="active",
            store_product_id="colab_premium_monthly",
            billing_period="month",
            current_period_start=now,
            current_period_end=now + timedelta(days=30),
            started_at=now,
        )
        web_sub = Subscription(
            id=uuid.uuid4(),
            user_id=sample_user_id,
            source="stripe",
            gateway="stripe",
            tier="pro",
            status="active",
            store_product_id="price_pro_monthly",
            billing_period="month",
            current_period_start=now,
            current_period_end=now + timedelta(days=30),
            started_at=now,
        )
        db.add(ios_sub)
        db.add(web_sub)
        await db.flush()

        from app.services.subscriptions import apply_entitlements_for_user
        await apply_entitlements_for_user(db, sample_user_id, ios_sub)
        await apply_entitlements_for_user(db, sample_user_id, web_sub)

        resolved = await resolve_entitlements(db, sample_user_id)
        # Pro wins
        assert resolved.tier == "pro"
        assert resolved.axes["mockup_fidelity"] == "advanced"
        assert resolved.axes["portfolio_pdf_export"] is True

    @pytest.mark.asyncio
    async def test_canceled_ios_active_web_web_wins(self, db, sample_user_id):
        from app.models.billing import Subscription

        now = datetime.now(UTC)
        ios_sub = Subscription(
            id=uuid.uuid4(),
            user_id=sample_user_id,
            source="revenuecat",
            gateway="apple",
            tier="pro",
            status="canceled",  # Canceled
            store_product_id="colab_pro_monthly",
            billing_period="month",
            current_period_start=now - timedelta(days=60),
            current_period_end=now - timedelta(days=30),
            started_at=now - timedelta(days=60),
        )
        web_sub = Subscription(
            id=uuid.uuid4(),
            user_id=sample_user_id,
            source="stripe",
            gateway="stripe",
            tier="premium",
            status="active",
            store_product_id="price_premium_monthly",
            billing_period="month",
            current_period_start=now,
            current_period_end=now + timedelta(days=30),
            started_at=now,
        )
        db.add(ios_sub)
        db.add(web_sub)
        await db.flush()

        from app.services.subscriptions import apply_entitlements_for_user
        await apply_entitlements_for_user(db, sample_user_id, web_sub)

        resolved = await resolve_entitlements(db, sample_user_id)
        # iOS is canceled so only web premium counts
        assert resolved.tier == "premium"


class TestRedisCache:
    @pytest.mark.asyncio
    async def test_cache_miss_resolves_and_sets(self, db, sample_user_id, mock_redis):
        """On cache miss, resolves from DB and stores in Redis."""
        mock_redis.get = AsyncMock(return_value=None)
        resolved = await get_cached_entitlements(mock_redis, db, sample_user_id)
        mock_redis.set.assert_called_once()
        assert resolved.tier == "free"

    @pytest.mark.asyncio
    async def test_cache_hit_skips_db(self, db, sample_user_id, mock_redis):
        """On cache hit, returns cached data without DB query."""
        import json

        cached_data = json.dumps({
            "axes": {"invites_per_week": -1, "ai_credits_per_month": 200},
            "tier": "premium",
            "subscription_status": "active",
            "current_period_end": None,
        })
        mock_redis.get = AsyncMock(return_value=cached_data)

        resolved = await get_cached_entitlements(mock_redis, db, sample_user_id)
        assert resolved.tier == "premium"
        assert resolved.axes["invites_per_week"] == -1
        # set should NOT be called on cache hit
        mock_redis.set.assert_not_called()

    @pytest.mark.asyncio
    async def test_invalidate_deletes_key(self, mock_redis, sample_user_id):
        await invalidate_entitlement_cache(mock_redis, sample_user_id)
        mock_redis.delete.assert_called_once_with(f"entitlements:{sample_user_id}")
