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


#: Simple security-score bucketing for the admin summary's "Project Health"
#: breakdown (Task 7) - reuses ProjectDashboardService's existing 0-100
#: score formula (Task 5), just grouped into three bands instead of shown
#: per-project. Thresholds are a new, documented judgement call for this
#: task (no prior convention exists): critical < 50, warning 50-79,
#: healthy >= 80 - the same "a single critical finding costs a lot" spirit
#: as the score formula itself (score 50 already implies roughly 3+ open
#: criticals, or an equivalent mix).
ProjectHealthBucket = Literal["healthy", "warning", "critical"]


class AdminProjectHealthItem(BaseModel):
    bucket: ProjectHealthBucket
    count: int


class AdminSummaryResponse(BaseModel):
    users: AdminUserCounts
    content: AdminContentCounts
    system_status: str
    audit_events: int = 0
    recent_admin_actions: int = 0
    #: Task 7: vuln-lifecycle admin overview additions. Every count below is
    #: a real aggregate query - see backend.api.admin.summary.
    active_workspaces: int = 0
    active_projects: int = 0
    open_findings: int = 0
    critical_findings: int = 0
    high_findings: int = 0
    overdue_findings: int = 0
    waiting_verify_findings: int = 0
    fixed_this_week_findings: int = 0
    project_health: list[AdminProjectHealthItem] = Field(default_factory=list)


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
