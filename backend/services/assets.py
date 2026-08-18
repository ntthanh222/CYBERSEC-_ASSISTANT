"""Asset inventory business logic - a thin layer over the repository.

Kept separate from the repository so routes never touch SQLAlchemy directly,
per the "route chỉ validate, authorize và gọi service" rule in
``docs/02_ARCHITECTURE_TARGET.md``.
"""
import uuid
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.audit import log_audit_event
from backend.core.exceptions import NotFoundError
from backend.database.models.asset import Asset
from backend.repositories.assets import AssetRepository


class AssetService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = AssetRepository(session)

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
        actor: Optional[str],
    ) -> Asset:
        record = await self._repo.create(
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
        await self._session.commit()
        log_audit_event(
            event_type="asset",
            action="asset_created",
            resource=f"asset:{record.id}",
            result="success",
            actor=actor,
            metadata={"type": record.type, "business_criticality": record.business_criticality},
        )
        return record

    async def get(self, asset_id: uuid.UUID, *, user_id: uuid.UUID) -> Asset:
        record = await self._repo.get(asset_id, user_id=user_id)
        if record is None:
            raise NotFoundError("Không tìm thấy tài sản.")
        return record

    async def list(
        self,
        *,
        user_id: uuid.UUID,
        page: int,
        page_size: int,
        type: Optional[str] = None,
        business_criticality: Optional[str] = None,
        sort: str = "desc",
    ):
        return await self._repo.list(
            user_id=user_id,
            page=page,
            page_size=page_size,
            type=type,
            business_criticality=business_criticality,
            sort=sort,
        )
