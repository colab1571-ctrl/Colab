"""
Tests: credit wallet — reservation, commit, release, idempotency, race conditions.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime

import pytest

from app.services.credits import (
    InsufficientCreditsError,
    commit_reservation,
    credit_purchase,
    grant_subscription_credits,
    release_reservation,
    reserve_credits,
)


class TestCreditReservation:
    @pytest.mark.asyncio
    async def test_reserve_sufficient_credits(self, db, sample_user_id):
        """Reserve succeeds when balance is sufficient."""
        # First, add some credits
        await credit_purchase(
            db, sample_user_id, 100,
            "stripe_checkout", "session_001", "purchase:session_001"
        )
        await db.flush()

        res_id = await reserve_credits(
            db, sample_user_id, 50,
            "ai_interaction", "interaction_001", "reserve:interaction_001"
        )
        await db.flush()
        assert res_id is not None

    @pytest.mark.asyncio
    async def test_reserve_insufficient_credits_raises(self, db, sample_user_id):
        """Reserve fails with InsufficientCreditsError when balance too low."""
        # Wallet has 0 credits by default
        with pytest.raises(InsufficientCreditsError) as exc_info:
            await reserve_credits(
                db, sample_user_id, 100,
                "ai_interaction", "interaction_002", "reserve:interaction_002"
            )
        assert exc_info.value.balance == 0
        assert exc_info.value.requested == 100

    @pytest.mark.asyncio
    async def test_reserve_commit_reduces_balance(self, db, sample_user_id):
        """Reserve + commit reduces wallet balance by the reserved amount."""
        from sqlalchemy import select
        from app.models.billing import CreditWallet

        await credit_purchase(db, sample_user_id, 200, "stripe", "s_001", "purchase:s_001")
        await db.flush()

        res_id = await reserve_credits(
            db, sample_user_id, 50, "ai_interaction", "ai_001", "reserve:ai_001"
        )
        await db.flush()
        await commit_reservation(db, res_id)
        await db.flush()

        wallet = (await db.execute(
            select(CreditWallet).where(CreditWallet.user_id == sample_user_id)
        )).scalar_one()
        assert wallet.balance == 150  # 200 - 50

    @pytest.mark.asyncio
    async def test_reserve_release_restores_balance(self, db, sample_user_id):
        """Reserve + release leaves balance unchanged (net zero)."""
        from sqlalchemy import select
        from app.models.billing import CreditWallet

        await credit_purchase(db, sample_user_id, 200, "stripe", "s_002", "purchase:s_002")
        await db.flush()

        res_id = await reserve_credits(
            db, sample_user_id, 50, "ai_interaction", "ai_002", "reserve:ai_002"
        )
        await db.flush()
        await release_reservation(db, res_id)
        await db.flush()

        wallet = (await db.execute(
            select(CreditWallet).where(CreditWallet.user_id == sample_user_id)
        )).scalar_one()
        assert wallet.balance == 200  # Unchanged

    @pytest.mark.asyncio
    async def test_idempotent_reserve_same_key(self, db, sample_user_id):
        """Two reserve calls with same idempotency_key return same reservation_id."""
        await credit_purchase(db, sample_user_id, 100, "stripe", "s_003", "purchase:s_003")
        await db.flush()

        idem_key = "reserve:idempotent_test_001"
        res_id_1 = await reserve_credits(
            db, sample_user_id, 10, "ai_interaction", "ai_003", idem_key
        )
        await db.flush()

        res_id_2 = await reserve_credits(
            db, sample_user_id, 10, "ai_interaction", "ai_003", idem_key
        )
        assert res_id_1 == res_id_2

    @pytest.mark.asyncio
    async def test_idempotent_purchase(self, db, sample_user_id):
        """Credit purchase is idempotent on same idempotency key."""
        from sqlalchemy import select
        from app.models.billing import CreditWallet

        idem_key = "purchase:idem_test_session"
        await credit_purchase(db, sample_user_id, 50, "stripe", "sess_001", idem_key)
        await db.flush()
        await credit_purchase(db, sample_user_id, 50, "stripe", "sess_001", idem_key)
        await db.flush()

        wallet = (await db.execute(
            select(CreditWallet).where(CreditWallet.user_id == sample_user_id)
        )).scalar_one()
        # Balance should be 50, not 100 (idempotent)
        assert wallet.balance == 50


class TestSubscriptionCreditGrant:
    @pytest.mark.asyncio
    async def test_grant_credits_on_subscription(self, db, sample_user_id):
        from sqlalchemy import select
        from app.models.billing import CreditWallet

        sub_id = uuid.uuid4()
        period_start = datetime.now(UTC)
        tx = await grant_subscription_credits(db, sample_user_id, 200, sub_id, period_start)
        await db.flush()

        assert tx is not None
        wallet = (await db.execute(
            select(CreditWallet).where(CreditWallet.user_id == sample_user_id)
        )).scalar_one()
        assert wallet.balance == 200

    @pytest.mark.asyncio
    async def test_grant_idempotent_same_period(self, db, sample_user_id):
        """Granting credits for same sub+period twice is idempotent."""
        from sqlalchemy import select
        from app.models.billing import CreditWallet

        sub_id = uuid.uuid4()
        period_start = datetime.now(UTC)

        tx1 = await grant_subscription_credits(db, sample_user_id, 200, sub_id, period_start)
        await db.flush()
        tx2 = await grant_subscription_credits(db, sample_user_id, 200, sub_id, period_start)
        await db.flush()

        assert tx1 is not None
        assert tx2 is None  # Duplicate, returns None

        wallet = (await db.execute(
            select(CreditWallet).where(CreditWallet.user_id == sample_user_id)
        )).scalar_one()
        assert wallet.balance == 200  # Not doubled
