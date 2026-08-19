"""Workspace-scoped authorization: "is this caller a member of this workspace,
and with what role?"

Deliberately separate from ``backend.core.authorization`` (global RBAC tiers):
a workspace's ``owner``/``admin``/``member`` roles are meaningful only within
that one workspace, not a system-wide privilege level. A global ``admin``/
``super_admin`` still bypasses every check here - see each dependency's
docstring - so platform administrators never need to be explicitly added as
a member to manage a workspace.

Uses ``get_db`` (not ``get_rls_db``) on purpose: this is the source-of-truth
authorization check the route handler relies on for its 404/403 decision, so
it must see every row regardless of the caller's RLS visibility. Row Level
Security on ``workspaces``/``workspace_members`` (migration 0023) is enabled
but not FORCEd for exactly this reason - defense in depth for routes that use
``get_rls_db`` to touch the tables directly, not a gate this dependency has to
route around.
"""
from __future__ import annotations

import uuid
from typing import Optional

import sqlalchemy as sa
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.authorization import AppUser, get_app_user
from backend.core.exceptions import AuthorizationError, NotFoundError
from backend.database.models.workspace import Workspace, WorkspaceMember
from backend.database.session import get_db

#: Global tiers that bypass every workspace-scoped check unconditionally.
_GLOBAL_BYPASS_ROLES = ("admin", "super_admin")


async def get_workspace_member(
    workspace_id: uuid.UUID,
    app_user: AppUser = Depends(get_app_user),
    session: AsyncSession = Depends(get_db),
) -> Optional[WorkspaceMember]:
    """The caller's membership row for ``workspace_id``, or ``None`` for a
    global admin/super_admin bypassing the check entirely.

    Raises 404 (never 403) if the workspace does not exist OR the caller has
    no membership row - existence of a workspace the caller cannot see must
    never leak through a distinguishable error code.
    """
    if app_user.role in _GLOBAL_BYPASS_ROLES:
        return None

    workspace = await session.scalar(sa.select(Workspace).where(Workspace.id == workspace_id))
    if workspace is None:
        raise NotFoundError("Workspace not found.")

    member = await session.scalar(
        sa.select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == app_user.id,
        )
    )
    if member is None:
        raise NotFoundError("Workspace not found.")
    return member


def require_workspace_role(*roles: str):
    """Build a dependency requiring the caller's ``workspace_role`` to be one
    of ``roles`` for this workspace. Global admin/super_admin still bypass.
    """

    async def _dependency(
        member: Optional[WorkspaceMember] = Depends(get_workspace_member),
    ) -> Optional[WorkspaceMember]:
        if member is None:
            # get_workspace_member already confirmed this is a global bypass.
            return None
        if member.workspace_role not in roles:
            raise AuthorizationError(
                "You do not have the required role in this workspace."
            )
        return member

    return _dependency
