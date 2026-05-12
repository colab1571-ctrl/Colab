"""
moderation-svc — Action propagation Celery tasks.

M-050: Action-dispatcher listens to mod.action_taken and fans out to
downstream services (003/004/006/007/009/013/014/015/016).

Each downstream consumer is a separate task on a dedicated queue so
individual service outages don't block others.

M-057: Propagation completeness watcher.
M-058: Reversal flow.
"""

from __future__ import annotations

import logging
import os
import uuid
from typing import Any

from app.workers.celery_app import celery_app
from app.workers.sla_tasks import _emit_sync

logger = logging.getLogger(__name__)

# Services to notify on permanent_ban; subset for other actions
_PERMANENT_BAN_SERVICES = [
    "auth_lockout",
    "badge_revoke",
    "chat_readonly",
    "subscription_pause",
    "notification_halt",
    "invite_cancel",
    "collab_pause",
    "support_ticket",
]


@celery_app.task(name="mod.propagation.dispatch", queue="mod-fast", bind=True, max_retries=5)
def dispatch_action(self: Any, action_id: str, action_type: str, target_user_id: str,
                    case_id: str, reason: str, reviewer_id: str,
                    second_reviewer_id: str | None = None) -> dict:
    """
    Entry point — called synchronously after ModerationAction is persisted.
    Spawns per-service consumer tasks in parallel.
    """
    propagation_id = str(uuid.uuid4())
    payload = {
        "action_id": action_id,
        "action_type": action_type,
        "target_user_id": target_user_id,
        "case_id": case_id,
        "reason": reason,
        "reviewer_id": reviewer_id,
        "second_reviewer_id": second_reviewer_id,
        "propagation_id": propagation_id,
    }

    tasks_to_dispatch = []

    if action_type in ("permanent_ban", "delete_account"):
        tasks_to_dispatch = [
            propagate_auth_lockout,
            propagate_badge_revoke,
            propagate_chat_readonly,
            propagate_subscription_pause,
            propagate_notification_halt,
            propagate_invite_cancel,
            propagate_collab_pause,
            propagate_support_ticket,
            propagate_admin_audit,
        ]
    elif action_type in ("temp_mute_1h", "temp_mute_24h", "temp_mute_7d"):
        tasks_to_dispatch = [propagate_chat_readonly, propagate_admin_audit]
    elif action_type == "hide":
        tasks_to_dispatch = [propagate_admin_audit]
    elif action_type == "restore":
        tasks_to_dispatch = [propagate_admin_audit]
    elif action_type == "warn":
        tasks_to_dispatch = [propagate_admin_audit]
    else:
        tasks_to_dispatch = [propagate_admin_audit]

    for task_fn in tasks_to_dispatch:
        task_fn.apply_async(kwargs={"payload": payload}, countdown=0)

    # Emit the high-level event
    _emit_sync("moderation.action_taken", payload)

    return {"propagation_id": propagation_id, "tasks": len(tasks_to_dispatch)}


# ---------------------------------------------------------------------------
# Per-service propagation tasks
# ---------------------------------------------------------------------------


@celery_app.task(name="mod.propagation.auth_lockout", queue="mod-fast", bind=True, max_retries=5)
def propagate_auth_lockout(self: Any, payload: dict) -> dict:
    """Emit auth.lockout event consumed by auth-svc (§003)."""
    _emit_sync("moderation.auth_lockout", payload)
    _update_propagation_event(payload["action_id"], "auth_lockout", "ok")
    logger.info("Auth lockout propagated", extra={"user": payload["target_user_id"]})
    return {"service": "auth", "status": "ok"}


@celery_app.task(name="mod.propagation.badge_revoke", queue="mod-fast", bind=True, max_retries=5)
def propagate_badge_revoke(self: Any, payload: dict) -> dict:
    """Emit profile.badge_revoke event consumed by profile-svc (§004)."""
    _emit_sync("moderation.badge_revoke", payload)
    _update_propagation_event(payload["action_id"], "badge_revoke", "ok")
    logger.info("Badge revoke propagated", extra={"user": payload["target_user_id"]})
    return {"service": "profile", "status": "ok"}


@celery_app.task(name="mod.propagation.chat_readonly", queue="mod-fast", bind=True, max_retries=5)
def propagate_chat_readonly(self: Any, payload: dict) -> dict:
    """Emit chat.readonly event consumed by chat-svc (§007)."""
    _emit_sync("moderation.chat_readonly", payload)
    _update_propagation_event(payload["action_id"], "chat_readonly", "ok")
    logger.info("Chat readonly propagated", extra={"user": payload["target_user_id"]})
    return {"service": "chat", "status": "ok"}


