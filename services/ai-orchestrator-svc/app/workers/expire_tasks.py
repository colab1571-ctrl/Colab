"""
Celery Beat tasks for lifespan expiry:

  expire_mockup_assets   — runs hourly at :00; sets active=false for expired MockupAssets.
  expire_pending_consents — runs hourly at :30; expires pending_b consents older than 48h.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, update, select
from sqlalchemy.orm import Session

from app.models import MockupAsset, MockupConsent
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

DATABASE_URL_SYNC = os.environ.get(
    "DATABASE_URL", "postgresql://colab:colab@localhost:5432/colab"
).replace("postgresql+asyncpg://", "postgresql://")


def _get_sync_session() -> Session:
    engine = create_engine(DATABASE_URL_SYNC, pool_pre_ping=True)
    return Session(engine)


@celery_app.task(name="app.workers.expire_tasks.expire_mockup_assets", bind=True, max_retries=3)
def expire_mockup_assets(self) -> dict:
    """Set active=false for all MockupAssets past their expires_at."""
    now = datetime.now(timezone.utc)
    expired_ids = []

    try:
        with _get_sync_session() as session:
            assets = (
                session.execute(
                    select(MockupAsset).where(
                        MockupAsset.active.is_(True),
                        MockupAsset.expires_at <= now,
                    )
                )
                .scalars()
                .all()
            )
            for asset in assets:
                asset.active = False
                expired_ids.append(str(asset.id))
            session.commit()

        logger.info("Expired %d MockupAssets at %s", len(expired_ids), now.isoformat())
        return {"expired_count": len(expired_ids), "asset_ids": expired_ids}
    except Exception as exc:
        logger.error("expire_mockup_assets failed: %s", exc)
        raise self.retry(exc=exc, countdown=60)


@celery_app.task(name="app.workers.expire_tasks.expire_pending_consents", bind=True, max_retries=3)
def expire_pending_consents(self) -> dict:
    """Expire MockupConsent rows still pending_b after 48h."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=48)
    expired_count = 0

    try:
        with _get_sync_session() as session:
            result = session.execute(
                update(MockupConsent)
                .where(
                    MockupConsent.status == "pending_b",
                    MockupConsent.created_at <= cutoff,
                )
                .values(status="expired")
                .returning(MockupConsent.id)
            )
            expired_count = result.rowcount
            session.commit()

        logger.info("Expired %d pending MockupConsents", expired_count)
        return {"expired_count": expired_count}
    except Exception as exc:
        logger.error("expire_pending_consents failed: %s", exc)
        raise self.retry(exc=exc, countdown=60)
