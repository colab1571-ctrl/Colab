"""
In-app banner channel — publishes notification.inapp events to RabbitMQ.
chat-svc consumes from the 'notifications' exchange and forwards over WebSocket.
"""

from __future__ import annotations

import logging
from datetime import datetime
from uuid import UUID

from colab_common import events

logger = logging.getLogger(__name__)

NOTIFICATIONS_EXCHANGE = "notifications"


async def publish_inapp_banner(
    user_id: str,
    notif_id: str,
    notif_type: str,
    title: str,
    body: str,
    action_url: str | None,
    created_at: datetime,
) -> None:
    """
    Publish an in-app banner event for chat-svc to fanout over WebSocket.
    """
    payload = {
        "event": "notification",
        "data": {
            "id": notif_id,
            "user_id": user_id,
            "type": notif_type,
            "title": title,
            "body": body,
            "action_url": action_url,
            "created_at": created_at.isoformat(),
        },
    }
    try:
        await events.publish(
            f"notification.inapp.{user_id}",
            payload,
            exchange_name=NOTIFICATIONS_EXCHANGE,
        )
        logger.info("In-app banner published", extra={"user_id": user_id, "type": notif_type})
    except Exception as exc:
        # In-app delivery is best-effort; do not fail the whole dispatch
        logger.warning("Failed to publish in-app banner: %s", exc)
