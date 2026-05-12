"""
Tests: dunning state machine transitions.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.services.dunning import (
    TERMINAL_STATES,
    advance_dunning_cases,
    mark_recovered,
    open_dunning_case,
)


class TestDunningStateMachine:
    @pytest.fixture
    async def active_subscription(self, db, sample_user_id):
        from app.models.billing import Subscription

        now = datetime.now(UTC)
        sub = Subscription(
            id=uuid.uuid4(),
            user_id=sample_user_id,
            source="stripe",
            gateway="stripe",
            tier="premium",
            status="past_due",
            store_product_id="price_premium_monthly",
            billing_period="month",
            current_period_start=now - timedelta(days=30),
            current_period_end=now,
            started_at=now - timedelta(days=30),
        )
        db.add(sub)
        await db.flush()
        return sub

    @pytest.mark.asyncio
    async def test_open_dunning_case(self, db, sample_user_id, active_subscription):
        case = await open_dunning_case(db, sample_user_id, active_subscription.id)
        await db.flush()
        assert case.state == "day0"
        assert case.user_id == sample_user_id

    @pytest.mark.asyncio
    async def test_open_dunning_idempotent(self, db, sample_user_id, active_subscription):
        """Opening dunning twice for same sub returns same case."""
        case1 = await open_dunning_case(db, sample_user_id, active_subscription.id)
        await db.flush()
        case2 = await open_dunning_case(db, sample_user_id, active_subscription.id)
        assert case1.id == case2.id

    @pytest.mark.asyncio
    async def test_advance_day0_to_day3(self, db, sample_user_id, active_subscription):
        """Case at day0 with attempt 3+ days ago should advance to day3."""
        case = await open_dunning_case(db, sample_user_id, active_subscription.id)
        # Backdate the last_attempt_at to 4 days ago
        case.last_attempt_at = datetime.now(UTC) - timedelta(days=4)
        await db.flush()

        actions = await advance_dunning_cases(db)
        advanced = [a for a in actions if a["case_id"] == str(case.id)]
        assert len(advanced) == 1
        assert advanced[0]["new_state"] == "day3"

    @pytest.mark.asyncio
    async def test_advance_day3_to_day7(self, db, sample_user_id, active_subscription):
        case = await open_dunning_case(db, sample_user_id, active_subscription.id)
        case.state = "day3"
        case.last_attempt_at = datetime.now(UTC) - timedelta(days=5)
        await db.flush()

        actions = await advance_dunning_cases(db)
        advanced = [a for a in actions if a["case_id"] == str(case.id)]
        assert len(advanced) == 1
        assert advanced[0]["new_state"] == "day7"

    @pytest.mark.asyncio
    async def test_advance_day7_to_day10_canceled(self, db, sample_user_id, active_subscription):
        case = await open_dunning_case(db, sample_user_id, active_subscription.id)
        case.state = "day7"
        case.last_attempt_at = datetime.now(UTC) - timedelta(days=4)
        await db.flush()

        actions = await advance_dunning_cases(db)
        advanced = [a for a in actions if a["case_id"] == str(case.id)]
        assert len(advanced) == 1
        assert advanced[0]["new_state"] == "day10_canceled"
        assert advanced[0]["action"] == "cancel_subscription"

    @pytest.mark.asyncio
    async def test_not_advanced_before_delay(self, db, sample_user_id, active_subscription):
        """Case should not advance if delay period has not passed."""
        case = await open_dunning_case(db, sample_user_id, active_subscription.id)
        case.last_attempt_at = datetime.now(UTC)  # Just now
        await db.flush()

        actions = await advance_dunning_cases(db)
        advanced = [a for a in actions if a["case_id"] == str(case.id)]
        assert len(advanced) == 0

    @pytest.mark.asyncio
    async def test_recovered_closes_case(self, db, sample_user_id, active_subscription):
        case = await open_dunning_case(db, sample_user_id, active_subscription.id)
        await db.flush()

        recovered = await mark_recovered(db, active_subscription.id)
        await db.flush()

        assert recovered is not None
        assert recovered.state == "recovered"
        assert recovered.recovered_at is not None
        assert recovered.id == case.id

    @pytest.mark.asyncio
    async def test_terminal_states_not_advanced(self, db, sample_user_id, active_subscription):
        """Cases in terminal states are not advanced."""
        case = await open_dunning_case(db, sample_user_id, active_subscription.id)
        case.state = "recovered"
        case.last_attempt_at = datetime.now(UTC) - timedelta(days=100)
        await db.flush()

        actions = await advance_dunning_cases(db)
        advanced = [a for a in actions if a["case_id"] == str(case.id)]
        assert len(advanced) == 0
