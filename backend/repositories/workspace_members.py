"""Workspace membership persistence."""
import uuid
from typing import Optional, Sequence

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database.models.workspace import WorkspaceMember


class WorkspaceMemberRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(
        self, *, workspace_id: uuid.UUID, user_id: uuid.UUID, workspace_role: str
    ) -> WorkspaceMember:
        record = WorkspaceMember(
            workspace_id=workspace_id, user_id=user_id, workspace_role=workspace_role
        )
        self._session.add(record)
        await self._session.flush()
        return record

    async def get(
        self, *, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> Optional[WorkspaceMember]:
        return await self._session.scalar(
            sa.select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == user_id,
            )
        )

    async def list(self, *, workspace_id: uuid.UUID) -> Sequence[WorkspaceMember]:
        rows = await self._session.scalars(
            sa.select(WorkspaceMember)
            .where(WorkspaceMember.workspace_id == workspace_id)
            .order_by(WorkspaceMember.created_at.asc())
        )
        return list(rows)

    async def count_by_role(self, *, workspace_id: uuid.UUID, role: str) -> int:
        result = await self._session.scalar(
            sa.select(sa.func.count())
            .select_from(WorkspaceMember)
            .where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.workspace_role == role,
            )
        )
        return int(result or 0)

    async def update_role(self, member: WorkspaceMember, *, workspace_role: str) -> WorkspaceMember:
        member.workspace_role = workspace_role
        await self._session.flush()
        return member

    async def remove(self, member: WorkspaceMember) -> None:
        await self._session.delete(member)
        await self._session.flush()
