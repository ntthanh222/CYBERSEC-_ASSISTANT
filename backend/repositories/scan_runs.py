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

    async def get_latest_completed(
        self, *, project_id: uuid.UUID, target: str
    ) -> Optional[ScanRun]:
        """The most recent ``completed`` run for this exact ``(project_id,
        target)`` pair - used by ``ScanOrchestrator.run_scan`` to
        auto-chain ``previous_scan_run_id`` so rescanning "just works"
        without the caller needing to track scan IDs (see Task 3 brief §2).
        Matches on the raw ``target`` string (not the normalized
        fingerprint target) since that is what a caller re-submits for a
        rescan of "the same" target - normalization only ever applies inside
        the fingerprint formula itself."""
        return await self._session.scalar(
            sa.select(ScanRun)
            .where(
                ScanRun.project_id == project_id,
                ScanRun.target == target,
                ScanRun.status == "completed",
            )
            .order_by(ScanRun.completed_at.desc(), ScanRun.created_at.desc())
            .limit(1)
        )

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

    async def get_latest_for_project(self, *, project_id: uuid.UUID) -> Optional[ScanRun]:
        """The most recent ``ScanRun`` for this project, any status/target -
        used by the Task 5 security dashboard's "Latest Scan" summary, unlike
        ``get_latest_completed`` which is scoped to a specific target and
        only ``completed`` runs."""
        return await self._session.scalar(
            sa.select(ScanRun)
            .where(ScanRun.project_id == project_id)
            .order_by(ScanRun.created_at.desc())
            .limit(1)
        )

    async def list_recent_completed(
        self, *, project_id: uuid.UUID, limit: int
    ) -> Sequence[ScanRun]:
        """The ``limit`` most recent ``completed`` scan runs for this
        project, oldest-first - feeds the Task 5 dashboard's "Security
        Trend" series (each point derived from that run's real, stored
        ``summary`` severity counts, nothing interpolated)."""
        rows = await self._session.scalars(
            sa.select(ScanRun)
            .where(ScanRun.project_id == project_id, ScanRun.status == "completed")
            .order_by(ScanRun.completed_at.desc())
            .limit(limit)
        )
        return list(reversed(list(rows)))

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
