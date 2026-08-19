"""Workspace persistence."""
import uuid
from typing import Optional, Sequence

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database.models.workspace import Workspace, WorkspaceMember


class WorkspaceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self, *, name: str, description: Optional[str], created_by_user_id: uuid.UUID
    ) -> Workspace:
        record = Workspace(name=name, description=description, created_by_user_id=created_by_user_id)
        self._session.add(record)
        await self._session.flush()
        return record

    async def get(self, workspace_id: uuid.UUID) -> Optional[Workspace]:
        return await self._session.scalar(
            sa.select(Workspace).where(Workspace.id == workspace_id)
        )

    async def list_for_user(
        self,
        *,
        user_id: uuid.UUID,
        is_global_admin: bool,
        page: int,
        page_size: int,
    ) -> tuple[Sequence[Workspace], int]:
        """Workspaces the caller is a member of, or every workspace for a
        global admin/super_admin."""
        if is_global_admin:
            stmt = sa.select(Workspace)
            count_stmt = sa.select(sa.func.count()).select_from(Workspace)
        else:
            stmt = (
                sa.select(Workspace)
                .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
                .where(WorkspaceMember.user_id == user_id)
            )
            count_stmt = (
                sa.select(sa.func.count())
                .select_from(Workspace)
                .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
                .where(WorkspaceMember.user_id == user_id)
            )

        total = await self._session.scalar(count_stmt)
        rows = await self._session.scalars(
            stmt.order_by(Workspace.created_at.desc(), Workspace.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(rows), int(total or 0)

    async def update(
        self, workspace: Workspace, *, name: Optional[str] = None, description: Optional[str] = None
    ) -> Workspace:
        if name is not None:
            workspace.name = name
        if description is not None:
            workspace.description = description
        await self._session.flush()
        return workspace
