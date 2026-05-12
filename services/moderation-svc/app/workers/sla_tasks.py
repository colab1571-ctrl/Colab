"""
moderation-svc — SLA scanner Celery Beat tasks.

M-013: every 5 min, scans for breached SLAs, sets sla_breached_at,
escalates tier_3 at +30 min past breach, emits events.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="mod.sla.scan", queue="mod-beat")
def sla_scan() -> dict:
    """
    Scan for ModerationCase rows with breached SLAs.
    Emits moderation.case.sla_breached for each breach.
    Auto-escalates tier_3 cases that are >30 min past breach and unclaimed.

    NOTE: This task uses synchronous SQLAlchemy (not async) because Celery
    workers run in a sync context. We create a dedicated sync engine session.
    """
    import os

    from sqlalchemy import create_engine, update
    from sqlalchemy.orm import Session

    from app.models import ModerationCase

    sync_db_url = os.environ.get(
        "DATABASE_URL_SYNC",
        os.environ.get("DATABASE_URL", "postgresql://colab:colab@localhost:5432/colab").replace(
            "postgresql+asyncpg://", "postgresql://"
        ),
    )

    engine = create_engine(sync_db_url, pool_pre_ping=True)
    now = datetime.now(tz=timezone.utc)
    escalate_cutoff = now - timedelta(minutes=30)

    breached_count = 0
    escalated_count = 0

    try:
        with Session(engine) as sess:
            # Find cases with breached SLA not yet marked
            cases = (
                sess.query(ModerationCase)
                .filter(
                    ModerationCase.status.in_(["open", "in_review"]),
                    ModerationCase.sla_breached_at.is_(None),
                    ModerationCase.sla_due_at <= now,
                )
                .all()
            )

            for case in cases:
                case.sla_breached_at = now
                breached_count += 1
                # Emit event (fire-and-forget via sync publish)
                _emit_sync(
                    "moderation.case.sla_breached",
                    {
                        "case_id": str(case.id),
                        "tier": case.priority_tier,
                        "breach_minutes": int(
                            (now - case.sla_due_at).total_seconds() / 60
                        ),
                    },
                )

            # Auto-escalate tier_3 cases >30 min past breach, still unclaimed
            tier3_to_escalate = (
                sess.query(ModerationCase)
                .filter(
                    ModerationCase.priority_tier == "tier_3_1h",
                    ModerationCase.status == "open",
                    ModerationCase.claimed_by.is_(None),
                    ModerationCase.sla_breached_at.isnot(None),
                    ModerationCase.sla_breached_at <= escalate_cutoff,
                )
                .all()
            )

            for case in tier3_to_escalate:
                case.status = "escalated"
                escalated_count += 1
                _emit_sync(
                    "moderation.case.escalated",
                    {"case_id": str(case.id), "reason": "sla_auto_escalate_30m"},
                )

            sess.commit()

    except Exception as exc:
        logger.error("SLA scan failed", extra={"exc": str(exc)})
        raise
    finally:
        engine.dispose()

    logger.info(
        "SLA scan complete",
        extra={"breached": breached_count, "escalated": escalated_count},
    )
    return {"breached": breached_count, "escalated": escalated_count}


def _emit_sync(event_name: str, payload: dict) -> None:
    """Best-effort synchronous event emit for Celery Beat tasks."""
    try:
        import json
        import os

        import pika

        rabbitmq_url = os.environ.get("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
        params = pika.URLParameters(rabbitmq_url)
        connection = pika.BlockingConnection(params)
        channel = connection.channel()
        domain = event_name.split(".")[0]
        channel.exchange_declare(exchange=domain, exchange_type="topic", durable=True)
        channel.basic_publish(
            exchange=domain,
            routing_key=event_name,
            body=json.dumps({"event": event_name, "data": payload}).encode(),
            properties=pika.BasicProperties(
                content_type="application/json",
                delivery_mode=2,
            ),
        )
        connection.close()
    except Exception as exc:
        logger.warning("Sync event emit failed", extra={"event": event_name, "exc": str(exc)})
