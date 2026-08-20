"""Project persistence."""
import uuid
from datetime import datetime
from typing import Any, Optional, Sequence

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database.models.project import Project, ProjectMember
from backend.database.models.workspace import WorkspaceMember


class ProjectRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        workspace_id: uuid.UUID,
        name: str,
        domain: Optional[str],
        environment: str,
        criticality: str,
        internet_facing: bool,
        technologies: list[dict[str, Any]],
        owner_user_id: uuid.UUID,
    ) -> Project:
        record = Project(
            workspace_id=workspace_id,
            name=name,
            domain=domain,
            environment=environment,
            criticality=criticality,
            internet_facing=internet_facing,
            technologies=technologies,
            status="active",
            owner_user_id=owner_user_id,
        )
        self._session.add(record)
        await self._session.flush()
        return record

    async def get(self, project_id: uuid.UUID) -> Optional[Project]:
        return await self._session.scalar(sa.select(Project).where(Project.id == project_id))

    async def list_for_user(
        self,
        *,
        user_id: uuid.UUID,
        is_global_admin: bool,
        workspace_id: Optional[uuid.UUID],
        include_archived: bool,
        page: int,
        page_size: int,
        environment: Optional[str] = None,
        criticality: Optional[str] = None,
        status: Optional[str] = None,
    ) -> tuple[Sequence[Project], int]:
        """Projects visible to the caller: every project for a global admin,
        else projects the caller is a direct member of OR whose parent
        workspace they own/admin - mirrors the RLS policy in migration 0024.

        ``environment``/``criticality``/``status`` are additive filters used
        by the admin projects list (Task 7) - when ``status`` is given it
        takes over from the ``include_archived`` boolean entirely (an
        explicit status filter is more precise than the archived/active
        toggle every other caller uses), so passing both is fine but
        ``status`` wins.
        """
        filters: list[Any] = []
        if workspace_id is not None:
            filters.append(Project.workspace_id == workspace_id)
        if status is not None:
            filters.append(Project.status == status)
        elif not include_archived:
            filters.append(Project.status == "active")
        if environment is not None:
            filters.append(Project.environment == environment)
        if criticality is not None:
            filters.append(Project.criticality == criticality)

        if is_global_admin:
            visibility = sa.true()
        else:
            visibility = sa.or_(
                sa.exists(
                    sa.select(ProjectMember.id).where(
                        ProjectMember.project_id == Project.id,
                        ProjectMember.user_id == user_id,
                    )
                ),
                sa.exists(
                    sa.select(WorkspaceMember.id).where(
                        WorkspaceMember.workspace_id == Project.workspace_id,
                        WorkspaceMember.user_id == user_id,
                        WorkspaceMember.workspace_role.in_(("owner", "admin")),
                    )
                ),
            )
        filters.append(visibility)

        total = await self._session.scalar(
            sa.select(sa.func.count()).select_from(Project).where(*filters)
        )
        rows = await self._session.scalars(
            sa.select(Project)
            .where(*filters)
            .order_by(Project.created_at.desc(), Project.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(rows), int(total or 0)

    async def update(
        self,
        project: Project,
        *,
        name: Optional[str] = None,
        domain: Optional[str] = None,
        environment: Optional[str] = None,
        criticality: Optional[str] = None,
        internet_facing: Optional[bool] = None,
        technologies: Optional[list[dict[str, Any]]] = None,
    ) -> Project:
        if name is not None:
            project.name = name
        if domain is not None:
            project.domain = domain
        if environment is not None:
            project.environment = environment
        if criticality is not None:
            project.criticality = criticality
        if internet_facing is not None:
            project.internet_facing = internet_facing
        if technologies is not None:
            project.technologies = technologies
        await self._session.flush()
        return project

    async def archive(self, project: Project, *, when: datetime) -> Project:
        project.status = "archived"
        project.archived_at = when
        await self._session.flush()
        return project

    # -- Task 7: admin-only cross-workspace aggregation ---------------------
    # Neither method below is membership-scoped - both are admin-only
    # (callers gated by require_admin), added rather than weakening
    # list_for_user's own membership-visibility semantics.

    async def list_active(self) -> Sequence[Project]:
        """Every active project, no membership filter, no pagination - used
        only by the admin summary's "Project Health" breakdown (Task 7),
        which computes each active project's security score once. Not for
        any membership-scoped listing - see list_for_user for that."""
        rows = await self._session.scalars(
            sa.select(Project)
            .where(Project.status == "active")
            .order_by(Project.created_at.desc())
        )
        return list(rows)

    async def count_for_workspace(self, *, workspace_id: uuid.UUID) -> int:
        """Every project in a workspace regardless of status - powers the
        admin workspaces list's "project count" column (Task 7)."""
        total = await self._session.scalar(
            sa.select(sa.func.count())
            .select_from(Project)
            .where(Project.workspace_id == workspace_id)
        )
        return int(total or 0)
