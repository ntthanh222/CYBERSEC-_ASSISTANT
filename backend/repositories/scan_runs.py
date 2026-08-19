"""ScanRun persistence."""
import uuid
from datetime import datetime
from typing import Any, Optional, Sequence

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database.models.scan import ScanRun


class ScanRunRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        project_id: uuid.UUID,
        triggered_by_user_id: uuid.UUID,
        scan_type: str,
        target: str,
        status: str,
        started_at: Optional[datetime],
        previous_scan_run_id: Optional[uuid.UUID] = None,
    ) -> ScanRun:
        record = ScanRun(
            project_id=project_id,
            triggered_by_user_id=triggered_by_user_id,
            scan_type=scan_type,
            target=target,
            status=status,
            started_at=started_at,
            summary={},
            previous_scan_run_id=previous_scan_run_id,
        )
        self._session.add(record)
        await self._session.flush()
        return record

    async def get(self, scan_run_id: uuid.UUID) -> Optional[ScanRun]:
        return await self._session.scalar(sa.select(ScanRun).where(ScanRun.id == scan_run_id))

    async def list_for_project(
        self, *, project_id: uuid.UUID, page: int, page_size: int
    ) -> tuple[Sequence[ScanRun], int]:
        total = await self._session.scalar(
            sa.select(sa.func.count()).select_from(ScanRun).where(ScanRun.project_id == project_id)
        )
        rows = await self._session.scalars(
            sa.select(ScanRun)
            .where(ScanRun.project_id == project_id)
            .order_by(ScanRun.created_at.desc(), ScanRun.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(rows), int(total or 0)

    async def mark_completed(
        self, scan_run: ScanRun, *, completed_at: datetime, summary: dict[str, Any]
    ) -> ScanRun:
        scan_run.status = "completed"
        scan_run.completed_at = completed_at
        scan_run.summary = summary
        await self._session.flush()
        return scan_run

    async def mark_failed(
        self, scan_run: ScanRun, *, completed_at: datetime, summary: dict[str, Any]
    ) -> ScanRun:
        scan_run.status = "failed"
        scan_run.completed_at = completed_at
        scan_run.summary = summary
        await self._session.flush()
        return scan_run
