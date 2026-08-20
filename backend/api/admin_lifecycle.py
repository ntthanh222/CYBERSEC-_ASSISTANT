"""Admin Console visibility over the vuln-lifecycle entities (Task 7):
Workspaces, Projects, Findings - cross-project/cross-workspace, not
membership-scoped, plus one admin-only bypass action (archive any project).

Kept as a sibling file to ``backend/api/admin.py`` (rather than growing that
file further) - same router-level ``Depends(require_admin)`` convention,
same ``get_db`` (never ``get_rls_db``) rationale every other admin route
already documents: the admin check itself is authoritative, RLS visibility
must never gate it.

This module is deliberately thin: every list reuses the repository/service
layer prior tasks already built (``WorkspaceService``, ``ProjectService``,
``FindingRepository``) rather than re-implementing project/finding business
logic. SLA policy admin endpoints already exist at
``backend/api/sla_policies.py`` (Task 3) and are not duplicated here.
"""
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import PageParams, page_params
from backend.core.actor import get_current_actor
from backend.core.authorization import AppUser, require_admin
from backend.database.models.finding import Finding
from backend.database.session import get_db
from backend.repositories.findings import FindingRepository
from backend.repositories.project import ProjectRepository
from backend.repositories.project_members import ProjectMemberRepository
from backend.repositories.rbac import RbacRepository
from backend.repositories.workspace_members import WorkspaceMemberRepository
from backend.schemas.admin_lifecycle import (
    AdminFindingPage,
    AdminProjectPage,
    AdminWorkspacePage,
)
from backend.schemas.health import ErrorResponse
from backend.services import sla as sla_service
from backend.services.project import ProjectService
from backend.services.workspace import WorkspaceService

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)])

_UNAUTHORIZED = {401: {"model": ErrorResponse, "description": "Missing or invalid bearer token."}}
_FORBIDDEN = {403: {"model": ErrorResponse, "description": "Administrator privileges required."}}
_NOT_FOUND = {404: {"model": ErrorResponse, "description": "Project not found."}}


def _finding_dict(record: Finding, *, project_name: str) -> dict[str, Any]:
    # Mirrors backend.api.findings._finding_dict + the project_name field
    # backend.api.my_tasks's MyTaskItem already adds - duplicated (not
    # imported across API modules) same as project_dashboard.py's own copy
    # already does, for the same reason (no api -> api dependency).
    return {
        "id": record.id,
        "project_id": record.project_id,
        "scan_run_id": record.scan_run_id,
        "fingerprint": record.fingerprint,
        "rule_id": record.rule_id,
        "category": record.category,
        "title": record.title,
        "evidence": record.evidence,
        "impact": record.impact,
        "remediation": record.remediation,
        "severity": record.severity,
        "status": record.status,
        "target": record.target,
        "cve_id": record.cve_id,
        "assignee_user_id": record.assignee_user_id,
        "deadline": record.deadline,
        "is_overdue": sla_service.is_overdue(record),
        "verification_notes": record.verification_notes,
        "resolution_reason": record.resolution_reason,
        "first_seen_scan_run_id": record.first_seen_scan_run_id,
        "last_seen_scan_run_id": record.last_seen_scan_run_id,
        "closed_at": record.closed_at,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
        "project_name": project_name,
    }


@router.get(
    "/workspaces",
    response_model=AdminWorkspacePage,
    summary="List every workspace",
    description="Every workspace regardless of the caller's membership, with member and "
    "project counts per row.",
    responses={**_UNAUTHORIZED, **_FORBIDDEN},
)
async def list_admin_workspaces(
    admin: AppUser = Depends(require_admin),
    pagination: PageParams = Depends(page_params),
    session: AsyncSession = Depends(get_db),
) -> dict:
    service = WorkspaceService(session)
    workspace_members = WorkspaceMemberRepository(session)
    projects_repo = ProjectRepository(session)
    items, total = await service.list(
        user_id=admin.id, is_global_admin=True, page=pagination.page, page_size=pagination.page_size
    )
    rows = []
    for workspace in items:
        member_count = await workspace_members.count_all(workspace_id=workspace.id)
        project_count = await projects_repo.count_for_workspace(workspace_id=workspace.id)
        rows.append(
            {
                "id": workspace.id,
                "name": workspace.name,
                "description": workspace.description,
                "created_by_user_id": workspace.created_by_user_id,
                "member_count": member_count,
                "project_count": project_count,
                "created_at": workspace.created_at,
                "updated_at": workspace.updated_at,
            }
        )
    return {"items": rows, "total": total, "page": pagination.page, "page_size": pagination.page_size}


