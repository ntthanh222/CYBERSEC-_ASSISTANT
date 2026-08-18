"""Alert persistence."""
import uuid
from typing import Any, Optional, Sequence

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database.models.alert import AlertRecord


class AlertRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, *, user_id: uuid.UUID, **values: Any) -> AlertRecord:
        record = AlertRecord(user_id=user_id, **values)
        self._session.add(record)
        await self._session.flush()
        return record

    async def get(self, alert_id: uuid.UUID, *, user_id: uuid.UUID) -> Optional[AlertRecord]:
        return await self._session.scalar(
            sa.select(AlertRecord).where(AlertRecord.id == alert_id, AlertRecord.user_id == user_id)
        )

    async def list(
        self,
        *,
        user_id: uuid.UUID,
        page: int,
        page_size: int,
        search: Optional[str] = None,
        severity: Optional[str] = None,
        status: Optional[str] = None,
    ) -> tuple[Sequence[AlertRecord], int]:
        filters: list[Any] = [AlertRecord.user_id == user_id]
        if search:
            pattern = f"%{search.lower()}%"
            filters.append(
                sa.or_(
                    sa.func.lower(AlertRecord.title).like(pattern),
                    sa.func.lower(AlertRecord.description).like(pattern),
                )
            )
        if severity:
            filters.append(AlertRecord.severity == severity)
        if status:
            filters.append(AlertRecord.status == status)
        total = await self._session.scalar(
            sa.select(sa.func.count()).select_from(AlertRecord).where(*filters)
        )
        rows = await self._session.scalars(
            sa.select(AlertRecord)
            .where(*filters)
            .order_by(AlertRecord.created_at.desc(), AlertRecord.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(rows), int(total or 0)

    async def set_status(
        self, alert_id: uuid.UUID, *, user_id: uuid.UUID, status: str
    ) -> Optional[AlertRecord]:
        record = await self.get(alert_id, user_id=user_id)
        if record is None:
            return None
        record.status = status
        await self._session.flush()
        return record
