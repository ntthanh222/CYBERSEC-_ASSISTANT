"""Request/response models for projects and project membership."""
from typing import List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from backend.schemas.common import Page, UtcDatetime

ProjectEnvironment = Literal["development", "staging", "production"]
ProjectCriticality = Literal["low", "medium", "high", "critical"]
ProjectStatus = Literal["active", "archived"]
ProjectRole = Literal["owner", "security", "developer", "viewer"]


class Technology(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    version: str = Field(default="", max_length=50)


class ProjectCreate(BaseModel):
    workspace_id: UUID
    name: str = Field(min_length=1, max_length=200, examples=["Customer Portal"])
    domain: Optional[str] = Field(default=None, max_length=255, examples=["portal.acme.com"])
    environment: ProjectEnvironment = Field(examples=["production"])
    criticality: ProjectCriticality = Field(examples=["high"])
    internet_facing: bool = Field(default=False)
    technologies: List[Technology] = Field(default_factory=list, max_length=100)


class ProjectUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    domain: Optional[str] = Field(default=None, max_length=255)
    environment: Optional[ProjectEnvironment] = None
    criticality: Optional[ProjectCriticality] = None
    internet_facing: Optional[bool] = None
    technologies: Optional[List[Technology]] = Field(default=None, max_length=100)


class ProjectItem(BaseModel):
    id: UUID = Field(examples=["7c9e6679-7425-40de-944b-e07fc1f90ae7"])
    workspace_id: UUID
    name: str
    domain: Optional[str] = None
    environment: ProjectEnvironment
    criticality: ProjectCriticality
    internet_facing: bool
    technologies: List[Technology]
    status: ProjectStatus
    archived_at: Optional[UtcDatetime] = None
    owner_user_id: UUID
    created_at: UtcDatetime
    updated_at: UtcDatetime


class ProjectPage(Page[ProjectItem]):
    pass


class ProjectMemberAdd(BaseModel):
    user_id: UUID
    project_role: ProjectRole


class ProjectMemberRoleChange(BaseModel):
    project_role: ProjectRole


class ProjectMemberItem(BaseModel):
    id: UUID
    project_id: UUID
    user_id: UUID
    project_role: ProjectRole
    created_at: UtcDatetime
    updated_at: UtcDatetime


class ProjectMemberList(BaseModel):
    items: List[ProjectMemberItem]
