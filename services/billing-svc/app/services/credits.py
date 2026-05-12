"""
billing-svc — Credit wallet service.

Pessimistic reservation pattern:
  reserve() → INSERT reserved tx → deduct from available
  commit()  → mark committed, reduce balance
  release() → mark released, insert compensating +N tx
All wallet writes under SERIALIZABLE isolation with row lock on CreditWallet.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.billing import CreditTransaction, CreditWallet
from colab_common.errors import ConflictError

logger = logging.getLogger(__name__)


class InsufficientCreditsError(Exception):
    def __init__(self, balance: int, requested: int) -> None:
        self.balance = balance
        self.requested = requested
        super().__init__(f"Insufficient credits: balance={balance}, requested={requested}")


async def _get_or_create_wallet(db: AsyncSession, user_id: uuid.UUID) -> CreditWallet:
    result = await db.execute(
        select(CreditWallet)
        .where(CreditWallet.user_id == user_id)
        .with_for_update()
    )
    wallet = result.scalar_one_or_none()
    if wallet is None:
        wallet = CreditWallet(user_id=user_id, balance=0)
        db.add(wallet)
        await db.flush()
    return wallet


async def _sum_reserved(db: AsyncSession, user_id: uuid.UUID) -> int:
    """Sum of negative reserved deltas (pending deductions)."""
    result = await db.execute(
        select(func.coalesce(func.sum(CreditTransaction.delta), 0)).where(
            CreditTransaction.user_id == user_id,
            CreditTransaction.status == "reserved",
        )
    )
    val = result.scalar()
    return int(val) if val else 0


async def reserve_credits(
    db: AsyncSession,
    user_id: uuid.UUID,
    amount: int,
    reference_kind: str,
    reference_id: str,
    idempotency_key: str,
) -> uuid.UUID:
    """
    Reserve `amount` credits. Returns reservation transaction id.
    Raises InsufficientCreditsError if not enough available.
    Uses SERIALIZABLE isolation (caller must set on session).
    """
    wallet = await _get_or_create_wallet(db, user_id)

    reserved_total = await _sum_reserved(db, user_id)
    available = wallet.balance + reserved_total  # reserved_total is negative

    if available < amount:
        raise InsufficientCreditsError(balance=available, requested=amount)

    tx = CreditTransaction(
        id=uuid.uuid4(),
        user_id=user_id,
        delta=-amount,
        reason="reserve",
        reference_kind=reference_kind,
        reference_id=reference_id,
        idempotency_key=idempotency_key,
        status="reserved",
    )
    db.add(tx)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        # Idempotent: find existing reservation
        result = await db.execute(
            select(CreditTransaction).where(
                CreditTransaction.idempotency_key == idempotency_key
            )
        )
        existing = result.scalar_one()
        return existing.id
    return tx.id


async def commit_reservation(
    db: AsyncSession,
    reservation_id: uuid.UUID,
) -> None:
    """Commit a reservation: mark committed, reduce wallet balance."""
    result = await db.execute(
        select(CreditTransaction)
        .where(CreditTransaction.id == reservation_id)
        .with_for_update()
    )
    tx = result.scalar_one_or_none()
    if tx is None or tx.status != "reserved":
        logger.warning("commit_reservation: tx %s not found or not reserved", reservation_id)
        return

    tx.status = "committed"
    tx.committed_at = datetime.now(UTC)

    wallet = await _get_or_create_wallet(db, tx.user_id)
    wallet.balance += tx.delta  # delta is negative
    wallet.updated_at = datetime.now(UTC)
    await db.flush()


async def release_reservation(
    db: AsyncSession,
    reservation_id: uuid.UUID,
    reason: str = "release",
) -> None:
    """Release a reservation: mark released, insert compensating +N transaction."""
    result = await db.execute(
        select(CreditTransaction)
        .where(CreditTransaction.id == reservation_id)
        .with_for_update()
    )
    tx = result.scalar_one_or_none()
    if tx is None or tx.status != "reserved":
        logger.warning("release_reservation: tx %s not found or not reserved", reservation_id)
        return

    tx.status = "released"

    # Compensating transaction
    comp = CreditTransaction(
        id=uuid.uuid4(),
        user_id=tx.user_id,
        delta=-tx.delta,  # undo the negative
        reason=reason,
        reference_kind="credit_transaction",
        reference_id=str(tx.id),
        idempotency_key=f"release:{tx.id}",
        status="committed",
        committed_at=datetime.now(UTC),
    )
    db.add(comp)
    await db.flush()


async def credit_purchase(
    db: AsyncSession,
    user_id: uuid.UUID,
    amount: int,
    reference_kind: str,
    reference_id: str,
    idempotency_key: str,
) -> CreditTransaction:
    """Add credits from a purchase (web or mobile). Idempotent."""
    wallet = await _get_or_create_wallet(db, user_id)

    tx = CreditTransaction(
        id=uuid.uuid4(),
        user_id=user_id,
        delta=amount,
        reason="purchase",
        reference_kind=reference_kind,
        reference_id=reference_id,
        idempotency_key=idempotency_key,
        status="committed",
        committed_at=datetime.now(UTC),
    )
    db.add(tx)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        result = await db.execute(
            select(CreditTransaction).where(
                CreditTransaction.idempotency_key == idempotency_key
            )
        )
        return result.scalar_one()

    wallet.balance += amount
    wallet.updated_at = datetime.now(UTC)
    return tx


async def grant_subscription_credits(
    db: AsyncSession,
    user_id: uuid.UUID,
    amount: int,
    subscription_id: uuid.UUID,
    period_start: datetime,
) -> CreditTransaction | None:
    """Grant monthly AI credits on subscription activation/renewal. Idempotent."""
    idem_key = f"grant:{subscription_id}:{period_start.date().isoformat()}"
    wallet = await _get_or_create_wallet(db, user_id)

    tx = CreditTransaction(
        id=uuid.uuid4(),
        user_id=user_id,
        delta=amount,
        reason="subscription_grant",
        reference_kind="subscription",
        reference_id=str(subscription_id),
        idempotency_key=idem_key,
        status="committed",
        committed_at=datetime.now(UTC),
    )
    db.add(tx)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        return None  # Already granted for this period

    wallet.balance += amount
    wallet.updated_at = datetime.now(UTC)
    return tx


async def admin_adjust_credits(
    db: AsyncSession,
    user_id: uuid.UUID,
    delta: int,
    reason: str,
    admin_action_id: str,
) -> CreditTransaction:
    wallet = await _get_or_create_wallet(db, user_id)

    tx = CreditTransaction(
        id=uuid.uuid4(),
        user_id=user_id,
        delta=delta,
        reason="admin_grant",
        reference_kind="admin_action",
        reference_id=admin_action_id,
        idempotency_key=f"admin:{admin_action_id}",
        status="committed",
        committed_at=datetime.now(UTC),
    )
    db.add(tx)
    await db.flush()

    wallet.balance += delta
    wallet.updated_at = datetime.now(UTC)
    return tx
