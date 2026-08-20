"""Response models for the project-scoped Security Dashboard (Task 5).

Pure read/aggregation over Finding/ScanRun - see
``backend.services.project_dashboard.ProjectDashboardService`` for the exact
queries and the documented security-score formula.
"""
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from backend.schemas.common import UtcDatetime
from backend.schemas.findings import FindingItem


class SeverityBreakdown(BaseModel):
    critical: int = Field(examples=[2])
    high: int = Field(examples=[5])
    medium: int = Field(examples=[3])
    low: int = Field(examples=[1])


class LatestScanSummary(BaseModel):
    id: UUID
    status: str
    target: str
    completed_at: Optional[UtcDatetime] = None
    summary: dict


class SecurityTrendPoint(BaseModel):
    """One point derived from a real, already-``completed`` ``ScanRun``'s
    stored ``summary`` severity counts - see ``ProjectDashboardService.
    _trend_point`` for how ``score``/``open_count`` are computed from it."""

    scan_run_id: UUID
    completed_at: Optional[UtcDatetime] = None
    open_count: int
    score: int


class AssigneeWorkload(BaseModel):
    assignee_user_id: UUID
    open_count: int


class ProjectSecurityDashboard(BaseModel):
    project_id: UUID
    security_score: int = Field(ge=0, le=100)
    open_findings: int
    open_by_severity: SeverityBreakdown
    waiting_verify: int
    overdue: int
    fixed_this_week: int
    latest_scan: Optional[LatestScanSummary] = None
    security_trend: list[SecurityTrendPoint]
    top_risks: list[FindingItem]
    latest_findings: list[FindingItem]
    assigned_open: int
    assigned_open_by_assignee: list[AssigneeWorkload]
