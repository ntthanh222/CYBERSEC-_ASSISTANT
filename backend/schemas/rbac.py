"""Request/response models for local admin auth and RBAC management."""
from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

Role = Literal["user", "developer", "security_analyst", "admin", "super_admin"]


class AdminSetupStatusResponse(BaseModel):
    admin_exists: bool


class AdminSetupRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class AdminLoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class MeResponse(BaseModel):
    id: str
    email: Optional[str] = None
    role: Role
    is_active: bool


class AdminUserItem(BaseModel):
    user_id: str
    email: Optional[str] = None
    username: Optional[str] = None
    role: Role
    is_active: bool
    source: Literal["demo", "test", "local", "hosted"] = "hosted"
    is_test_account: bool = False
    created_at: datetime
    updated_at: datetime
    last_login_at: Optional[datetime] = None


class AdminUserPage(BaseModel):
    items: list[AdminUserItem]
    total: int
    page: int
    page_size: int


class AdminRoleChangeRequest(BaseModel):
    role: Role


class AdminActiveChangeRequest(BaseModel):
    is_active: bool


class AdminUserMutationResponse(BaseModel):
    user_id: str
    role: Role
    is_active: bool


class AdminUserCounts(BaseModel):
    total: int
    admins: int
    active: int
    disabled: int
    users: int = 0
    security_analysts: int = 0
    super_admins: int = 0
    demo: int = 0
    test: int = 0
    local: int = 0
    hosted: int = 0


class AdminContentCounts(BaseModel):
    documents: int
    conversations: int
    messages: int
    scans: int


class AdminSummaryResponse(BaseModel):
    users: AdminUserCounts
    content: AdminContentCounts
    system_status: str
    audit_events: int = 0
    recent_admin_actions: int = 0


class AdminAuditLogItem(BaseModel):
    id: str
    actor_user_id: Optional[str] = None
    action: str
    target_user_id: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None
    created_at: datetime


class AdminAuditLogPage(BaseModel):
    items: list[AdminAuditLogItem]
    total: int
    page: int
    page_size: int
