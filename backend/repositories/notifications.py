"""Notification center persistence."""

import uuid
from typing import Any, Optional, Sequence

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database.models.notification import NotificationRecord


class NotificationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, *, user_id: uuid.UUID, **values: Any) -> NotificationRecord:
        record = NotificationRecord(user_id=user_id, **values)
        self._session.add(record)
        await self._session.flush()
        return record

    async def get(
        self, notification_id: uuid.UUID, *, user_id: uuid.UUID
    ) -> Optional[NotificationRecord]:
        return await self._session.scalar(
            sa.select(NotificationRecord).where(
                NotificationRecord.id == notification_id, NotificationRecord.user_id == user_id
            )
        )

    async def list(
        self,
        *,
        user_id: uuid.UUID,
        page: int,
        page_size: int,
        unread_only: bool = False,
    ) -> tuple[Sequence[NotificationRecord], int, int]:
        filters: list[Any] = [NotificationRecord.user_id == user_id]
        if unread_only:
            filters.append(NotificationRecord.is_read.is_(False))
        total = await self._session.scalar(
            sa.select(sa.func.count()).select_from(NotificationRecord).where(*filters)
        )
        unread_count = await self._session.scalar(
            sa.select(sa.func.count())
            .select_from(NotificationRecord)
            .where(NotificationRecord.user_id == user_id, NotificationRecord.is_read.is_(False))
        )
        rows = await self._session.scalars(
            sa.select(NotificationRecord)
            .where(*filters)
            .order_by(NotificationRecord.created_at.desc(), NotificationRecord.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(rows), int(total or 0), int(unread_count or 0)

    async def set_read(self, record: NotificationRecord, *, is_read: bool) -> NotificationRecord:
        record.is_read = is_read
        await self._session.flush()
        return record
