"""Request/response models for the Admin Console's Workspace/Project/Finding
visibility surface (Task 7 - Admin Console Upgrade).

These are thin, admin-only extensions of the existing Task 1/2 schemas
(``ProjectItem``, ``WorkspaceItem``, ``FindingItem``/``MyTaskItem``) - each
adds only the cross-project aggregate fields (member counts, open-finding
counts, parent project name) the admin views need, reusing every other
field/shape as-is rather than re-declaring the whole entity from scratch.
"""
from typing import List
from uuid import UUID

from backend.schemas.common import Page, UtcDatetime
from backend.schemas.findings import MyTaskItem
from backend.schemas.projects import (
    ProjectCriticality,
    ProjectEnvironment,
    ProjectStatus,
    Technology,
)
from pydantic import BaseModel


class AdminWorkspaceItem(BaseModel):
    id: UUID
    name: str
    description: str | None = None
    created_by_user_id: UUID
    member_count: int
    project_count: int
    created_at: UtcDatetime
    updated_at: UtcDatetime


class AdminWorkspacePage(Page[AdminWorkspaceItem]):
    pass


class AdminProjectItem(BaseModel):
    id: UUID
    workspace_id: UUID
    name: str
    domain: str | None = None
    environment: ProjectEnvironment
    criticality: ProjectCriticality
    internet_facing: bool
    technologies: List[Technology]
    status: ProjectStatus
    archived_at: UtcDatetime | None = None
    owner_user_id: UUID
    member_count: int
    open_findings_count: int
    created_at: UtcDatetime
    updated_at: UtcDatetime


class AdminProjectPage(Page[AdminProjectItem]):
    pass


#: The admin cross-project findings view is shaped identically to Task 4's
#: "My Tasks" (a FindingItem plus its parent project's name) - reused
#: directly rather than re-declared, since the field set is genuinely the
#: same, just populated from a different query (every finding vs. one
#: caller's assigned findings).
AdminFindingItem = MyTaskItem


class AdminFindingPage(Page[MyTaskItem]):
    pass
