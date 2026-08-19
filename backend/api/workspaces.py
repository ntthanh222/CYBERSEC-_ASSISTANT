"""Workspace and workspace-membership API.

**Requires a valid Supabase Auth Bearer token on every route.** Visibility
and mutation rights are workspace-membership-scoped - see
``backend.core.workspace_authorization`` - with a global ``admin``/
``super_admin`` bypassing every membership check.
"""
import uuid
from typing import Any, Optional

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import PageParams, page_params
from backend.core.actor import get_current_actor
from backend.core.authorization import AppUser, get_app_user
from backend.core.auth import get_current_user
from backend.core.workspace_authorization import get_workspace_member, require_workspace_role
from backend.database.models.workspace import Workspace, WorkspaceMember
from backend.database.session import get_rls_db
from backend.schemas.health import ErrorResponse
from backend.schemas.workspaces import (
    WorkspaceCreate,
    WorkspaceItem,
    WorkspaceMemberAdd,
    WorkspaceMemberItem,
    WorkspaceMemberList,
    WorkspaceMemberRoleChange,
    WorkspacePage,
    WorkspaceUpdate,
)
from backend.services.workspace import WorkspaceService

router = APIRouter(
    prefix="/api/workspaces", tags=["workspaces"], dependencies=[Depends(get_current_user)]
)
_UNAUTHORIZED = {401: {"model": ErrorResponse, "description": "Missing or invalid bearer token."}}
_FORBIDDEN = {403: {"model": ErrorResponse, "description": "Insufficient workspace role."}}
_NOT_FOUND = {404: {"model": ErrorResponse, "description": "Workspace not found."}}


def _workspace_dict(record: Workspace) -> dict[str, Any]:
    return {
        "id": record.id,
        "name": record.name,
        "description": record.description,
        "created_by_user_id": record.created_by_user_id,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }


def _member_dict(record: WorkspaceMember) -> dict[str, Any]:
    return {
        "id": record.id,
        "workspace_id": record.workspace_id,
        "user_id": record.user_id,
        "workspace_role": record.workspace_role,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }


@router.post(
    "",
    status_code=201,
    summary="Create a workspace",
    description="Creates a workspace owned by the caller, who is auto-added as its 'owner' member.",
    response_model=WorkspaceItem,
    responses={422: {"model": ErrorResponse, "description": "Invalid body."}, **_UNAUTHORIZED},
)
async def create_workspace(
    body: WorkspaceCreate,
    session: AsyncSession = Depends(get_rls_db),
    app_user: AppUser = Depends(get_app_user),
    actor: str = Depends(get_current_actor),
) -> dict:
    service = WorkspaceService(session)
    record = await service.create(
        name=body.name,
        description=body.description,
        created_by_user_id=app_user.id,
        actor=actor,
    )
    return _workspace_dict(record)


@router.get(
    "",
    summary="List workspaces",
    description="Workspaces the caller is a member of, or every workspace for a global admin.",
    response_model=WorkspacePage,
    responses={**_UNAUTHORIZED},
)
async def list_workspaces(
    pagination: PageParams = Depends(page_params),
    session: AsyncSession = Depends(get_rls_db),
    app_user: AppUser = Depends(get_app_user),
) -> dict:
    service = WorkspaceService(session)
    is_global_admin = app_user.role in ("admin", "super_admin")
    items, total = await service.list(
        user_id=app_user.id,
        is_global_admin=is_global_admin,
        page=pagination.page,
        page_size=pagination.page_size,
    )
    return {
        "items": [_workspace_dict(item) for item in items],
        "total": total,
        "page": pagination.page,
        "page_size": pagination.page_size,
    }


@router.get(
    "/{workspace_id}",
    summary="Get one workspace",
    description="Only visible to a member (or a global admin).",
    response_model=WorkspaceItem,
    responses={**_UNAUTHORIZED, **_NOT_FOUND},
)
async def get_workspace(
    workspace_id: uuid.UUID,
    session: AsyncSession = Depends(get_rls_db),
    _member: Optional[WorkspaceMember] = Depends(get_workspace_member),
) -> dict:
    service = WorkspaceService(session)
    record = await service.get(workspace_id)
    return _workspace_dict(record)


