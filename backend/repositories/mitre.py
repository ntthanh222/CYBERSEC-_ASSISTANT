"""MITRE coverage persistence."""

import uuid
from typing import Any, Optional, Sequence

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database.models.mitre import MitreTechniqueCoverage


class MitreRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, *, user_id: uuid.UUID, **values: Any) -> MitreTechniqueCoverage:
        record = MitreTechniqueCoverage(user_id=user_id, **values)
        self._session.add(record)
        await self._session.flush()
        return record

    async def get(
        self, record_id: uuid.UUID, *, user_id: uuid.UUID
    ) -> Optional[MitreTechniqueCoverage]:
        return await self._session.scalar(
            sa.select(MitreTechniqueCoverage).where(
                MitreTechniqueCoverage.id == record_id,
                MitreTechniqueCoverage.user_id == user_id,
            )
        )

    async def get_global_by_technique(
        self, technique_id: str, *, user_id: uuid.UUID
    ) -> Optional[MitreTechniqueCoverage]:
        return await self._session.scalar(
            sa.select(MitreTechniqueCoverage).where(
                MitreTechniqueCoverage.user_id == user_id,
                MitreTechniqueCoverage.technique_id == technique_id,
                MitreTechniqueCoverage.incident_id.is_(None),
            )
        )

    async def list(
        self,
        *,
        user_id: uuid.UUID,
        page: int,
        page_size: int,
        search: Optional[str] = None,
        tactic: Optional[str] = None,
        coverage_status: Optional[str] = None,
        incident_id: Optional[uuid.UUID] = None,
    ) -> tuple[Sequence[MitreTechniqueCoverage], int]:
        filters: list[Any] = [MitreTechniqueCoverage.user_id == user_id]
        if incident_id is not None:
            filters.append(MitreTechniqueCoverage.incident_id == incident_id)
        if search:
            pattern = f"%{search.lower()}%"
            filters.append(
                sa.or_(
                    sa.func.lower(MitreTechniqueCoverage.technique_id).like(pattern),
                    sa.func.lower(MitreTechniqueCoverage.name).like(pattern),
                    sa.func.lower(MitreTechniqueCoverage.description).like(pattern),
                )
            )
        if tactic:
            filters.append(MitreTechniqueCoverage.tactic == tactic)
        if coverage_status:
            filters.append(MitreTechniqueCoverage.coverage_status == coverage_status)
        total = await self._session.scalar(
            sa.select(sa.func.count()).select_from(MitreTechniqueCoverage).where(*filters)
        )
        rows = await self._session.scalars(
            sa.select(MitreTechniqueCoverage)
            .where(*filters)
            .order_by(MitreTechniqueCoverage.tactic, MitreTechniqueCoverage.technique_id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(rows), int(total or 0)

    async def update(
        self,
        record_id: uuid.UUID,
        *,
        user_id: uuid.UUID,
        values: dict[str, Any],
    ) -> Optional[MitreTechniqueCoverage]:
        record = await self.get(record_id, user_id=user_id)
        if record is None:
            return None
        for key, value in values.items():
            setattr(record, key, value)
        await self._session.flush()
        return record
