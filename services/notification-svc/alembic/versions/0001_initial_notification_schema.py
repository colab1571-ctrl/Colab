"""Initial notification schema: enums + Notification + NotificationPreference + PushDevice.

Revision ID: 0001
Revises:
Create Date: 2026-05-11
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- Enums ---
    op.execute("""
        CREATE TYPE notification_type_enum AS ENUM (
            'new_match',
            'new_request',
            'request_accepted',
            'chat_message',
            'file_shared',
            'ai_mockup_ready',
            'collab_nudge',
            'collab_status_change',
            'weekly_digest',
            'support_reply',
            'marketing'
        )
    """)

    op.execute("""
        CREATE TYPE notification_channel_enum AS ENUM ('push', 'email', 'in_app')
    """)

    # --- Notification table ---
    op.create_table(
        "notification",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("type", sa.Enum(name="notification_type_enum", create_type=False), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("in_app_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_push_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("push_failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("push_failure_reason", sa.Text(), nullable=True),
        sa.Column("delivered_email_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("email_failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("email_failure_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
    )
    op.create_index("idx_notification_user_type", "notification", ["user_id", "type", "created_at"])
    op.create_index(
        "idx_notification_unread",
        "notification",
        ["user_id", "in_app_seen_at"],
        postgresql_where=sa.text("in_app_seen_at IS NULL"),
    )

    # --- NotificationPreference table ---
    op.create_table(
        "notification_preference",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("type", sa.Enum(name="notification_type_enum", create_type=False), nullable=False),
        sa.Column("channel", sa.Enum(name="notification_channel_enum", create_type=False), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("TRUE")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.UniqueConstraint("user_id", "type", "channel", name="uq_preference_user_type_channel"),
    )
    op.create_index("idx_preference_user", "notification_preference", ["user_id"])

    # --- PushDevice table ---
    op.create_table(
        "push_device",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("device_id", sa.String(255), nullable=False),
        sa.Column("platform", sa.String(10), nullable=False),
        sa.Column("expo_push_token", sa.Text(), nullable=True),
        sa.Column("device_token", sa.Text(), nullable=True),
        sa.Column("sns_endpoint_arn", sa.Text(), nullable=True),
        sa.Column("endpoint_enabled", sa.Boolean(), nullable=False, server_default=sa.text("TRUE")),
        sa.Column("prompt_dismissed_count", sa.String(5), nullable=False, server_default="0"),
        sa.Column("app_version", sa.String(50), nullable=True),
        sa.Column("os_version", sa.String(50), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.UniqueConstraint("user_id", "device_id", name="uq_push_device_user_device"),
    )
    op.create_index(
        "idx_push_device_user_enabled",
        "push_device",
        ["user_id"],
        postgresql_where=sa.text("endpoint_enabled = TRUE"),
    )

    # Add platform CHECK constraint
    op.execute("ALTER TABLE push_device ADD CONSTRAINT chk_push_device_platform CHECK (platform IN ('ios', 'android'))")


def downgrade() -> None:
    op.drop_table("push_device")
    op.drop_table("notification_preference")
    op.drop_table("notification")
    op.execute("DROP TYPE IF EXISTS notification_channel_enum")
    op.execute("DROP TYPE IF EXISTS notification_type_enum")
