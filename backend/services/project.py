"""Project business logic - a thin layer over the repositories.

``create`` is the one place project creation authorization is checked
in-service rather than via a route-level dependency: the target workspace is
supplied in the request body (``POST /api/projects``), not the URL path, so
there is no ``workspace_id`` path parameter for
``backend.core.workspace_authorization.require_workspace_role`` to bind to.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.audit import log_audit_event
from backend.core.authorization import AppUser
from backend.core.exceptions import AuthorizationError, ConflictError, InvalidRequestError, NotFoundError
from backend.database.models.project import PROJECT_MEMBER_ROLES, Project, ProjectMember
from backend.repositories.project import ProjectRepository
from backend.repositories.project_members import ProjectMemberRepository
from backend.repositories.workspace import WorkspaceRepository
from backend.repositories.workspace_members import WorkspaceMemberRepository

_GLOBAL_BYPASS_ROLES = ("admin", "super_admin")
_WORKSPACE_ROLES_THAT_MAY_CREATE_PROJECTS = ("owner", "admin")


class ProjectService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._projects = ProjectRepository(session)
        self._members = ProjectMemberRepository(session)
        self._workspaces = WorkspaceRepository(session)
        self._workspace_members = WorkspaceMemberRepository(session)

    async def _authorize_project_creation(
        self, workspace_id: uuid.UUID, app_user: AppUser
    ) -> None:
        if app_user.role in _GLOBAL_BYPASS_ROLES:
            return
        workspace = await self._workspaces.get(workspace_id)
        if workspace is None:
            raise NotFoundError("Workspace not found.")
        member = await self._workspace_members.get(workspace_id=workspace_id, user_id=app_user.id)
        if member is None:
            raise NotFoundError("Workspace not found.")
        if member.workspace_role not in _WORKSPACE_ROLES_THAT_MAY_CREATE_PROJECTS:
            raise AuthorizationError(
                "Only a workspace owner or admin may create projects in this workspace."
            )

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
        creator: AppUser,
        actor: Optional[str],
    ) -> Project:
        await self._authorize_project_creation(workspace_id, creator)

        project = await self._projects.create(
            workspace_id=workspace_id,
            name=name,
            domain=domain,
            environment=environment,
            criticality=criticality,
            internet_facing=internet_facing,
            technologies=technologies,
            owner_user_id=creator.id,
        )
        await self._members.add(project_id=project.id, user_id=creator.id, project_role="owner")
        await self._session.commit()
        log_audit_event(
            event_type="project",
            action="project_created",
            resource=f"project:{project.id}",
            result="success",
            actor=actor,
            metadata={"workspace_id": str(workspace_id)},
        )
        return project

    async def get(self, project_id: uuid.UUID) -> Project:
        project = await self._projects.get(project_id)
        if project is None:
            raise NotFoundError("Project not found.")
        return project

    async def list(
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
    ):
        return await self._projects.list_for_user(
            user_id=user_id,
            is_global_admin=is_global_admin,
            workspace_id=workspace_id,
            include_archived=include_archived,
            page=page,
            page_size=page_size,
            environment=environment,
            criticality=criticality,
            status=status,
        )

    async def update(
        self,
        project_id: uuid.UUID,
        *,
        name: Optional[str],
        domain: Optional[str],
        environment: Optional[str],
        criticality: Optional[str],
        internet_facing: Optional[bool],
        technologies: Optional[list[dict[str, Any]]],
        actor: Optional[str],
    ) -> Project:
        project = await self.get(project_id)
        project = await self._projects.update(
            project,
            name=name,
            domain=domain,
            environment=environment,
            criticality=criticality,
            internet_facing=internet_facing,
            technologies=technologies,
        )
        await self._session.commit()
        log_audit_event(
            event_type="project",
            action="project_updated",
            resource=f"project:{project.id}",
            result="success",
            actor=actor,
        )
        return project

    async def archive(self, project_id: uuid.UUID, *, actor: Optional[str]) -> Project:
        project = await self.get(project_id)
        project = await self._projects.archive(project, when=datetime.now(timezone.utc))
        await self._session.commit()
        log_audit_event(
            event_type="project",
            action="project_archived",
            resource=f"project:{project.id}",
            result="success",
            actor=actor,
        )
        return project

    async def list_members(self, project_id: uuid.UUID):
        return await self._members.list(project_id=project_id)

    async def add_member(
        self,
        project_id: uuid.UUID,
        *,
        user_id: uuid.UUID,
        project_role: str,
        actor: Optional[str],
    ) -> ProjectMember:
        if project_role not in PROJECT_MEMBER_ROLES:
            raise InvalidRequestError(f"project_role must be one of {sorted(PROJECT_MEMBER_ROLES)}.")
        await self.get(project_id)
        existing = await self._members.get(project_id=project_id, user_id=user_id)
        if existing is not None:
            raise ConflictError("This user is already a member of the project.")
        member = await self._members.add(
            project_id=project_id, user_id=user_id, project_role=project_role
        )
        await self._session.commit()
        log_audit_event(
            event_type="project",
            action="project_member_added",
            resource=f"project:{project_id}",
            result="success",
            actor=actor,
            metadata={"target_user_id": str(user_id), "project_role": project_role},
        )
        return member

    async def _ensure_not_last_owner(self, project_id: uuid.UUID, member: ProjectMember) -> None:
        """Mirrors ``WorkspaceService._ensure_not_last_owner``: blocks
        demoting/removing the last ``owner`` member of a project."""
        if member.project_role != "owner":
            return
        if await self._members.count_by_role(project_id=project_id, role="owner") <= 1:
            raise ConflictError("Cannot change this member: they are the project's only owner.")

    async def change_member_role(
        self,
        project_id: uuid.UUID,
        *,
        user_id: uuid.UUID,
        new_role: str,
        actor: Optional[str],
    ) -> ProjectMember:
        if new_role not in PROJECT_MEMBER_ROLES:
            raise InvalidRequestError(f"project_role must be one of {sorted(PROJECT_MEMBER_ROLES)}.")
        member = await self._members.get(project_id=project_id, user_id=user_id)
        if member is None:
            raise NotFoundError("Project member not found.")

        if member.project_role == "owner" and new_role != "owner":
            await self._ensure_not_last_owner(project_id, member)

        member = await self._members.update_role(member, project_role=new_role)
        await self._session.commit()
        log_audit_event(
            event_type="project",
            action="project_member_role_changed",
            resource=f"project:{project_id}",
            result="success",
            actor=actor,
            metadata={"target_user_id": str(user_id), "project_role": new_role},
        )
        return member

    async def remove_member(
        self, project_id: uuid.UUID, *, user_id: uuid.UUID, actor: Optional[str]
    ) -> None:
        member = await self._members.get(project_id=project_id, user_id=user_id)
        if member is None:
            raise NotFoundError("Project member not found.")

        await self._ensure_not_last_owner(project_id, member)

        await self._members.remove(member)
        await self._session.commit()
        log_audit_event(
            event_type="project",
            action="project_member_removed",
            resource=f"project:{project_id}",
            result="success",
            actor=actor,
            metadata={"target_user_id": str(user_id)},
        )
