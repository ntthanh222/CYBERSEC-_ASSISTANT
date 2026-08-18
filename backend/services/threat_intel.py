"""Threat intelligence IOC service."""
from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.audit import log_audit_event
from backend.core.exceptions import ConflictError, InvalidRequestError, NotFoundError
from backend.core.timeutils import utcnow
from backend.database.models.threat_intel import ThreatIOC
from backend.repositories.threat_intel import ThreatIOCRepository


class ThreatIOCService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = ThreatIOCRepository(session)

    async def create(self, *, user_id: uuid.UUID, actor: Optional[str], **values) -> ThreatIOC:
        if values["last_seen"] < values["first_seen"]:
            raise InvalidRequestError("Thời điểm phát hiện cuối không thể trước thời điểm phát hiện đầu.")
        try:
            record = await self._repo.create(user_id=user_id, **values)
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise ConflictError("Chỉ báo này đã tồn tại.") from exc
        except Exception:
            await self._session.rollback()
            raise
        log_audit_event(
            event_type="threat_intel",
            action="ioc_created",
            resource=f"threat_ioc:{record.id}",
            result="success",
            actor=actor,
            metadata={"type": record.type, "severity": record.severity},
        )
        return record

    async def get(self, ioc_id: uuid.UUID, *, user_id: uuid.UUID) -> ThreatIOC:
        record = await self._repo.get(ioc_id, user_id=user_id)
        if record is None:
            raise NotFoundError("Không tìm thấy chỉ báo.")
        return record

    async def list(self, *, user_id: uuid.UUID, page: int, page_size: int, **filters):
        return await self._repo.list(user_id=user_id, page=page, page_size=page_size, **filters)

    async def summary(self, *, user_id: uuid.UUID) -> tuple[dict, list[ThreatIOC]]:
        items, total = await self._repo.list(user_id=user_id, page=1, page_size=5)
        all_items, _ = await self._repo.list(user_id=user_id, page=1, page_size=500)
        cutoff = utcnow() - timedelta(hours=48)
        recent_count = 0
        for item in all_items:
            first_seen = item.first_seen
            if first_seen.tzinfo is None:
                first_seen = first_seen.replace(tzinfo=cutoff.tzinfo)
            if first_seen >= cutoff:
                recent_count += 1
        return (
            {
                "total": total,
                "critical": sum(1 for item in all_items if item.severity == "critical"),
                "watchlist": sum(1 for item in all_items if item.watchlist),
                "recent_48h": recent_count,
            },
            list(items),
        )

    async def set_watchlist(
        self, ioc_id: uuid.UUID, *, user_id: uuid.UUID, watchlist: bool, actor: Optional[str]
    ) -> ThreatIOC:
        record = await self._repo.set_watchlist(ioc_id, user_id=user_id, watchlist=watchlist)
        if record is None:
            raise NotFoundError("Không tìm thấy chỉ báo.")
        await self._session.commit()
        log_audit_event(
            event_type="threat_intel",
            action="ioc_watchlist_updated",
            resource=f"threat_ioc:{record.id}",
            result="success",
            actor=actor,
            metadata={"watchlist": record.watchlist},
        )
        return record
