"""Reports persistence."""

import uuid
from typing import Any, Optional, Sequence

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database.models.report import ReportRecord


class ReportRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, *, user_id: uuid.UUID, **values: Any) -> ReportRecord:
        record = ReportRecord(user_id=user_id, **values)
        self._session.add(record)
        await self._session.flush()
        return record

    async def get(self, report_id: uuid.UUID, *, user_id: uuid.UUID) -> Optional[ReportRecord]:
        return await self._session.scalar(
            sa.select(ReportRecord).where(
                ReportRecord.id == report_id, ReportRecord.user_id == user_id
            )
        )

    async def list(
        self,
        *,
        user_id: uuid.UUID,
        page: int,
        page_size: int,
        category: Optional[str] = None,
    ) -> tuple[Sequence[ReportRecord], int]:
        filters: list[Any] = [ReportRecord.user_id == user_id]
        if category:
            filters.append(ReportRecord.category == category)
        total = await self._session.scalar(
            sa.select(sa.func.count()).select_from(ReportRecord).where(*filters)
        )
        rows = await self._session.scalars(
            sa.select(ReportRecord)
            .where(*filters)
            .order_by(ReportRecord.created_at.desc(), ReportRecord.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(rows), int(total or 0)
