"""Conversation and message persistence.

Every method that can touch another user's row takes ``user_id`` and filters
on it explicitly - this is the service-layer ownership check the RLS
policies in migration 0004 back up, not a substitute for it. Both layers
must independently refuse cross-user access.
"""
import uuid
from typing import Any, Optional, Sequence

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.timeutils import utcnow
from backend.database.models.conversation import Conversation, Message


class ConversationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self, *, title: str, user_id: uuid.UUID, actor: Optional[str]
    ) -> Conversation:
        conversation = Conversation(title=title, user_id=user_id, actor=actor)
        self._session.add(conversation)
        await self._session.flush()
        return conversation

    async def get(
        self, conversation_id: uuid.UUID, *, user_id: uuid.UUID
    ) -> Optional[Conversation]:
        return await self._session.scalar(
            sa.select(Conversation).where(
                Conversation.id == conversation_id, Conversation.user_id == user_id
            )
        )

    async def list(
        self, *, user_id: uuid.UUID, page: int, page_size: int
    ) -> tuple[Sequence[Conversation], int]:
        filters = [Conversation.user_id == user_id]

        total = await self._session.scalar(
            sa.select(sa.func.count()).select_from(Conversation).where(*filters)
        )
        rows = await self._session.scalars(
            sa.select(Conversation)
            .where(*filters)
            .order_by(Conversation.updated_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(rows), int(total or 0)

    async def delete(self, conversation: Conversation) -> None:
        # Messages go with it: the FK is ON DELETE CASCADE and the relationship
        # is delete-orphan, so no orphaned message can survive.
        await self._session.delete(conversation)

    async def add_message(
        self,
        conversation: Conversation,
        *,
        role: str,
        content: str,
        provider: Optional[str] = None,
        intent: Optional[str] = None,
        meta: Optional[dict[str, Any]] = None,
    ) -> Message:
        message = Message(
            conversation_id=conversation.id,
            role=role,
            content=content,
            provider=provider,
            intent=intent,
            meta=meta,
        )
        self._session.add(message)
        # Adding a child row does not touch the parent, so the "most recently
        # used conversation" ordering has to be maintained explicitly.
        conversation.updated_at = utcnow()
        await self._session.flush()
        return message

    async def list_messages(
        self, conversation_id: uuid.UUID, *, user_id: uuid.UUID, page: int, page_size: int
    ) -> tuple[Sequence[Message], int]:
        base = (
            sa.select(Message)
            .join(Conversation, Conversation.id == Message.conversation_id)
            .where(
                Message.conversation_id == conversation_id,
                Conversation.user_id == user_id,
            )
        )
        total = await self._session.scalar(
            sa.select(sa.func.count()).select_from(base.subquery())
        )
        rows = await self._session.scalars(
            base.order_by(Message.created_at.asc(), Message.id.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(rows), int(total or 0)

    async def count_messages(self, *, user_id: uuid.UUID) -> int:
        total = await self._session.scalar(
            sa.select(sa.func.count())
            .select_from(Message)
            .join(Conversation, Conversation.id == Message.conversation_id)
            .where(Conversation.user_id == user_id)
        )
        return int(total or 0)

    async def recent_messages(
        self, conversation_id: uuid.UUID, *, user_id: uuid.UUID, limit: int
    ) -> Sequence[Message]:
        """Newest ``limit`` messages, returned oldest-first for prompting."""
        rows = await self._session.scalars(
            sa.select(Message)
            .join(Conversation, Conversation.id == Message.conversation_id)
            .where(
                Message.conversation_id == conversation_id,
                Conversation.user_id == user_id,
            )
            .order_by(Message.created_at.desc(), Message.id.desc())
            .limit(limit)
        )
        return list(reversed(list(rows)))
