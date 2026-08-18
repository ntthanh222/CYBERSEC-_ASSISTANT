"""Threat intelligence IOC persistence."""
import uuid
from typing import Any, Optional, Sequence

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database.models.threat_intel import ThreatIOC


class ThreatIOCRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, *, user_id: uuid.UUID, **values: Any) -> ThreatIOC:
        record = ThreatIOC(user_id=user_id, **values)
        self._session.add(record)
        await self._session.flush()
        return record

    async def get(self, ioc_id: uuid.UUID, *, user_id: uuid.UUID) -> Optional[ThreatIOC]:
        return await self._session.scalar(
            sa.select(ThreatIOC).where(ThreatIOC.id == ioc_id, ThreatIOC.user_id == user_id)
        )

    async def list(
        self,
        *,
        user_id: uuid.UUID,
        page: int,
        page_size: int,
        search: Optional[str] = None,
        type: Optional[str] = None,
        severity: Optional[str] = None,
        watchlist: Optional[bool] = None,
    ) -> tuple[Sequence[ThreatIOC], int]:
        filters: list[Any] = [ThreatIOC.user_id == user_id]
        if search:
            pattern = f"%{search.lower()}%"
            filters.append(
                sa.or_(
                    sa.func.lower(ThreatIOC.value).like(pattern),
                    sa.func.lower(ThreatIOC.description).like(pattern),
                )
            )
        if type:
            filters.append(ThreatIOC.type == type)
        if severity:
            filters.append(ThreatIOC.severity == severity)
        if watchlist is not None:
            filters.append(ThreatIOC.watchlist.is_(watchlist))

        total = await self._session.scalar(
            sa.select(sa.func.count()).select_from(ThreatIOC).where(*filters)
        )
        rows = await self._session.scalars(
            sa.select(ThreatIOC)
            .where(*filters)
            .order_by(ThreatIOC.last_seen.desc(), ThreatIOC.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(rows), int(total or 0)

    async def set_watchlist(
        self, ioc_id: uuid.UUID, *, user_id: uuid.UUID, watchlist: bool
    ) -> Optional[ThreatIOC]:
        record = await self.get(ioc_id, user_id=user_id)
        if record is None:
            return None
        record.watchlist = watchlist
        await self._session.flush()
        return record
