"""
support-svc — SLA scanner Celery Beat tasks.

Runs every 5 minutes (via beat_schedule.py).

Scan 1 (ack breach):
  Tickets where sla_ack_due < now AND first_response_at IS NULL
  AND status NOT IN ('resolved','closed').
  → emit SupportTicketEvent(kind='sla_breach')
  → set priority='critical'
  → publish support.sla.ack_breached

Scan 2 (resolve breach):
  Tickets where sla_resolve_due < now AND resolved_at IS NULL
  AND status NOT IN ('resolved','closed').
  → emit SupportTicketEvent(kind='sla_resolve_breached')
  → publish support.sla.resolve_breached

Both scans account for sla_paused_seconds (pause/resume logic §3.4).
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


def _sync_db_url() -> str:
    return os.environ.get(
        "DATABASE_URL_SYNC",
        os.environ.get(
            "DATABASE_URL", "postgresql://colab:colab@localhost:5432/colab"
        ).replace("postgresql+asyncpg://", "postgresql://"),
    )


def _rabbitmq_url() -> str:
    return os.environ.get("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")


def _emit_sync(event_name: str, payload: dict) -> None:
    try:
        import pika

        params = pika.URLParameters(_rabbitmq_url())
        conn = pika.BlockingConnection(params)
        ch = conn.channel()
        domain = event_name.split(".")[0]
        ch.exchange_declare(exchange=domain, exchange_type="topic", durable=True)
        ch.basic_publish(
            exchange=domain,
            routing_key=event_name,
            body=json.dumps({"event": event_name, "data": payload}).encode(),
            properties=pika.BasicProperties(
                content_type="application/json",
                delivery_mode=2,
            ),
        )
        conn.close()
    except Exception as exc:
        logger.warning("Sync emit failed [%s]: %s", event_name, exc)


@celery_app.task(name="support.sla.scan", queue="support-beat")
def sla_scan() -> dict:
    """
    Full SLA scan: check both ack and resolve breaches.
    Idempotent — only marks rows that have not already been marked breached.
    """
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import Session

    db_url = _sync_db_url()
    engine = create_engine(db_url, pool_pre_ping=True)
    now = datetime.now(tz=timezone.utc)
    ack_breached = 0
    resolve_breached = 0

    try:
        with Session(engine) as sess:
            # ----------------------------------------------------------------
            # ACK breach scan
            # ----------------------------------------------------------------
            ack_rows = sess.execute(
                text(
                    """
                    SELECT id, user_id, category, sla_ack_due, sla_paused_seconds
                    FROM support.support_ticket
                    WHERE first_response_at IS NULL
                      AND sla_ack_breached_at IS NULL
                      AND status NOT IN ('resolved', 'closed')
                      AND sla_ack_due + (sla_paused_seconds || ' seconds')::interval < :now
                    """
                ),
                {"now": now},
            ).fetchall()

            for row in ack_rows:
                sess.execute(
                    text(
                        """
                        UPDATE support.support_ticket
                        SET sla_ack_breached_at = :now, priority = 'critical', updated_at = :now
                        WHERE id = :tid
                        """
                    ),
                    {"now": now, "tid": row.id},
                )
                sess.execute(
                    text(
                        """
                        INSERT INTO support.support_ticket_event
                          (ticket_id, kind, actor, body)
                        VALUES (:tid, 'sla_breach', 'system', 'Ack SLA breached')
                        """
                    ),
                    {"tid": row.id},
                )
                _emit_sync(
                    "support.sla.ack_breached",
                    {
                        "ticket_id": str(row.id),
                        "user_id": str(row.user_id),
                        "category": row.category,
                    },
                )
                ack_breached += 1

            # ----------------------------------------------------------------
            # RESOLVE breach scan
            # ----------------------------------------------------------------
            resolve_rows = sess.execute(
                text(
                    """
                    SELECT id, user_id, category, sla_resolve_due, sla_paused_seconds
                    FROM support.support_ticket
                    WHERE resolved_at IS NULL
                      AND sla_resolve_breached_at IS NULL
                      AND status NOT IN ('resolved', 'closed')
                      AND sla_resolve_due + (sla_paused_seconds || ' seconds')::interval < :now
                    """
                ),
                {"now": now},
            ).fetchall()

            for row in resolve_rows:
                sess.execute(
                    text(
                        """
                        UPDATE support.support_ticket
                        SET sla_resolve_breached_at = :now, priority = 'critical', updated_at = :now
                        WHERE id = :tid
                        """
                    ),
                    {"now": now, "tid": row.id},
                )
                sess.execute(
                    text(
                        """
                        INSERT INTO support.support_ticket_event
                          (ticket_id, kind, actor, body)
                        VALUES (:tid, 'sla_resolve_breached', 'system', 'Resolve SLA breached')
                        """
                    ),
                    {"tid": row.id},
                )
                _emit_sync(
                    "support.sla.resolve_breached",
                    {
                        "ticket_id": str(row.id),
                        "user_id": str(row.user_id),
                        "category": row.category,
                    },
                )
                resolve_breached += 1

            sess.commit()

    except Exception as exc:
        logger.error("SLA scan failed: %s", exc)
        raise
    finally:
        engine.dispose()

    logger.info(
        "Support SLA scan complete — ack_breached=%d resolve_breached=%d",
        ack_breached,
        resolve_breached,
    )
    return {"ack_breached": ack_breached, "resolve_breached": resolve_breached}
