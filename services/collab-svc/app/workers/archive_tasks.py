"""
Celery tasks for collaboration archival.

- archive_collab: auto-archive (30d inactivity)
- archive_finalize: called after terminal status transition
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime

from celery import shared_task
from sqlalchemy import select, update

from app.db import AsyncSessionLocal
from app.models import Collaboration
from app.workers.events import emit_event

logger = logging.getLogger(__name__)


def _run_async(coro):  # type: ignore[no-untyped-def]
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@shared_task(name="app.workers.archive_tasks.archive_collab", bind=True)
def archive_collab(self, collab_id_str: str) -> None:  # type: ignore[no-untyped-def]
    """Auto-archive a collab due to 30-day inactivity."""
    _run_async(_archive_collab_async(collab_id_str))


async def _archive_collab_async(collab_id_str: str) -> None:
    collab_id = uuid.UUID(collab_id_str)
    now = datetime.now(UTC)

    async with AsyncSessionLocal() as db:
        await db.execute(
            update(Collaboration)
            .where(
                Collaboration.id == collab_id,
                Collaboration.archived_at.is_(None),
            )
            .values(archived_at=now, archive_at=None, updated_at=now)
        )
        await db.commit()

    await emit_event(
        "collab.archived",
        {
            "collab_id": collab_id_str,
            "reason": "inactivity_30d",
            "archived_at": now.isoformat(),
        },
    )
    logger.info("Collab %s auto-archived (30d inactivity)", collab_id_str)


@shared_task(name="app.workers.archive_tasks.archive_finalize", bind=True)
def archive_finalize(self, collab_id_str: str, reason: str) -> None:  # type: ignore[no-untyped-def]
    """
    Finalize archive after a terminal status transition (completed/didnt_work_out).
    Sets archived_at, emits collab.archived and collab.feedback_prompt_due.
    """
    _run_async(_archive_finalize_async(collab_id_str, reason))


async def _archive_finalize_async(collab_id_str: str, reason: str) -> None:
    collab_id = uuid.UUID(collab_id_str)
    now = datetime.now(UTC)

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Collaboration).where(Collaboration.id == collab_id)
        )
        collab = result.scalars().first()
        if collab is None:
            return

        await db.execute(
            update(Collaboration)
            .where(Collaboration.id == collab_id)
            .values(archived_at=now, archive_at=None, updated_at=now)
        )
        await db.commit()

    await emit_event(
        "collab.archived",
        {
            "collab_id": collab_id_str,
            "reason": reason,
            "archived_at": now.isoformat(),
        },
    )

    if reason in ("completed", "didnt_work_out"):
        await emit_event(
            "collab.feedback_prompt_due",
            {
                "collab_id": collab_id_str,
                "profile_id_a": str(collab.profile_id_a),
                "profile_id_b": str(collab.profile_id_b),
            },
        )

    logger.info("Collab %s finalized/archived (reason: %s)", collab_id_str, reason)
