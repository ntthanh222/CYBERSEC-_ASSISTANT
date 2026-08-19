"""Request/response models for workspaces and workspace membership."""
from typing import List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from backend.schemas.common import Page, UtcDatetime

WorkspaceRole = Literal["owner", "admin", "member"]


class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200, examples=["Acme Corp Security"])
    description: Optional[str] = Field(default=None, max_length=2000)


class WorkspaceUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=2000)


class WorkspaceItem(BaseModel):
    id: UUID = Field(examples=["7c9e6679-7425-40de-944b-e07fc1f90ae7"])
    name: str
    description: Optional[str] = None
    created_by_user_id: UUID
    created_at: UtcDatetime
    updated_at: UtcDatetime


class WorkspacePage(Page[WorkspaceItem]):
    pass


class WorkspaceMemberAdd(BaseModel):
    user_id: UUID
    workspace_role: WorkspaceRole


class WorkspaceMemberRoleChange(BaseModel):
    workspace_role: WorkspaceRole


class WorkspaceMemberItem(BaseModel):
    id: UUID
    workspace_id: UUID
    user_id: UUID
    workspace_role: WorkspaceRole
    created_at: UtcDatetime
    updated_at: UtcDatetime


class WorkspaceMemberList(BaseModel):
    items: List[WorkspaceMemberItem]
