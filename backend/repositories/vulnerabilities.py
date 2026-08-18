"""Vulnerability management persistence."""
import uuid
from typing import Any, Optional, Sequence

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database.models.vulnerability import VulnerabilityPatchTask, VulnerabilityRecord


class VulnerabilityRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, *, user_id: uuid.UUID, **values: Any) -> VulnerabilityRecord:
        record = VulnerabilityRecord(user_id=user_id, **values)
        self._session.add(record)
        await self._session.flush()
        return record

    async def get(
        self,
        vulnerability_id: uuid.UUID,
        *,
        user_id: uuid.UUID,
    ) -> Optional[VulnerabilityRecord]:
        return await self._session.scalar(
            sa.select(VulnerabilityRecord).where(
                VulnerabilityRecord.id == vulnerability_id,
                VulnerabilityRecord.user_id == user_id,
            )
        )

    async def get_by_cve(self, cve_id: str, *, user_id: uuid.UUID) -> Optional[VulnerabilityRecord]:
        return await self._session.scalar(
            sa.select(VulnerabilityRecord).where(
                VulnerabilityRecord.cve_id == cve_id,
                VulnerabilityRecord.user_id == user_id,
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
        watchlist: Optional[bool] = None,
    ) -> tuple[Sequence[VulnerabilityRecord], int]:
        filters: list[Any] = [VulnerabilityRecord.user_id == user_id]
        if search:
            pattern = f"%{search.lower()}%"
            filters.append(
                sa.or_(
                    sa.func.lower(VulnerabilityRecord.cve_id).like(pattern),
                    sa.func.lower(VulnerabilityRecord.title).like(pattern),
                )
            )
        if severity:
            filters.append(VulnerabilityRecord.severity == severity)
        if watchlist is not None:
            filters.append(VulnerabilityRecord.watchlist.is_(watchlist))
        total = await self._session.scalar(
            sa.select(sa.func.count()).select_from(VulnerabilityRecord).where(*filters)
        )
        rows = await self._session.scalars(
            sa.select(VulnerabilityRecord)
            .where(*filters)
            .order_by(VulnerabilityRecord.updated_date.desc(), VulnerabilityRecord.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(rows), int(total or 0)

    async def set_watchlist(
        self, vulnerability_id: uuid.UUID, *, user_id: uuid.UUID, watchlist: bool
    ) -> Optional[VulnerabilityRecord]:
        record = await self.get(vulnerability_id, user_id=user_id)
        if record is None:
            return None
        record.watchlist = watchlist
        await self._session.flush()
        return record


class PatchTaskRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, *, user_id: uuid.UUID, **values: Any) -> VulnerabilityPatchTask:
        record = VulnerabilityPatchTask(user_id=user_id, **values)
        self._session.add(record)
        await self._session.flush()
        return record

    async def get(
        self,
        task_id: uuid.UUID,
        *,
        user_id: uuid.UUID,
    ) -> Optional[VulnerabilityPatchTask]:
        return await self._session.scalar(
            sa.select(VulnerabilityPatchTask).where(
                VulnerabilityPatchTask.id == task_id,
                VulnerabilityPatchTask.user_id == user_id,
            )
        )

    async def list(
        self, *, user_id: uuid.UUID, page: int, page_size: int
    ) -> tuple[Sequence[tuple[VulnerabilityPatchTask, VulnerabilityRecord]], int]:
        filters = [VulnerabilityPatchTask.user_id == user_id]
        total = await self._session.scalar(
            sa.select(sa.func.count()).select_from(VulnerabilityPatchTask).where(*filters)
        )
        rows = await self._session.execute(
            sa.select(VulnerabilityPatchTask, VulnerabilityRecord)
            .join(
                VulnerabilityRecord,
                VulnerabilityRecord.id == VulnerabilityPatchTask.vulnerability_id,
            )
            .where(*filters, VulnerabilityRecord.user_id == user_id)
            .order_by(VulnerabilityPatchTask.updated_at.desc(), VulnerabilityPatchTask.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(rows.all()), int(total or 0)

    async def set_status(
        self, task_id: uuid.UUID, *, user_id: uuid.UUID, status: str
    ) -> Optional[VulnerabilityPatchTask]:
        record = await self.get(task_id, user_id=user_id)
        if record is None:
            return None
        record.status = status
        await self._session.flush()
        return record
