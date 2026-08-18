"""Security scan history persistence.

Every method that can touch another user's row takes ``user_id`` and filters
on it explicitly - the service-layer ownership check backing the RLS
policies in migration 0004, not a substitute for them.
"""
import uuid
from typing import Any, Optional, Sequence

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database.models.scan_history import SecurityScanRecord


class ScanHistoryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        scan_type: str,
        target: str,
        status: str,
        summary: str,
        user_id: uuid.UUID,
        risk_score: Optional[int] = None,
        severity: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
        actor: Optional[str] = None,
    ) -> SecurityScanRecord:
        record = SecurityScanRecord(
            scan_type=scan_type,
            target=target,
            status=status,
            summary=summary,
            user_id=user_id,
            risk_score=risk_score,
            severity=severity,
            details=details,
            actor=actor,
        )
        self._session.add(record)
        await self._session.flush()
        return record

    async def get(
        self, record_id: uuid.UUID, *, user_id: uuid.UUID
    ) -> Optional[SecurityScanRecord]:
        return await self._session.scalar(
            sa.select(SecurityScanRecord).where(
                SecurityScanRecord.id == record_id, SecurityScanRecord.user_id == user_id
            )
        )

    async def list(
        self,
        *,
        user_id: uuid.UUID,
        page: int,
        page_size: int,
        scan_type: Optional[str] = None,
        status: Optional[str] = None,
        severity: Optional[str] = None,
        sort: str = "desc",
    ) -> tuple[Sequence[SecurityScanRecord], int]:
        filters = [SecurityScanRecord.user_id == user_id]
        if scan_type is not None:
            filters.append(SecurityScanRecord.scan_type == scan_type)
        if status is not None:
            filters.append(SecurityScanRecord.status == status)
        if severity is not None:
            filters.append(SecurityScanRecord.severity == severity)

        total = await self._session.scalar(
            sa.select(sa.func.count()).select_from(SecurityScanRecord).where(*filters)
        )
        order = (
            SecurityScanRecord.created_at.asc()
            if sort == "asc"
            else SecurityScanRecord.created_at.desc()
        )
        rows = await self._session.scalars(
            sa.select(SecurityScanRecord)
            .where(*filters)
            .order_by(order, SecurityScanRecord.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(rows), int(total or 0)

    async def delete(self, record: SecurityScanRecord) -> None:
        await self._session.delete(record)
