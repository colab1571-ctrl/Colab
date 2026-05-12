"""
notification-svc ORM models.

Tables:
  - Notification
  - NotificationPreference
  - PushDevice
"""

from __future__ import annotations

import enum
from typing import Any

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.sql import func

from colab_common.db import Base


class NotificationType(str, enum.Enum):
    new_match = "new_match"
    new_request = "new_request"
    request_accepted = "request_accepted"
    chat_message = "chat_message"
    file_shared = "file_shared"
    ai_mockup_ready = "ai_mockup_ready"
    collab_nudge = "collab_nudge"
    collab_status_change = "collab_status_change"
    weekly_digest = "weekly_digest"
    support_reply = "support_reply"
    marketing = "marketing"


class NotificationChannel(str, enum.Enum):
    push = "push"
    email = "email"
    in_app = "in_app"


# Notification types that trigger email fallback when push is unreachable
KEY_NOTIFICATION_TYPES: set[str] = {
    NotificationType.new_match,
    NotificationType.request_accepted,
    NotificationType.ai_mockup_ready,
    NotificationType.collab_nudge,
    NotificationType.collab_status_change,
}

# Defaults: all ON except these
DEFAULT_OFF_TYPES: set[str] = {
    NotificationType.marketing,
    NotificationType.weekly_digest,
}


class Notification(Base):
    __tablename__ = "notification"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    type = Column(
        Enum(NotificationType, name="notification_type_enum", create_type=True),
        nullable=False,
    )
    payload = Column(JSONB, nullable=False, server_default="{}")
    in_app_seen_at = Column(DateTime(timezone=True), nullable=True)
    delivered_push_at = Column(DateTime(timezone=True), nullable=True)
    push_failed_at = Column(DateTime(timezone=True), nullable=True)
    push_failure_reason = Column(Text, nullable=True)
    delivered_email_at = Column(DateTime(timezone=True), nullable=True)
    email_failed_at = Column(DateTime(timezone=True), nullable=True)
    email_failure_reason = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        Index("idx_notification_user_type", "user_id", "type", "created_at"),
        Index(
            "idx_notification_unread",
            "user_id",
            "in_app_seen_at",
            postgresql_where="in_app_seen_at IS NULL",
        ),
    )


class NotificationPreference(Base):
    __tablename__ = "notification_preference"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    type = Column(
        Enum(NotificationType, name="notification_type_enum", create_type=False),
        nullable=False,
    )
    channel = Column(
        Enum(NotificationChannel, name="notification_channel_enum", create_type=True),
        nullable=False,
    )
    enabled = Column(Boolean, nullable=False, default=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("user_id", "type", "channel", name="uq_preference_user_type_channel"),
    )


class PushDevice(Base):
    __tablename__ = "push_device"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    device_id = Column(String(255), nullable=False)
    platform = Column(String(10), nullable=False)  # 'ios' | 'android'
    expo_push_token = Column(Text, nullable=True)
    device_token = Column(Text, nullable=True)  # raw APNs / FCM token (prod)
    sns_endpoint_arn = Column(Text, nullable=True)
    endpoint_enabled = Column(Boolean, nullable=False, default=True)
    prompt_dismissed_count = Column(String(5), nullable=False, default="0")
    app_version = Column(String(50), nullable=True)
    os_version = Column(String(50), nullable=True)
    last_seen_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("user_id", "device_id", name="uq_push_device_user_device"),
        Index(
            "idx_push_device_user_enabled",
            "user_id",
            postgresql_where="endpoint_enabled = TRUE",
        ),
    )
