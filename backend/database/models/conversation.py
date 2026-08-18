"""Assistant conversation and message models.

``Message.content`` is written **after** redaction
(:mod:`backend.services.redaction`): secret-shaped substrings never reach this
table, per the "chat content phải redacted trước khi lưu" rule in
``docs/05_DATA_MODEL.md``.
"""
import uuid
from typing import Any, Optional

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database.base import (
    Base,
    CreatedAtMixin,
    JSONVariant,
    TimestampMixin,
    UuidPrimaryKeyMixin,
    UuidType,
)

#: Roles a stored message may carry. ``system`` exists for future prompt
#: bookkeeping; nothing in Phase 2 writes it from user input.
MESSAGE_ROLES = ("user", "assistant", "system")


class Conversation(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "conversations"

    title: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    # Free-text audit hint only - never the ownership key. See user_id.
    actor: Mapped[Optional[str]] = mapped_column(sa.String(128), nullable=True)
    # Ownership: the Supabase Auth user (auth.users.id / JWT `sub`) this
    # conversation belongs to. Always set from the verified token
    # (backend.core.auth.AuthenticatedUser), never from client input. Row
    # Level Security policies on this table key on this column.
    user_id: Mapped[uuid.UUID] = mapped_column(UuidType, nullable=False)

    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Message.created_at",
    )

    __table_args__ = (
        sa.Index("ix_conversations_actor_updated_at", "actor", sa.text("updated_at DESC")),
        sa.Index("ix_conversations_user_id", "user_id"),
    )


class Message(UuidPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "messages"

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UuidType,
        sa.ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(sa.String(16), nullable=False)
    content: Mapped[str] = mapped_column(sa.Text, nullable=False)
    provider: Mapped[Optional[str]] = mapped_column(sa.String(64), nullable=True)
    intent: Mapped[Optional[str]] = mapped_column(sa.String(64), nullable=True)
    # Attribute is ``meta`` because ``metadata`` is reserved by SQLAlchemy's
    # declarative base; the underlying column keeps the contract name.
    meta: Mapped[Optional[dict[str, Any]]] = mapped_column(
        "metadata", JSONVariant, nullable=True
    )

    conversation: Mapped[Conversation] = relationship(back_populates="messages")

    __table_args__ = (
        sa.CheckConstraint(
            "role IN ('user', 'assistant', 'system')",
            name="ck_messages_role",
        ),
        sa.Index("ix_messages_conversation_id_created_at", "conversation_id", "created_at"),
    )