@router.patch(
    "/{workspace_id}",
    summary="Update a workspace",
    description="Requires the caller to be a workspace owner/admin (or global admin).",
    response_model=WorkspaceItem,
    responses={**_UNAUTHORIZED, **_FORBIDDEN, **_NOT_FOUND},
)
async def update_workspace(
    workspace_id: uuid.UUID,
    body: WorkspaceUpdate,
    session: AsyncSession = Depends(get_rls_db),
    actor: str = Depends(get_current_actor),
    _member: Optional[WorkspaceMember] = Depends(require_workspace_role("owner", "admin")),
) -> dict:
    service = WorkspaceService(session)
    record = await service.update(
        workspace_id, name=body.name, description=body.description, actor=actor
    )
    return _workspace_dict(record)


@router.get(
    "/{workspace_id}/members",
    summary="List workspace members",
    response_model=WorkspaceMemberList,
    responses={**_UNAUTHORIZED, **_NOT_FOUND},
)
async def list_workspace_members(
    workspace_id: uuid.UUID,
    session: AsyncSession = Depends(get_rls_db),
    _member: Optional[WorkspaceMember] = Depends(get_workspace_member),
) -> dict:
    service = WorkspaceService(session)
    members = await service.list_members(workspace_id)
    return {"items": [_member_dict(item) for item in members]}


@router.post(
    "/{workspace_id}/members",
    status_code=201,
    summary="Add a workspace member",
    description="Requires the caller to be a workspace owner/admin (or global admin).",
    response_model=WorkspaceMemberItem,
    responses={
        **_UNAUTHORIZED,
        **_FORBIDDEN,
        **_NOT_FOUND,
        409: {"model": ErrorResponse, "description": "Already a member."},
    },
)
async def add_workspace_member(
    workspace_id: uuid.UUID,
    body: WorkspaceMemberAdd,
    session: AsyncSession = Depends(get_rls_db),
    actor: str = Depends(get_current_actor),
    _member: Optional[WorkspaceMember] = Depends(require_workspace_role("owner", "admin")),
) -> dict:
    service = WorkspaceService(session)
    record = await service.add_member(
        workspace_id, user_id=body.user_id, workspace_role=body.workspace_role, actor=actor
    )
    return _member_dict(record)


@router.patch(
    "/{workspace_id}/members/{user_id}",
    summary="Change a workspace member's role",
    description="Requires the caller to be a workspace owner/admin (or global admin). "
    "Blocked with 409 if this would leave the workspace with zero owners.",
    response_model=WorkspaceMemberItem,
    responses={
        **_UNAUTHORIZED,
        **_FORBIDDEN,
        404: {"model": ErrorResponse, "description": "Workspace or member not found."},
        409: {"model": ErrorResponse, "description": "Would remove the workspace's last owner."},
    },
)
async def change_workspace_member_role(
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    body: WorkspaceMemberRoleChange,
    session: AsyncSession = Depends(get_rls_db),
    actor: str = Depends(get_current_actor),
    _member: Optional[WorkspaceMember] = Depends(require_workspace_role("owner", "admin")),
) -> dict:
    service = WorkspaceService(session)
    record = await service.change_member_role(
        workspace_id, user_id=user_id, new_role=body.workspace_role, actor=actor
    )
    return _member_dict(record)


@router.delete(
    "/{workspace_id}/members/{user_id}",
    status_code=204,
    summary="Remove a workspace member",
    description="Requires the caller to be a workspace owner/admin (or global admin). "
    "Blocked with 409 if this would leave the workspace with zero owners.",
    responses={
        **_UNAUTHORIZED,
        **_FORBIDDEN,
        404: {"model": ErrorResponse, "description": "Workspace or member not found."},
        409: {"model": ErrorResponse, "description": "Would remove the workspace's last owner."},
    },
)
async def remove_workspace_member(
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    session: AsyncSession = Depends(get_rls_db),
    actor: str = Depends(get_current_actor),
    _member: Optional[WorkspaceMember] = Depends(require_workspace_role("owner", "admin")),
) -> None:
    service = WorkspaceService(session)
    await service.remove_member(workspace_id, user_id=user_id, actor=actor)
