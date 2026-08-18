"""Incident persistence."""

import uuid
from typing import Any, Optional, Sequence

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database.models.incident import IncidentRecord, IncidentTask, IncidentTimelineEvent


class IncidentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, *, user_id: uuid.UUID, **values: Any) -> IncidentRecord:
        record = IncidentRecord(user_id=user_id, **values)
        self._session.add(record)
        await self._session.flush()
        return record

    async def get(self, incident_id: uuid.UUID, *, user_id: uuid.UUID) -> Optional[IncidentRecord]:
        return await self._session.scalar(
            sa.select(IncidentRecord).where(
                IncidentRecord.id == incident_id,
                IncidentRecord.user_id == user_id,
            )
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
    ) -> tuple[Sequence[IncidentRecord], int]:
        filters: list[Any] = [IncidentRecord.user_id == user_id]
        if search:
            pattern = f"%{search.lower()}%"
            filters.append(
                sa.or_(
                    sa.func.lower(IncidentRecord.title).like(pattern),
                    sa.func.lower(IncidentRecord.description).like(pattern),
                    sa.func.lower(IncidentRecord.asset_name).like(pattern),
                )
            )
        if severity:
            filters.append(IncidentRecord.severity == severity)
        if status:
            filters.append(IncidentRecord.status == status)
        total = await self._session.scalar(
            sa.select(sa.func.count()).select_from(IncidentRecord).where(*filters)
        )
        rows = await self._session.scalars(
            sa.select(IncidentRecord)
            .where(*filters)
            .order_by(IncidentRecord.created_at.desc(), IncidentRecord.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(rows), int(total or 0)

    async def set_status(
        self, incident_id: uuid.UUID, *, user_id: uuid.UUID, status: str, closed_at
    ) -> Optional[IncidentRecord]:
        record = await self.get(incident_id, user_id=user_id)
        if record is None:
            return None
        record.status = status
        record.closed_at = closed_at
        await self._session.flush()
        return record


class IncidentTaskRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self, *, user_id: uuid.UUID, incident_id: uuid.UUID, **values: Any
    ) -> IncidentTask:
        task = IncidentTask(user_id=user_id, incident_id=incident_id, **values)
        self._session.add(task)
        await self._session.flush()
        return task

    async def get(self, task_id: uuid.UUID, *, user_id: uuid.UUID) -> Optional[IncidentTask]:
        return await self._session.scalar(
            sa.select(IncidentTask).where(
                IncidentTask.id == task_id, IncidentTask.user_id == user_id
            )
        )

    async def list_for_incident(
        self, incident_id: uuid.UUID, *, user_id: uuid.UUID
    ) -> Sequence[IncidentTask]:
        rows = await self._session.scalars(
            sa.select(IncidentTask)
            .where(IncidentTask.incident_id == incident_id, IncidentTask.user_id == user_id)
            .order_by(IncidentTask.created_at, IncidentTask.id)
        )
        return list(rows)

    async def set_status(
        self, task_id: uuid.UUID, *, user_id: uuid.UUID, status: str
    ) -> Optional[IncidentTask]:
        task = await self.get(task_id, user_id=user_id)
        if task is None:
            return None
        task.status = status
        await self._session.flush()
        return task


class IncidentTimelineRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        user_id: uuid.UUID,
        incident_id: uuid.UUID,
        event_type: str,
        message: str,
        actor: Optional[str],
    ) -> IncidentTimelineEvent:
        event = IncidentTimelineEvent(
            user_id=user_id,
            incident_id=incident_id,
            event_type=event_type,
            message=message,
            actor=actor or "",
        )
        self._session.add(event)
        await self._session.flush()
        return event

    async def list_for_incident(
        self, incident_id: uuid.UUID, *, user_id: uuid.UUID
    ) -> Sequence[IncidentTimelineEvent]:
        rows = await self._session.scalars(
            sa.select(IncidentTimelineEvent)
            .where(
                IncidentTimelineEvent.incident_id == incident_id,
                IncidentTimelineEvent.user_id == user_id,
            )
            .order_by(IncidentTimelineEvent.created_at.desc(), IncidentTimelineEvent.id)
        )
        return list(rows)
