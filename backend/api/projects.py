"""Project and project-membership API.

**Requires a valid Supabase Auth Bearer token on every route.** Visibility
and mutation rights are project-membership-scoped (with a workspace
owner/admin implicitly treated as project-owner-equivalent) - see
``backend.core.project_authorization`` - with a global ``admin``/
``super_admin`` bypassing every check.
"""
import uuid
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import PageParams, page_params
from backend.core.actor import get_current_actor
from backend.core.authorization import AppUser, get_app_user
from backend.core.auth import get_current_user
from backend.core.project_authorization import get_project_member, require_project_role
from backend.database.models.project import Project, ProjectMember
from backend.database.session import get_rls_db
from backend.schemas.health import ErrorResponse
from backend.schemas.projects import (
    ProjectCreate,
    ProjectItem,
    ProjectMemberAdd,
    ProjectMemberItem,
    ProjectMemberList,
    ProjectMemberRoleChange,
    ProjectPage,
    ProjectUpdate,
)
from backend.services.project import ProjectService

router = APIRouter(
    prefix="/api/projects", tags=["projects"], dependencies=[Depends(get_current_user)]
)
_UNAUTHORIZED = {401: {"model": ErrorResponse, "description": "Missing or invalid bearer token."}}
_FORBIDDEN = {403: {"model": ErrorResponse, "description": "Insufficient project role."}}
_NOT_FOUND = {404: {"model": ErrorResponse, "description": "Project not found."}}
#: Only owner/security project roles (or the workspace-owner/admin bypass, or
#: a global admin) may manage membership/archival - see the Task 1 brief.
_MANAGE_ROLES = ("owner", "security")


def _project_dict(record: Project) -> dict[str, Any]:
    return {
        "id": record.id,
        "workspace_id": record.workspace_id,
        "name": record.name,
        "domain": record.domain,
        "environment": record.environment,
        "criticality": record.criticality,
        "internet_facing": record.internet_facing,
        "technologies": record.technologies,
        "status": record.status,
        "archived_at": record.archived_at,
        "owner_user_id": record.owner_user_id,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }


def _member_dict(record: ProjectMember) -> dict[str, Any]:
    return {
        "id": record.id,
        "project_id": record.project_id,
        "user_id": record.user_id,
        "project_role": record.project_role,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }


@router.post(
    "",
    status_code=201,
    summary="Create a project",
    description="Creates a project in the given workspace. Requires the caller to be a "
    "workspace owner/admin (or global admin). The caller is auto-added as its 'owner' member.",
    response_model=ProjectItem,
    responses={
        422: {"model": ErrorResponse, "description": "Invalid body."},
        **_UNAUTHORIZED,
        **_FORBIDDEN,
        404: {"model": ErrorResponse, "description": "Workspace not found."},
    },
)
async def create_project(
    body: ProjectCreate,
    session: AsyncSession = Depends(get_rls_db),
    app_user: AppUser = Depends(get_app_user),
    actor: str = Depends(get_current_actor),
) -> dict:
    service = ProjectService(session)
    record = await service.create(
        workspace_id=body.workspace_id,
        name=body.name,
        domain=body.domain,
        environment=body.environment,
        criticality=body.criticality,
        internet_facing=body.internet_facing,
        technologies=[tech.model_dump() for tech in body.technologies],
        creator=app_user,
        actor=actor,
    )
    return _project_dict(record)


@router.get(
    "",
    summary="List projects",
    description="Projects visible to the caller, optionally filtered by workspace. "
    "Archived projects are excluded unless include_archived=true.",
    response_model=ProjectPage,
    responses={**_UNAUTHORIZED},
)
async def list_projects(
    pagination: PageParams = Depends(page_params),
    workspace_id: Optional[uuid.UUID] = Query(default=None),
    include_archived: bool = Query(default=False),
    session: AsyncSession = Depends(get_rls_db),
    app_user: AppUser = Depends(get_app_user),
) -> dict:
    service = ProjectService(session)
    is_global_admin = app_user.role in ("admin", "super_admin")
    items, total = await service.list(
        user_id=app_user.id,
        is_global_admin=is_global_admin,
        workspace_id=workspace_id,
        include_archived=include_archived,
        page=pagination.page,
        page_size=pagination.page_size,
    )
    return {
        "items": [_project_dict(item) for item in items],
        "total": total,
        "page": pagination.page,
        "page_size": pagination.page_size,
    }


@router.get(
    "/{project_id}",
    summary="Get one project",
    description="Only visible to a project member, a workspace owner/admin, or a global admin. "
    "Archived projects remain fetchable by id for history purposes.",
    response_model=ProjectItem,
    responses={**_UNAUTHORIZED, **_NOT_FOUND},
)
async def get_project(
    project_id: uuid.UUID,
    session: AsyncSession = Depends(get_rls_db),
    _member: Optional[ProjectMember] = Depends(get_project_member),
) -> dict:
    service = ProjectService(session)
    record = await service.get(project_id)
    return _project_dict(record)


