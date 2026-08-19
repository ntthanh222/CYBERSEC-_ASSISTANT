"""Request/response models for findings and finding transitions."""
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from backend.schemas.common import Page, UtcDatetime

FindingSeverity = Literal["low", "medium", "high", "critical"]
FindingStatus = Literal[
    "open",
    "confirmed",
    "in_progress",
    "fixed",
    "verified",
    "closed",
    "false_positive",
    "accepted_risk",
    "reopened",
]


class FindingCreate(BaseModel):
    rule_id: str = Field(min_length=1, max_length=100)
    category: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=240)
    evidence: str = Field(default="")
    impact: str = Field(default="")
    remediation: str = Field(default="")
    severity: FindingSeverity
    target: str = Field(min_length=1, max_length=2048)
    cve_id: Optional[str] = Field(default=None, max_length=32)
    assignee_user_id: Optional[UUID] = None


class FindingTransitionRequest(BaseModel):
    to_status: FindingStatus
    reason: Optional[str] = Field(default=None, max_length=4000)


class FindingAssigneeUpdate(BaseModel):
    assignee_user_id: Optional[UUID] = None


class FindingItem(BaseModel):
    id: UUID
    project_id: UUID
    scan_run_id: Optional[UUID] = None
    fingerprint: str
    rule_id: str
    category: str
    title: str
    evidence: str
    impact: str
    remediation: str
    severity: FindingSeverity
    status: FindingStatus
    target: str
    cve_id: Optional[str] = None
    assignee_user_id: Optional[UUID] = None
    deadline: Optional[UtcDatetime] = None
    #: Computed at read time (backend.services.sla.is_overdue) - never a
    #: stored column, so it can never drift out of sync with "now" or the
    #: finding's current status. See backend/api/findings.py's _finding_dict.
    is_overdue: bool = False
    verification_notes: str
    resolution_reason: Optional[str] = None
    first_seen_scan_run_id: Optional[UUID] = None
    last_seen_scan_run_id: Optional[UUID] = None
    closed_at: Optional[UtcDatetime] = None
    created_at: UtcDatetime
    updated_at: UtcDatetime


class FindingPage(Page[FindingItem]):
    pass


class EligibleAssigneeItem(BaseModel):
    """A project member eligible to be a Finding's assignee (Task 4) -
    developer/security/owner project roles, never viewer. No local ``User``
    table exists in this app (identity comes from Supabase ``auth.users``) -
    same as ``ProjectMemberItem`` (Task 1), this deliberately returns only
    ``user_id``/``project_role`` rather than inventing a display-name/email
    resolution the rest of the app doesn't have either."""

    user_id: UUID
    project_role: Literal["developer", "security", "owner"]


class EligibleAssigneeList(BaseModel):
    items: list[EligibleAssigneeItem]


class MyTaskItem(FindingItem):
    """A ``FindingItem`` plus its parent project's name, for the
    cross-project "My Tasks" view (Task 4)."""

    project_name: str


class MyTaskPage(Page[MyTaskItem]):
    pass


class FindingTransitionItem(BaseModel):
    id: UUID
    finding_id: UUID
    from_status: str
    to_status: str
    actor_user_id: UUID
    reason: Optional[str] = None
    created_at: UtcDatetime
