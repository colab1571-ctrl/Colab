"""
billing-svc — Dunning state machine.

States: day0 → day3 → day7 → day10_canceled → day30_grace_expired | recovered
Celery Beat job `dunning_tick` runs every 10 minutes.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.billing import DunningCase, Subscription

logger = logging.getLogger(__name__)

# Days from opened_at when each state transitions
STATE_DELAYS: dict[str, timedelta] = {
    "day0": timedelta(days=3),
    "day3": timedelta(days=4),   # day 3→7
    "day7": timedelta(days=3),   # day 7→10
    "day10_canceled": timedelta(days=20),  # day 10→30
}

TERMINAL_STATES = {"day30_grace_expired", "recovered"}


async def open_dunning_case(
    db: AsyncSession,
    user_id: uuid.UUID,
    subscription_id: uuid.UUID,
) -> DunningCase:
    """Open a new dunning case when a payment fails. Idempotent (check existing open case)."""
    result = await db.execute(
        select(DunningCase).where(
            DunningCase.subscription_id == subscription_id,
            DunningCase.state.not_in(list(TERMINAL_STATES)),
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        logger.info("Dunning case already open for sub %s", subscription_id)
        return existing

    case = DunningCase(
        id=uuid.uuid4(),
        user_id=user_id,
        subscription_id=subscription_id,
        opened_at=datetime.now(UTC),
        state="day0",
        last_attempt_at=datetime.now(UTC),
        last_attempt_result="payment_failed",
    )
    db.add(case)
    await db.flush()
    logger.info("Opened dunning case %s for sub %s", case.id, subscription_id)
    return case


async def mark_recovered(
    db: AsyncSession,
    subscription_id: uuid.UUID,
) -> DunningCase | None:
    """Mark dunning case as recovered when payment succeeds."""
    result = await db.execute(
        select(DunningCase).where(
            DunningCase.subscription_id == subscription_id,
            DunningCase.state.not_in(list(TERMINAL_STATES)),
        )
    )
    case = result.scalar_one_or_none()
    if case is None:
        return None

    case.state = "recovered"
    case.recovered_at = datetime.now(UTC)
    case.closed_at = datetime.now(UTC)
    await db.flush()
    logger.info("Dunning case %s recovered for sub %s", case.id, subscription_id)
    return case


async def advance_dunning_cases(db: AsyncSession) -> list[dict[str, Any]]:
    """
    Called by Celery Beat every 10 minutes.
    Advances eligible open cases to the next state.
    Returns list of actions taken (for observability).
    """
    now = datetime.now(UTC)
    actions = []

    result = await db.execute(
        select(DunningCase).where(
            DunningCase.state.not_in(list(TERMINAL_STATES))
        )
    )
    cases = result.scalars().all()

    for case in cases:
        delay = STATE_DELAYS.get(case.state)
        if delay is None:
            continue

        reference_time = case.last_attempt_at or case.opened_at
        if now < reference_time + delay:
            continue

        # Advance state
        old_state = case.state
        if case.state == "day0":
            case.state = "day3"
            action = "retry_charge"
        elif case.state == "day3":
            case.state = "day7"
            action = "retry_charge"
        elif case.state == "day7":
            case.state = "day10_canceled"
            action = "cancel_subscription"
        elif case.state == "day10_canceled":
            case.state = "day30_grace_expired"
            action = "expire_grace"
        else:
            continue

        case.last_attempt_at = now
        actions.append({
            "case_id": str(case.id),
            "user_id": str(case.user_id),
            "subscription_id": str(case.subscription_id),
            "old_state": old_state,
            "new_state": case.state,
            "action": action,
        })

        logger.info(
            "Dunning advance: case=%s sub=%s %s→%s action=%s",
            case.id, case.subscription_id, old_state, case.state, action,
        )

    await db.flush()
    return actions


async def cancel_subscription_for_dunning(
    db: AsyncSession,
    subscription_id: uuid.UUID,
) -> Subscription | None:
    """Cancel subscription at day10. Entitlements drop to Free."""
    result = await db.execute(
        select(Subscription).where(Subscription.id == subscription_id)
    )
    sub = result.scalar_one_or_none()
    if sub is None:
        return None

    sub.status = "canceled"
    sub.canceled_at = datetime.now(UTC)
    await db.flush()
    return sub