@router.patch(
    "/{project_id}",
    summary="Update a project",
    description="Requires an owner/security project role (or workspace owner/admin, or global admin).",
    response_model=ProjectItem,
    responses={**_UNAUTHORIZED, **_FORBIDDEN, **_NOT_FOUND},
)
async def update_project(
    project_id: uuid.UUID,
    body: ProjectUpdate,
    session: AsyncSession = Depends(get_rls_db),
    actor: str = Depends(get_current_actor),
    _member: Optional[ProjectMember] = Depends(require_project_role(*_MANAGE_ROLES)),
) -> dict:
    service = ProjectService(session)
    record = await service.update(
        project_id,
        name=body.name,
        domain=body.domain,
        environment=body.environment,
        criticality=body.criticality,
        internet_facing=body.internet_facing,
        technologies=(
            [tech.model_dump() for tech in body.technologies]
            if body.technologies is not None
            else None
        ),
        actor=actor,
    )
    return _project_dict(record)


@router.post(
    "/{project_id}/archive",
    summary="Archive a project",
    description="Requires an owner/security project role (or workspace owner/admin, or global admin). "
    "Archived projects are excluded from default list queries but remain fetchable by id.",
    response_model=ProjectItem,
    responses={**_UNAUTHORIZED, **_FORBIDDEN, **_NOT_FOUND},
)
async def archive_project(
    project_id: uuid.UUID,
    session: AsyncSession = Depends(get_rls_db),
    actor: str = Depends(get_current_actor),
    _member: Optional[ProjectMember] = Depends(require_project_role(*_MANAGE_ROLES)),
) -> dict:
    service = ProjectService(session)
    record = await service.archive(project_id, actor=actor)
    return _project_dict(record)


@router.get(
    "/{project_id}/members",
    summary="List project members",
    response_model=ProjectMemberList,
    responses={**_UNAUTHORIZED, **_NOT_FOUND},
)
async def list_project_members(
    project_id: uuid.UUID,
    session: AsyncSession = Depends(get_rls_db),
    _member: Optional[ProjectMember] = Depends(get_project_member),
) -> dict:
    service = ProjectService(session)
    members = await service.list_members(project_id)
    return {"items": [_member_dict(item) for item in members]}


@router.post(
    "/{project_id}/members",
    status_code=201,
    summary="Add a project member",
    description="Requires an owner/security project role (or workspace owner/admin, or global admin).",
    response_model=ProjectMemberItem,
    responses={
        **_UNAUTHORIZED,
        **_FORBIDDEN,
        **_NOT_FOUND,
        409: {"model": ErrorResponse, "description": "Already a member."},
    },
)
async def add_project_member(
    project_id: uuid.UUID,
    body: ProjectMemberAdd,
    session: AsyncSession = Depends(get_rls_db),
    actor: str = Depends(get_current_actor),
    _member: Optional[ProjectMember] = Depends(require_project_role(*_MANAGE_ROLES)),
) -> dict:
    service = ProjectService(session)
    record = await service.add_member(
        project_id, user_id=body.user_id, project_role=body.project_role, actor=actor
    )
    return _member_dict(record)


@router.patch(
    "/{project_id}/members/{user_id}",
    summary="Change a project member's role",
    description="Requires an owner/security project role (or workspace owner/admin, or global "
    "admin). Blocked with 409 if this would leave the project with zero owners.",
    response_model=ProjectMemberItem,
    responses={
        **_UNAUTHORIZED,
        **_FORBIDDEN,
        404: {"model": ErrorResponse, "description": "Project or member not found."},
        409: {"model": ErrorResponse, "description": "Would remove the project's last owner."},
    },
)
async def change_project_member_role(
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    body: ProjectMemberRoleChange,
    session: AsyncSession = Depends(get_rls_db),
    actor: str = Depends(get_current_actor),
    _member: Optional[ProjectMember] = Depends(require_project_role(*_MANAGE_ROLES)),
) -> dict:
    service = ProjectService(session)
    record = await service.change_member_role(
        project_id, user_id=user_id, new_role=body.project_role, actor=actor
    )
    return _member_dict(record)


@router.delete(
    "/{project_id}/members/{user_id}",
    status_code=204,
    summary="Remove a project member",
    description="Requires an owner/security project role (or workspace owner/admin, or global "
    "admin). Blocked with 409 if this would leave the project with zero owners.",
    responses={
        **_UNAUTHORIZED,
        **_FORBIDDEN,
        404: {"model": ErrorResponse, "description": "Project or member not found."},
        409: {"model": ErrorResponse, "description": "Would remove the project's last owner."},
    },
)
async def remove_project_member(
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    session: AsyncSession = Depends(get_rls_db),
    actor: str = Depends(get_current_actor),
    _member: Optional[ProjectMember] = Depends(require_project_role(*_MANAGE_ROLES)),
) -> None:
    service = ProjectService(session)
    await service.remove_member(project_id, user_id=user_id, actor=actor)
