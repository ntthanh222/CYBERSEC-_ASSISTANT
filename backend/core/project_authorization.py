"""Project-scoped authorization: "is this caller allowed to see/act on this
project, and with what role?"

Three ways a caller can be authorized for a project, checked in order:

1. Global ``admin``/``super_admin`` - unconditional bypass, same as
   ``backend.core.workspace_authorization``.
2. A direct ``ProjectMember`` row (``owner``/``security``/``developer``/
   ``viewer``).
3. An ``owner``/``admin`` ``WorkspaceMember`` of the project's parent
   workspace - implicitly treated as project-owner-equivalent, even with no
   ``ProjectMember`` row of their own.

``require_project_role`` is deliberately set-based, not a linear rank: the
plan does not want an implicit hierarchy where ``owner`` alone satisfies
every check that lists only ``security`` (or vice versa) - a route must list
every role it accepts explicitly. The workspace-owner/admin bypass in (3) is
the only implicit elevation, and it satisfies *any* role check on the
project, exactly like the global bypass in (1).

Uses ``get_db`` (not ``get_rls_db``) for the same reason as
``workspace_authorization.get_workspace_member``: this is the authoritative
check the route relies on, so RLS visibility must never gate it.
"""
from __future__ import annotations

import uuid
from typing import Optional

import sqlalchemy as sa
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.authorization import AppUser, get_app_user
from backend.core.exceptions import AuthorizationError, NotFoundError
from backend.database.models.project import Project, ProjectMember
from backend.database.models.workspace import WorkspaceMember
from backend.database.session import get_db

_GLOBAL_BYPASS_ROLES = ("admin", "super_admin")
#: Workspace roles that imply project-owner-equivalent rights on every
#: project in that workspace.
_WORKSPACE_IMPLIED_ROLES = ("owner", "admin")


async def get_project_member(
    project_id: uuid.UUID,
    app_user: AppUser = Depends(get_app_user),
    session: AsyncSession = Depends(get_db),
) -> Optional[ProjectMember]:
    """The caller's direct ``ProjectMember`` row for ``project_id``, or
    ``None`` when authorized via a bypass (global admin, or owner/admin of
    the parent workspace) - both are treated as fully authorized for every
    role check on this project, see ``require_project_role``.

    Raises 404 (never 403) if the project does not exist OR the caller has
    no path to visibility.
    """
    if app_user.role in _GLOBAL_BYPASS_ROLES:
        return None

    project = await session.scalar(sa.select(Project).where(Project.id == project_id))
    if project is None:
        raise NotFoundError("Project not found.")

    member = await session.scalar(
        sa.select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == app_user.id,
        )
    )
    if member is not None:
        return member

    workspace_member = await session.scalar(
        sa.select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == project.workspace_id,
            WorkspaceMember.user_id == app_user.id,
            WorkspaceMember.workspace_role.in_(_WORKSPACE_IMPLIED_ROLES),
        )
    )
    if workspace_member is not None:
        return None

    raise NotFoundError("Project not found.")


def require_project_role(*roles: str):
    """Build a dependency requiring the caller's ``project_role`` to be one
    of ``roles``. A bypass (global admin, or workspace owner/admin - see
    ``get_project_member``) satisfies any role set unconditionally.
    """

    async def _dependency(
        member: Optional[ProjectMember] = Depends(get_project_member),
    ) -> Optional[ProjectMember]:
        if member is None:
            return None
        if member.project_role not in roles:
            raise AuthorizationError(
                "You do not have the required role on this project."
            )
        return member

    return _dependency
