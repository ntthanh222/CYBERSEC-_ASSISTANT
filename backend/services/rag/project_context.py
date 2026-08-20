"""Project-membership authorization for AI-assistant tool-router handlers
(Task 8: AI Project Security Copilot).

``backend.core.project_authorization.get_project_member`` is built for
FastAPI ``Depends(...)`` route wiring and deliberately conflates "project
does not exist" with "caller has no access" into a single 404 - that is a
documented anti-enumeration measure for a public REST path parameter.

The AI-copilot brief requires the OPPOSITE: a caller who asks the assistant
about a project must get an UNAMBIGUOUS answer distinguishing "this project
does not exist" from "you are not authorized to see this project" - never a
generic message that could be misread as "this project has no problems" (see
the Task 8 brief's "non-negotiable requirement" section). ``project_id`` here
is always an explicit parameter selected by the caller from their own
project-membership dropdown (see the frontend composer's project selector),
not a public path parameter probed over anonymous HTTP - so the enumeration
concern that justifies the flat-404 pattern in
``project_authorization.get_project_member`` does not transfer unchanged to
this surface. This is a deliberate, brief-mandated difference; noted in the
Task 8 report.

EVERY new tool-router handler in ``AppDataToolRouter`` that touches
Project/Finding/ScanRun/CveAssessment data MUST call
``resolve_project_access`` as its very first action and return immediately
on a denial (``authorized is False``) - no exceptions, no data queried
before this check passes.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.authorization import AppUser
from backend.database.models.project import Project, ProjectMember
from backend.repositories.project import ProjectRepository
from backend.repositories.project_members import ProjectMemberRepository
from backend.repositories.workspace_members import WorkspaceMemberRepository

#: Global roles that bypass every project-membership check - mirrors
#: backend.core.project_authorization._GLOBAL_BYPASS_ROLES exactly.
_GLOBAL_BYPASS_ROLES = ("admin", "super_admin")
#: Workspace roles that imply project-owner-equivalent rights on every
#: project in that workspace - mirrors
#: backend.core.project_authorization._WORKSPACE_IMPLIED_ROLES exactly.
_WORKSPACE_IMPLIED_ROLES = ("owner", "admin")

#: Distinct denial reasons so a caller can choose the exact user-facing
#: message the brief requires - never conflated into one generic response.
DENIAL_NOT_FOUND = "not_found"
DENIAL_FORBIDDEN = "forbidden"

#: The exact denial message the brief mandates for a non-member/non-admin
#: caller. Must never be substituted with (or fall through to) a "no
#: evidence"/"nothing found" style message, which could be misread as "this
#: project has no problems" rather than "you cannot see this project".
ACCESS_DENIED_MESSAGE = "Bạn không có quyền truy cập project này."


def _not_found_message(project_id: uuid.UUID) -> str:
    return f"Không tìm thấy project với ID `{project_id}`."


@dataclass(frozen=True)
class ProjectAccessResult:
    """Outcome of a project-authorization check for one tool-router call."""

    authorized: bool
    project: Optional[Project] = None
    member: Optional[ProjectMember] = None
    denial_reason: Optional[str] = None
    denial_message: Optional[str] = None


async def resolve_project_access(
    project_id: uuid.UUID, caller: AppUser, session: AsyncSession
) -> ProjectAccessResult:
    """The ONE shared authorization gate every project-scoped tool-router
    handler must call first, before touching Finding/ScanRun/CveAssessment
    data.

    ``session`` MUST be a non-RLS session (``backend.database.session.get_db``,
    never ``get_rls_db``) - see ``AppDataToolRouter.__init__``'s
    ``authz_session`` docstring for why: Postgres RLS on ``projects`` already
    hides rows a caller isn't a member of, so running this check on an
    RLS-scoped session would make ``ProjectRepository.get`` return ``None``
    for a non-member exactly as it would for a genuinely nonexistent
    project, silently collapsing the mandated FORBIDDEN response into
    NOT_FOUND in production. Mirrors ``backend.core.project_authorization``'s
    own ``get_db``-over-``get_rls_db`` choice for the identical reason.

    Checks, in order:
    1. Does the project exist at all? If not -> ``DENIAL_NOT_FOUND``.
    2. Is the caller a global admin/super_admin? -> authorized (bypass).
    3. Does the caller have a direct ``ProjectMember`` row? -> authorized.
    4. Is the caller an owner/admin ``WorkspaceMember`` of the project's
       parent workspace (implicit project-owner-equivalent, matching
       ``project_authorization.get_project_member``)? -> authorized.
    5. Otherwise -> ``DENIAL_FORBIDDEN``.
    """
    project = await ProjectRepository(session).get(project_id)
    if project is None:
        return ProjectAccessResult(
            authorized=False,
            denial_reason=DENIAL_NOT_FOUND,
            denial_message=_not_found_message(project_id),
        )

    if caller.role in _GLOBAL_BYPASS_ROLES:
        return ProjectAccessResult(authorized=True, project=project, member=None)

    member = await ProjectMemberRepository(session).get(project_id=project_id, user_id=caller.id)
    if member is not None:
        return ProjectAccessResult(authorized=True, project=project, member=member)

    workspace_member = await WorkspaceMemberRepository(session).get(
        workspace_id=project.workspace_id, user_id=caller.id
    )
    if workspace_member is not None and workspace_member.workspace_role in _WORKSPACE_IMPLIED_ROLES:
        return ProjectAccessResult(authorized=True, project=project, member=None)

    return ProjectAccessResult(
        authorized=False,
        denial_reason=DENIAL_FORBIDDEN,
        denial_message=ACCESS_DENIED_MESSAGE,
    )
