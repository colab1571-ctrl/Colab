"""
SLA computation helpers for support-svc.

SLA map:
  harassment_threats: ack 4h / resolve 24h
  ip_dmca:            ack 24h / resolve 168h (7d)
  payment:            ack 24h / resolve 72h
  technical:          ack 24h / resolve 120h (5d)
  other:              ack 48h / resolve 168h (7d)

Premium Pro: ack SLA halved (resolve unchanged).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

# (ack_hours, resolve_hours)
SLA_MAP: dict[str, tuple[int, int]] = {
    "harassment_threats": (4, 24),
    "ip_dmca": (24, 168),
    "payment": (24, 72),
    "technical": (24, 120),
    "other": (48, 168),
}


def compute_sla_due(
    category: str,
    tier: str,
    created_at: datetime | None = None,
) -> tuple[datetime, datetime]:
    """
    Return (sla_ack_due, sla_resolve_due) for a ticket.

    Args:
        category: one of SLA_MAP keys
        tier: 'free' | 'premium' | 'premium_pro'
        created_at: ticket creation timestamp; defaults to now(UTC)
    """
    if created_at is None:
        created_at = datetime.now(tz=timezone.utc)

    ack_h, resolve_h = SLA_MAP.get(category, (48, 168))

    if tier == "premium_pro":
        ack_h = ack_h // 2  # integer halving per spec §5.2

    sla_ack_due = created_at + timedelta(hours=ack_h)
    sla_resolve_due = created_at + timedelta(hours=resolve_h)
    return sla_ack_due, sla_resolve_due


def adjusted_due(due: datetime, paused_seconds: int) -> datetime:
    """Return SLA due date extended by accumulated pause time."""
    return due + timedelta(seconds=paused_seconds)
