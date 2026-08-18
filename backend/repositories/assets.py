"""Asset inventory persistence.

Every method that can touch another user's row takes ``user_id`` and filters
on it explicitly - the service-layer ownership check backing the RLS policy
in migration 0007, not a substitute for it.
"""
import uuid
from typing import Any, Optional, Sequence

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database.models.asset import Asset


class AssetRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        user_id: uuid.UUID,
        name: str,
        type: str,
        hostname: str,
        ip_address: str,
        operating_system: str,
        owner: str,
        department: str,
        business_criticality: str,
        internet_exposed: bool,
        description: str,
        linked_cves: list[str],
        patch_status: Optional[str],
        exploit_evidence: Optional[str],
    ) -> Asset:
        record = Asset(
            user_id=user_id,
            name=name,
            type=type,
            hostname=hostname,
            ip_address=ip_address,
            operating_system=operating_system,
            owner=owner,
            department=department,
            business_criticality=business_criticality,
            internet_exposed=internet_exposed,
            description=description,
            linked_cves=linked_cves,
            patch_status=patch_status,
            exploit_evidence=exploit_evidence,
        )
        self._session.add(record)
        await self._session.flush()
        return record

    async def get(self, asset_id: uuid.UUID, *, user_id: uuid.UUID) -> Optional[Asset]:
        return await self._session.scalar(
            sa.select(Asset).where(Asset.id == asset_id, Asset.user_id == user_id)
        )

    async def list(
        self,
        *,
        user_id: uuid.UUID,
        page: int,
        page_size: int,
        type: Optional[str] = None,
        business_criticality: Optional[str] = None,
        sort: str = "desc",
    ) -> tuple[Sequence[Asset], int]:
        filters: list[Any] = [Asset.user_id == user_id]
        if type is not None:
            filters.append(Asset.type == type)
        if business_criticality is not None:
            filters.append(Asset.business_criticality == business_criticality)

        total = await self._session.scalar(
            sa.select(sa.func.count()).select_from(Asset).where(*filters)
        )
        order = Asset.created_at.asc() if sort == "asc" else Asset.created_at.desc()
        rows = await self._session.scalars(
            sa.select(Asset)
            .where(*filters)
            .order_by(order, Asset.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(rows), int(total or 0)
