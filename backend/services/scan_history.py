"""Scan history business logic - a thin layer over the repository.

Kept separate from the repository so routes never touch SQLAlchemy directly,
per the "route chỉ validate, authorize và gọi service" rule in
``docs/02_ARCHITECTURE_TARGET.md``.
"""
import uuid
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.audit import log_audit_event
from backend.core.exceptions import NotFoundError
from backend.database.models.scan_history import SecurityScanRecord
from backend.repositories.scan_history import ScanHistoryRepository


class ScanHistoryService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = ScanHistoryRepository(session)

    async def record(
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
        record = await self._repo.create(
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
        await self._session.commit()
        return record

    async def get(self, record_id: uuid.UUID, *, user_id: uuid.UUID) -> SecurityScanRecord:
        record = await self._repo.get(record_id, user_id=user_id)
        if record is None:
            raise NotFoundError("Không tìm thấy bản ghi lịch sử quét.")
        return record

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
    ):
        return await self._repo.list(
            user_id=user_id,
            page=page,
            page_size=page_size,
            scan_type=scan_type,
            status=status,
            severity=severity,
            sort=sort,
        )

    async def delete(
        self, record_id: uuid.UUID, *, user_id: uuid.UUID, actor: Optional[str]
    ) -> None:
        record = await self.get(record_id, user_id=user_id)
        await self._repo.delete(record)
        await self._session.commit()
        log_audit_event(
            event_type="scan_history",
            action="record_deleted",
            resource=f"scan_history:{record_id}",
            result="success",
            actor=actor,
            metadata={"scan_type": record.scan_type},
        )
