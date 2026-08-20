"""Project membership persistence.

``list_by_role`` exists specifically so a later phase (Task 2's Finding
assignment) can query "who are the developers on this project" without
reaching into the ORM model directly - see the Task 1 brief's sequencing
note.
"""
import uuid
from typing import Optional, Sequence

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database.models.project import ProjectMember


class ProjectMemberRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(
        self, *, project_id: uuid.UUID, user_id: uuid.UUID, project_role: str
    ) -> ProjectMember:
        record = ProjectMember(project_id=project_id, user_id=user_id, project_role=project_role)
        self._session.add(record)
        await self._session.flush()
        return record

    async def get(self, *, project_id: uuid.UUID, user_id: uuid.UUID) -> Optional[ProjectMember]:
        return await self._session.scalar(
            sa.select(ProjectMember).where(
                ProjectMember.project_id == project_id,
                ProjectMember.user_id == user_id,
            )
        )

    async def list(self, *, project_id: uuid.UUID) -> Sequence[ProjectMember]:
        rows = await self._session.scalars(
            sa.select(ProjectMember)
            .where(ProjectMember.project_id == project_id)
            .order_by(ProjectMember.created_at.asc())
        )
        return list(rows)

    async def list_by_role(
        self, *, project_id: uuid.UUID, project_role: str
    ) -> Sequence[ProjectMember]:
        """Members of ``project_id`` with a given ``project_role`` (e.g.
        ``"developer"``) - the lookup a Finding-assignment picker needs."""
        rows = await self._session.scalars(
            sa.select(ProjectMember)
            .where(
                ProjectMember.project_id == project_id,
                ProjectMember.project_role == project_role,
            )
            .order_by(ProjectMember.created_at.asc())
        )
        return list(rows)

    async def list_by_roles(
        self, *, project_id: uuid.UUID, project_roles: Sequence[str]
    ) -> Sequence[ProjectMember]:
        """Members of ``project_id`` whose ``project_role`` is any of
        ``project_roles`` - the eligible-assignee picker (Task 4) needs
        "developer OR security OR owner" in one query rather than three
        calls to ``list_by_role``."""
        rows = await self._session.scalars(
            sa.select(ProjectMember)
            .where(
                ProjectMember.project_id == project_id,
                ProjectMember.project_role.in_(project_roles),
            )
            .order_by(ProjectMember.created_at.asc())
        )
        return list(rows)

    async def count_by_role(self, *, project_id: uuid.UUID, role: str) -> int:
        result = await self._session.scalar(
            sa.select(sa.func.count())
            .select_from(ProjectMember)
            .where(ProjectMember.project_id == project_id, ProjectMember.project_role == role)
        )
        return int(result or 0)

    async def count_all(self, *, project_id: uuid.UUID) -> int:
        """Every member regardless of role - the admin projects list's
        "member count" column (Task 7)."""
        result = await self._session.scalar(
            sa.select(sa.func.count())
            .select_from(ProjectMember)
            .where(ProjectMember.project_id == project_id)
        )
        return int(result or 0)

    async def update_role(self, member: ProjectMember, *, project_role: str) -> ProjectMember:
        member.project_role = project_role
        await self._session.flush()
        return member

    async def remove(self, member: ProjectMember) -> None:
        await self._session.delete(member)
        await self._session.flush()