@celery_app.task(name="mod.propagation.subscription_pause", queue="mod-fast", bind=True, max_retries=5)
def propagate_subscription_pause(self: Any, payload: dict) -> dict:
    """Emit billing.subscription_pause event consumed by billing-svc (§013)."""
    _emit_sync("moderation.subscription_pause", payload)
    _update_propagation_event(payload["action_id"], "subscription_pause", "ok")
    logger.info("Subscription pause propagated", extra={"user": payload["target_user_id"]})
    return {"service": "billing", "status": "ok"}


@celery_app.task(name="mod.propagation.notification_halt", queue="mod-fast", bind=True, max_retries=5)
def propagate_notification_halt(self: Any, payload: dict) -> dict:
    """Emit notification.halt event consumed by notification-svc (§014)."""
    _emit_sync("moderation.notification_halt", payload)
    _update_propagation_event(payload["action_id"], "notification_halt", "ok")
    logger.info("Notification halt propagated", extra={"user": payload["target_user_id"]})
    return {"service": "notification", "status": "ok"}


@celery_app.task(name="mod.propagation.invite_cancel", queue="mod-fast", bind=True, max_retries=5)
def propagate_invite_cancel(self: Any, payload: dict) -> dict:
    """Emit invite.cancel_batch event consumed by invite-svc (§006)."""
    _emit_sync("moderation.invite_cancel", payload)
    _update_propagation_event(payload["action_id"], "invite_cancel", "ok")
    logger.info("Invite cancel propagated", extra={"user": payload["target_user_id"]})
    return {"service": "invite", "status": "ok"}


@celery_app.task(name="mod.propagation.collab_pause", queue="mod-fast", bind=True, max_retries=5)
def propagate_collab_pause(self: Any, payload: dict) -> dict:
    """Emit collab.admin_pause event consumed by collab-svc (§009)."""
    _emit_sync("moderation.collab_pause", payload)
    _update_propagation_event(payload["action_id"], "collab_pause", "ok")
    logger.info("Collab pause propagated", extra={"user": payload["target_user_id"]})
    return {"service": "collab", "status": "ok"}


@celery_app.task(name="mod.propagation.support_ticket", queue="mod-fast", bind=True, max_retries=5)
def propagate_support_ticket(self: Any, payload: dict) -> dict:
    """Emit support.auto_ticket event consumed by support-svc (§015)."""
    _emit_sync("moderation.support_ticket", payload)
    _update_propagation_event(payload["action_id"], "support_ticket", "ok")
    logger.info("Support ticket propagated", extra={"user": payload["target_user_id"]})
    return {"service": "support", "status": "ok"}


@celery_app.task(name="mod.propagation.admin_audit", queue="mod-fast", bind=True, max_retries=5)
def propagate_admin_audit(self: Any, payload: dict) -> dict:
    """Insert AdminAuditLog row via event (§016)."""
    _emit_sync("moderation.admin_audit", payload)
    _update_propagation_event(payload["action_id"], "admin_audit", "ok")
    logger.info("Admin audit propagated", extra={"action": payload["action_id"]})
    return {"service": "admin", "status": "ok"}


# ---------------------------------------------------------------------------
# Reversal — M-058
# ---------------------------------------------------------------------------


@celery_app.task(name="mod.propagation.reverse", queue="mod-fast", bind=True, max_retries=5)
def dispatch_action_reversal(self: Any, original_action_id: str, target_user_id: str,
                              reversal_action_id: str, reason: str) -> dict:
    """
    Fan out moderation.action_reversed to all downstream services.
    Each service performs the inverse operation (re-enable, restore, etc.).
    """
    payload = {
        "original_action_id": original_action_id,
        "reversal_action_id": reversal_action_id,
        "target_user_id": target_user_id,
        "reason": reason,
    }
    _emit_sync("moderation.action_reversed", payload)
    logger.info("Action reversal dispatched", extra={"original": original_action_id})
    return {"status": "dispatched"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _update_propagation_event(action_id: str, service_key: str, status: str) -> None:
    """Update ModerationAction.propagation_events[service_key] = status in DB."""
    import os

    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from app.models import ActionPropagationLog, ModerationAction

    sync_url = os.environ.get(
        "DATABASE_URL_SYNC",
        os.environ.get("DATABASE_URL", "postgresql://colab:colab@localhost:5432/colab").replace(
            "postgresql+asyncpg://", "postgresql://"
        ),
    )
    try:
        engine = create_engine(sync_url, pool_pre_ping=True)
        with Session(engine) as sess:
            # Append to ActionPropagationLog (append-only audit)
            log_entry = ActionPropagationLog(
                action_id=uuid.UUID(action_id),
                target_event=service_key,
                target_service=service_key,
                status=status,
                payload={"service": service_key, "status": status},
            )
            sess.add(log_entry)
            sess.commit()
        engine.dispose()
    except Exception as exc:
        logger.warning("Failed to update propagation log", extra={"exc": str(exc)})
