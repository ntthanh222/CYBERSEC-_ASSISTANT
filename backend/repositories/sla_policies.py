"""SlaPolicy persistence (Task 3)."""
import uuid
from typing import Optional, Sequence

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database.models.sla_policy import SlaPolicy


class SlaPolicyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_global(self) -> Sequence[SlaPolicy]:
        rows = await self._session.scalars(
            sa.select(SlaPolicy).where(SlaPolicy.project_id.is_(None)).order_by(SlaPolicy.severity)
        )
        return list(rows)

    async def get_global(self, severity: str) -> Optional[SlaPolicy]:
        return await self._session.scalar(
            sa.select(SlaPolicy).where(
                SlaPolicy.project_id.is_(None), SlaPolicy.severity == severity
            )
        )

    async def upsert_global(self, *, severity: str, hours_to_deadline: int) -> SlaPolicy:
        policy = await self.get_global(severity)
        if policy is None:
            policy = SlaPolicy(project_id=None, severity=severity, hours_to_deadline=hours_to_deadline)
            self._session.add(policy)
        else:
            policy.hours_to_deadline = hours_to_deadline
        await self._session.flush()
        return policy

    async def list_project_overrides(self, project_id: uuid.UUID) -> Sequence[SlaPolicy]:
        rows = await self._session.scalars(
            sa.select(SlaPolicy)
            .where(SlaPolicy.project_id == project_id)
            .order_by(SlaPolicy.severity)
        )
        return list(rows)

    async def get_project_override(
        self, *, project_id: uuid.UUID, severity: str
    ) -> Optional[SlaPolicy]:
        return await self._session.scalar(
            sa.select(SlaPolicy).where(
                SlaPolicy.project_id == project_id, SlaPolicy.severity == severity
            )
        )

    async def upsert_project_override(
        self, *, project_id: uuid.UUID, severity: str, hours_to_deadline: int
    ) -> SlaPolicy:
        policy = await self.get_project_override(project_id=project_id, severity=severity)
        if policy is None:
            policy = SlaPolicy(
                project_id=project_id, severity=severity, hours_to_deadline=hours_to_deadline
            )
            self._session.add(policy)
        else:
            policy.hours_to_deadline = hours_to_deadline
        await self._session.flush()
        return policy

    async def delete_project_override(self, *, project_id: uuid.UUID, severity: str) -> bool:
        policy = await self.get_project_override(project_id=project_id, severity=severity)
        if policy is None:
            return False
        await self._session.delete(policy)
        await self._session.flush()
        return True
