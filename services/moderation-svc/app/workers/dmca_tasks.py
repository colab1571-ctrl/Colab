"""
moderation-svc — DMCA Celery Beat tasks.

M-032: mod.dmca.enact_hide — runs every 5 min
M-034: mod.dmca.scan_counter_window — runs every 1h

Both use synchronous SQLAlchemy (sync Celery worker context).
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

from app.workers.celery_app import celery_app
from app.workers.sla_tasks import _emit_sync

logger = logging.getLogger(__name__)


def _get_sync_session():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    sync_url = os.environ.get(
        "DATABASE_URL_SYNC",
        os.environ.get("DATABASE_URL", "postgresql://colab:colab@localhost:5432/colab").replace(
            "postgresql+asyncpg://", "postgresql://"
        ),
    )
    engine = create_engine(sync_url, pool_pre_ping=True)
    return engine, Session(engine)


@celery_app.task(name="mod.dmca.enact_hide", queue="mod-beat")
def enact_dmca_hide() -> dict:
    """
    Find DMCANotice rows with state='received' and hide_at <= now.
    Execute hide action for each via ModerationAction insert.
    Emits dmca.notice_filed_hidden.
    """
    from app.models import DMCANotice, ModerationAction, ModerationCase

    engine, sess = _get_sync_session()
    now = datetime.now(tz=timezone.utc)
    hidden_count = 0

    try:
        notices = (
            sess.query(DMCANotice)
            .filter(
                DMCANotice.state == "received",
                DMCANotice.hide_at <= now,
            )
            .all()
        )

        for notice in notices:
            # Insert hide action
            action = ModerationAction(
                case_id=notice.case_id,
                action_type="hide",
                reviewer_id=notice.target_user_id,  # system action
                reason="DMCA notice 24h hide enacted automatically",
                evidence_refs=[],
                target_user_id=notice.target_user_id,
                propagation_status="pending",
            )
            sess.add(action)

            # Update case status
            if notice.case_id:
                case = sess.get(ModerationCase, notice.case_id)
                if case:
                    case.status = "actioned"
                    case.action_type = "hide"
                    case.actioned_at = now

            # Update DMCA notice state
            notice.state = "hidden"
            notice.hidden_at = now
            hidden_count += 1

            _emit_sync(
                "dmca.notice_filed_hidden",
                {"dmca_id": str(notice.id), "target_user_id": str(notice.target_user_id)},
            )

        sess.commit()
    except Exception as exc:
        sess.rollback()
        logger.error("DMCA enact_hide failed", extra={"exc": str(exc)})
        raise
    finally:
        sess.close()
        engine.dispose()

    logger.info("DMCA hide enacted", extra={"hidden_count": hidden_count})
    return {"hidden_count": hidden_count}


@celery_app.task(name="mod.dmca.scan_counter_window", queue="mod-beat")
def scan_counter_window() -> dict:
    """
    Find CounterNotice rows where:
    - state='received'
    - statutory_window_end <= now
    - dmca_notice.suit_filed_notice_received_at IS NULL

    Auto-restore content and emit dmca.restored.
    """
    from app.models import CounterNotice, DMCANotice, ModerationAction, ModerationCase

    engine, sess = _get_sync_session()
    now = datetime.now(tz=timezone.utc)
    restored_count = 0

    try:
        counters = (
            sess.query(CounterNotice)
            .join(DMCANotice, CounterNotice.dmca_id == DMCANotice.id)
            .filter(
                CounterNotice.state == "received",
                CounterNotice.statutory_window_end <= now,
                DMCANotice.suit_filed_notice_received_at.is_(None),
            )
            .all()
        )

        for counter in counters:
            dmca = sess.get(DMCANotice, counter.dmca_id)
            if dmca is None:
                continue

            # Insert restore action
            action = ModerationAction(
                case_id=dmca.case_id,
                action_type="restore",
                reviewer_id=counter.counter_claimant_user_id,  # system
                reason="DMCA counter-notice 14-day statutory window expired — auto-restore",
                evidence_refs=[],
                target_user_id=counter.counter_claimant_user_id,
                propagation_status="pending",
            )
            sess.add(action)

            # Update states
            dmca.state = "restored"
            counter.state = "restored"
            counter.restored_at = now

            # Update case
            if dmca.case_id:
                case = sess.get(ModerationCase, dmca.case_id)
                if case:
                    case.status = "actioned"
                    case.action_type = "restore"
                    case.actioned_at = now

            restored_count += 1
            _emit_sync(
                "dmca.restored",
                {
                    "dmca_id": str(dmca.id),
                    "counter_id": str(counter.id),
                    "target_user_id": str(counter.counter_claimant_user_id),
                },
            )

        sess.commit()
    except Exception as exc:
        sess.rollback()
        logger.error("Counter-notice window scan failed", extra={"exc": str(exc)})
        raise
    finally:
        sess.close()
        engine.dispose()

    logger.info("Counter-notice scan complete", extra={"restored": restored_count})
    return {"restored_count": restored_count}
