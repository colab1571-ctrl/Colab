"""
chat-svc SQLAlchemy ORM models.

All tables live in the `chat` Postgres schema.
ChatMessage uses UUIDv7 for time-ordered primary keys.
Partitioned by created_at (monthly) for 3-year retention — see migration.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy.sql import func


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

RoomStateEnum = Enum(
    "open", "read_only", "archived",
    name="room_state", schema="chat",
)

MessageTypeEnum = Enum(
    "text", "voice", "image", "video", "audio", "doc", "link", "system",
    name="message_type", schema="chat",
)

ModerationStatusEnum = Enum(
    "pending", "allowed", "soft_warn", "hidden", "auto_hidden",
    name="moderation_status", schema="chat",
)


# ---------------------------------------------------------------------------
# Declarative Base
# ---------------------------------------------------------------------------


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# ChatRoom
# ---------------------------------------------------------------------------


class ChatRoom(Base):
    __tablename__ = "chat_room"
    __table_args__ = (
        Index("idx_chat_room_collaboration", "collaboration_id"),
        Index("idx_chat_room_participants", "participant_ids", postgresql_using="gin"),
        {"schema": "chat"},
    )

    id: uuid.UUID = Column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    collaboration_id: uuid.UUID = Column(
        UUID(as_uuid=True), nullable=False
    )
    # Array of exactly 2 profile UUIDs — enforced via CHECK in migration
    participant_ids: list[uuid.UUID] = Column(
        ARRAY(UUID(as_uuid=True)), nullable=False
    )
    state: str = Column(RoomStateEnum, nullable=False, default="open")
    created_at: datetime = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    archived_at: datetime | None = Column(DateTime(timezone=True), nullable=True)

    messages: list[ChatMessage] = relationship(
        "ChatMessage", back_populates="room", lazy="noload"
    )
    read_receipts: list[ChatReadReceipt] = relationship(
        "ChatReadReceipt", back_populates="room", lazy="noload"
    )


# ---------------------------------------------------------------------------
# ChatMessage (partitioned by created_at monthly — DDL in migration)
# ---------------------------------------------------------------------------


class ChatMessage(Base):
    __tablename__ = "chat_message"
    __table_args__ = (
        Index("idx_chat_msg_room_id", "room_id", "id"),
        Index("idx_chat_msg_sender", "sender_profile_id"),
        Index("idx_chat_msg_nonce", "client_nonce", postgresql_where="client_nonce IS NOT NULL"),
        {"schema": "chat"},
    )

    # UUIDv7 — time-ordered; must be supplied by application layer.
    # Note: partitioned table uses (id, created_at) composite PK in DDL.
    # SQLAlchemy ORM uses id as logical PK for query purposes.
    id: uuid.UUID = Column(UUID(as_uuid=True), primary_key=True)
    room_id: uuid.UUID = Column(
        UUID(as_uuid=True),
        # No ForeignKey here: Postgres partitioned tables don't support FK refs
        # to composite PKs cleanly; referential integrity enforced at app layer.
        nullable=False,
    )
    sender_profile_id: uuid.UUID = Column(UUID(as_uuid=True), nullable=False)
    type: str = Column(MessageTypeEnum, nullable=False)
    body: str | None = Column(Text, nullable=True)
    media_key: str | None = Column(Text, nullable=True)
    mime: str | None = Column(Text, nullable=True)
    size_bytes: int | None = Column(BigInteger, nullable=True)
    duration_ms: int | None = Column(Integer, nullable=True)
    reply_to: uuid.UUID | None = Column(
        UUID(as_uuid=True),
        # Self-referential reply; no FK on partitioned table — enforced at app layer.
        nullable=True,
    )
    client_nonce: uuid.UUID | None = Column(UUID(as_uuid=True), nullable=True)
    edited_at: datetime | None = Column(DateTime(timezone=True), nullable=True)
    deleted_at: datetime | None = Column(DateTime(timezone=True), nullable=True)
    moderation_score: float | None = Column(Float, nullable=True)
    moderation_status: str = Column(
        ModerationStatusEnum, nullable=False, default="pending"
    )
    created_at: datetime = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    room: ChatRoom = relationship("ChatRoom", back_populates="messages")
    revisions: list[ChatMessageRevision] = relationship(
        "ChatMessageRevision", back_populates="message", lazy="noload"
    )
    attachments: list[ChatAttachment] = relationship(
        "ChatAttachment", back_populates="message", lazy="noload"
    )


# ---------------------------------------------------------------------------
# ChatMessageRevision
# ---------------------------------------------------------------------------


class ChatMessageRevision(Base):
    __tablename__ = "chat_message_revision"
    __table_args__ = (
        UniqueConstraint("msg_id", "version", name="idx_revision_msg_version"),
        {"schema": "chat"},
    )

    id: int = Column(BigInteger, primary_key=True, autoincrement=True)
    msg_id: uuid.UUID = Column(
        UUID(as_uuid=True),
        nullable=False,  # References chat_message.id; no FK on partitioned table
    )
    version: int = Column(SmallInteger, nullable=False)
    body: str = Column(Text, nullable=False)
    edited_at: datetime = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    message: ChatMessage = relationship("ChatMessage", back_populates="revisions")


# ---------------------------------------------------------------------------
# ChatAttachment
# ---------------------------------------------------------------------------


class ChatAttachment(Base):
    __tablename__ = "chat_attachment"
    __table_args__ = {"schema": "chat"}

    id: uuid.UUID = Column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    msg_id: uuid.UUID = Column(
        UUID(as_uuid=True),
        nullable=False,  # References chat_message.id; no FK on partitioned table
    )
    kind: str = Column(Text, nullable=False)  # image|audio|video|doc|voice
    s3_key: str = Column(Text, nullable=False)
    signed_url_cache_until: datetime | None = Column(DateTime(timezone=True), nullable=True)
    signed_url_cache: str | None = Column(Text, nullable=True)

    message: ChatMessage = relationship("ChatMessage", back_populates="attachments")


# ---------------------------------------------------------------------------
# ChatReadReceipt
# ---------------------------------------------------------------------------


class ChatReadReceipt(Base):
    __tablename__ = "chat_read_receipt"
    __table_args__ = (
        UniqueConstraint("room_id", "profile_id", name="pk_chat_read_receipt"),
        {"schema": "chat"},
    )

    room_id: uuid.UUID = Column(
        UUID(as_uuid=True),
        ForeignKey("chat.chat_room.id"),  # chat_room has standard PK — FK is fine
        primary_key=True,
    )
    profile_id: uuid.UUID = Column(UUID(as_uuid=True), primary_key=True)
    last_read_msg_id: uuid.UUID | None = Column(UUID(as_uuid=True), nullable=True)
    last_read_at: datetime | None = Column(DateTime(timezone=True), nullable=True)

    room: ChatRoom = relationship("ChatRoom", back_populates="read_receipts")