@router.get(
    "/projects",
    response_model=AdminProjectPage,
    summary="List every project",
    description="Every project regardless of the caller's membership, filterable by "
    "workspace_id, environment, criticality, and status. Includes member and open-finding "
    "counts per row.",
    responses={**_UNAUTHORIZED, **_FORBIDDEN},
)
async def list_admin_projects(
    admin: AppUser = Depends(require_admin),
    pagination: PageParams = Depends(page_params),
    workspace_id: Optional[uuid.UUID] = Query(default=None),
    environment: Optional[str] = Query(default=None),
    criticality: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    session: AsyncSession = Depends(get_db),
) -> dict:
    service = ProjectService(session)
    project_members = ProjectMemberRepository(session)
    findings_repo = FindingRepository(session)
    items, total = await service.list(
        user_id=admin.id,
        is_global_admin=True,
        workspace_id=workspace_id,
        include_archived=True,
        page=pagination.page,
        page_size=pagination.page_size,
        environment=environment,
        criticality=criticality,
        status=status,
    )
    rows = []
    for project in items:
        member_count = await project_members.count_all(project_id=project.id)
        open_findings_count = await findings_repo.count_open(project_id=project.id)
        rows.append(
            {
                "id": project.id,
                "workspace_id": project.workspace_id,
                "name": project.name,
                "domain": project.domain,
                "environment": project.environment,
                "criticality": project.criticality,
                "internet_facing": project.internet_facing,
                "technologies": project.technologies,
                "status": project.status,
                "archived_at": project.archived_at,
                "owner_user_id": project.owner_user_id,
                "member_count": member_count,
                "open_findings_count": open_findings_count,
                "created_at": project.created_at,
                "updated_at": project.updated_at,
            }
        )
    return {"items": rows, "total": total, "page": pagination.page, "page_size": pagination.page_size}


@router.post(
    "/projects/{project_id}/archive",
    summary="Archive any project (admin bypass)",
    description="Unlike POST /api/projects/{id}/archive, this requires no project role at "
    "all - only the router-wide admin gate. Writes an AdminAuditLog row, same as every other "
    "admin mutation.",
    responses={**_UNAUTHORIZED, **_FORBIDDEN, **_NOT_FOUND},
)
async def archive_project_as_admin(
    project_id: uuid.UUID,
    admin: AppUser = Depends(require_admin),
    actor: str = Depends(get_current_actor),
    session: AsyncSession = Depends(get_db),
) -> dict:
    service = ProjectService(session)
    project = await service.archive(project_id, actor=actor)

    rbac_repo = RbacRepository(session)
    await rbac_repo.record_audit(
        actor_user_id=admin.id,
        action="project_archived_by_admin",
        target_user_id=None,
        metadata={"project_id": str(project_id)},
    )
    await session.commit()

    return {
        "id": project.id,
        "workspace_id": project.workspace_id,
        "name": project.name,
        "domain": project.domain,
        "environment": project.environment,
        "criticality": project.criticality,
        "internet_facing": project.internet_facing,
        "technologies": project.technologies,
        "status": project.status,
        "archived_at": project.archived_at,
        "owner_user_id": project.owner_user_id,
        "created_at": project.created_at,
        "updated_at": project.updated_at,
    }


@router.get(
    "/findings",
    response_model=AdminFindingPage,
    summary="List findings across every project",
    description="Filterable by project_id, severity, status, assignee_user_id, and overdue. "
    "The requirement's named sub-views (Open/Critical/High/Overdue/Waiting Verify/Fixed This "
    "Week/Accepted Risk/False Positive) are all filter presets on this one endpoint: "
    "?status=open, ?severity=critical, ?severity=high, ?overdue=true, ?status=fixed "
    "(waiting verify), ?status=accepted_risk, ?status=false_positive, and either "
    "?preset=fixed_this_week or ?status=closed&fixed_since=<iso8601> for Fixed This Week.",
    responses={**_UNAUTHORIZED, **_FORBIDDEN},
)
async def list_admin_findings(
    project_id: Optional[uuid.UUID] = Query(default=None),
    severity: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    assignee_user_id: Optional[uuid.UUID] = Query(default=None),
    overdue: Optional[bool] = Query(default=None),
    fixed_since: Optional[datetime] = Query(default=None),
    preset: Optional[Literal["fixed_this_week"]] = Query(
        default=None,
        description="'fixed_this_week' is a convenience for status=closed + fixed_since=7 "
        "days ago - explicit status/fixed_since values win if also given.",
    ),
    pagination: PageParams = Depends(page_params),
    session: AsyncSession = Depends(get_db),
) -> dict:
    effective_status = status
    effective_fixed_since = fixed_since
    if preset == "fixed_this_week":
        effective_status = effective_status or "closed"
        effective_fixed_since = effective_fixed_since or (
            datetime.now(timezone.utc) - timedelta(days=7)
        )

    repo = FindingRepository(session)
    rows, total = await repo.list_for_admin(
        project_id=project_id,
        status=effective_status,
        severity=severity,
        assignee_user_id=assignee_user_id,
        overdue=overdue,
        fixed_since=effective_fixed_since,
        page=pagination.page,
        page_size=pagination.page_size,
    )
    return {
        "items": [_finding_dict(finding, project_name=project_name) for finding, project_name in rows],
        "total": total,
        "page": pagination.page,
        "page_size": pagination.page_size,
    }
