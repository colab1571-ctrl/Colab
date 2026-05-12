"""
invite-svc — RabbitMQ event publishers.

Exchange: colab.events (topic, durable)
Routing keys:
  invite.sent
  invite.accepted
  invite.rejected
  invite.expired
  invite.cancelled
  match.created
  block.created
  block.removed
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone

import aio_pika

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


async def _publish(
    channel: aio_pika.abc.AbstractChannel,
    routing_key: str,
    payload: dict,
) -> None:
    """Publish a JSON event to the colab.events topic exchange."""
    exchange = await channel.declare_exchange(
        "colab.events", aio_pika.ExchangeType.TOPIC, durable=True
    )
    message = aio_pika.Message(
        body=json.dumps(payload).encode(),
        content_type="application/json",
        delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
    )
    await exchange.publish(message, routing_key=routing_key)
    logger.debug("Published event: %s payload=%s", routing_key, payload)


async def emit_invite_sent(
    channel: aio_pika.abc.AbstractChannel,
    invite_id: uuid.UUID,
    from_profile_id: uuid.UUID,
    to_profile_id: uuid.UUID,
) -> None:
    await _publish(channel, "invite.sent", {
        "event": "invite.sent",
        "invite_id": str(invite_id),
        "from_profile_id": str(from_profile_id),
        "to_profile_id": str(to_profile_id),
        "sent_at": _now_iso(),
    })


async def emit_invite_accepted(
    channel: aio_pika.abc.AbstractChannel,
    invite_id: uuid.UUID,
    from_profile_id: uuid.UUID,
    to_profile_id: uuid.UUID,
) -> None:
    await _publish(channel, "invite.accepted", {
        "event": "invite.accepted",
        "invite_id": str(invite_id),
        "from_profile_id": str(from_profile_id),
        "to_profile_id": str(to_profile_id),
        "accepted_at": _now_iso(),
    })


async def emit_invite_rejected(
    channel: aio_pika.abc.AbstractChannel,
    invite_id: uuid.UUID,
    from_profile_id: uuid.UUID,
    to_profile_id: uuid.UUID,
) -> None:
    # Rejection is SILENT to sender — event is NOT published to notification-svc
    # but IS emitted for audit/analytics purposes only.
    await _publish(channel, "invite.rejected", {
        "event": "invite.rejected",
        "invite_id": str(invite_id),
        "from_profile_id": str(from_profile_id),
        "to_profile_id": str(to_profile_id),
        "rejected_at": _now_iso(),
        "silent": True,  # notification-svc filters this
    })


async def emit_invite_cancelled(
    channel: aio_pika.abc.AbstractChannel,
    invite_id: uuid.UUID,
    from_profile_id: uuid.UUID,
    to_profile_id: uuid.UUID,
) -> None:
    await _publish(channel, "invite.cancelled", {
        "event": "invite.cancelled",
        "invite_id": str(invite_id),
        "from_profile_id": str(from_profile_id),
        "to_profile_id": str(to_profile_id),
        "cancelled_at": _now_iso(),
    })


async def emit_match_created(
    channel: aio_pika.abc.AbstractChannel,
    profile_a_id: uuid.UUID,
    profile_b_id: uuid.UUID,
    invite_a_id: uuid.UUID,
    invite_b_id: uuid.UUID,
) -> None:
    """
    Emit match.created event with canonical profile ordering (min/max UUID).
    Idempotent: chat-svc uses ON CONFLICT DO NOTHING; notification-svc deduplicates
    on (user_id, event_type, reference_id) within 24h.
    """
    # Canonical ordering to ensure same message key regardless of accept order
    if str(profile_a_id) > str(profile_b_id):
        profile_a_id, profile_b_id = profile_b_id, profile_a_id
        invite_a_id, invite_b_id = invite_b_id, invite_a_id

    await _publish(channel, "match.created", {
        "event": "match.created",
        "profile_a_id": str(profile_a_id),
        "profile_b_id": str(profile_b_id),
        "invite_a_id": str(invite_a_id),
        "invite_b_id": str(invite_b_id),
        "matched_at": _now_iso(),
    })


async def emit_block_created(
    channel: aio_pika.abc.AbstractChannel,
    blocker_id: uuid.UUID,
    blocked_id: uuid.UUID,
) -> None:
    """
    Emit block.created — consumed by:
      - discovery-svc: evict feed cache for both users
      - chat-svc: flip active collab chat to read-only
      - notification-svc: suppress delivery across block boundary
    """
    await _publish(channel, "block.created", {
        "event": "block.created",
        "blocker_id": str(blocker_id),
        "blocked_id": str(blocked_id),
        # Also emit as profile.blocked for discovery-svc legacy binding
        "type": "profile.blocked",
        "payload": {
            "blocker_id": str(blocker_id),
            "blocked_id": str(blocked_id),
        },
        "created_at": _now_iso(),
    })
    # Also publish under the legacy discovery-svc routing key
    await _publish(channel, "profile.blocked", {
        "type": "profile.blocked",
        "payload": {
            "blocker_id": str(blocker_id),
            "blocked_id": str(blocked_id),
        },
    })


async def emit_block_removed(
    channel: aio_pika.abc.AbstractChannel,
    blocker_id: uuid.UUID,
    blocked_id: uuid.UUID,
) -> None:
    await _publish(channel, "block.removed", {
        "event": "block.removed",
        "blocker_id": str(blocker_id),
        "blocked_id": str(blocked_id),
        "removed_at": _now_iso(),
    })
