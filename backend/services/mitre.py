"""MITRE coverage service."""

import uuid
from typing import Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.audit import log_audit_event
from backend.core.exceptions import ConflictError, NotFoundError
from backend.repositories.mitre import MitreRepository


class MitreService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = MitreRepository(session)

    async def create(self, *, user_id: uuid.UUID, actor: Optional[str], **values):
        if values.get("incident_id") is None:
            existing = await self._repo.get_global_by_technique(
                values["technique_id"], user_id=user_id
            )
            if existing is not None:
                raise ConflictError("Kỹ thuật này đã được theo dõi.")
        try:
            record = await self._repo.create(user_id=user_id, **values)
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise ConflictError("Kỹ thuật này đã được theo dõi.") from exc
        log_audit_event(
            event_type="mitre",
            action="mitre_technique_created",
            resource=f"mitre:{record.id}",
            result="success",
            actor=actor,
            metadata={
                "technique_id": record.technique_id,
                "coverage_status": record.coverage_status,
            },
        )
        return record

    async def list(self, *, user_id: uuid.UUID, page: int, page_size: int, **filters):
        return await self._repo.list(user_id=user_id, page=page, page_size=page_size, **filters)

    async def get(self, record_id: uuid.UUID, *, user_id: uuid.UUID):
        record = await self._repo.get(record_id, user_id=user_id)
        if record is None:
            raise NotFoundError("Không tìm thấy kỹ thuật MITRE.")
        return record

    async def update(
        self,
        record_id: uuid.UUID,
        *,
        user_id: uuid.UUID,
        actor: Optional[str],
        values: dict,
    ):
        record = await self._repo.update(record_id, user_id=user_id, values=values)
        if record is None:
            raise NotFoundError("Không tìm thấy kỹ thuật MITRE.")
        await self._session.commit()
        log_audit_event(
            event_type="mitre",
            action="mitre_technique_updated",
            resource=f"mitre:{record.id}",
            result="success",
            actor=actor,
            metadata={"coverage_status": record.coverage_status},
        )
        return record
