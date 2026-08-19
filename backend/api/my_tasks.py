"""Cross-project "My Tasks" API (Task 4).

Deliberately its own tiny router, not nested under
``backend.api.findings``'s ``/api/projects/{project_id}/findings`` prefix -
this view genuinely spans projects by design (a developer's assignments
across every project they've ever been assigned a Finding in), so there is
no single ``project_id`` to gate on. Router-level ``get_current_user`` is the
only auth dependency - the query itself is inherently authorization-safe
because it always filters ``WHERE assignee_user_id = caller.id``, so a
caller can only ever see their own assignments (see
``FindingRepository.list_by_assignee``'s docstring for why this remains true
even after the caller is later removed as a project member).
"""
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import PageParams, page_params
from backend.core.authorization import AppUser, get_app_user
from backend.core.auth import get_current_user
from backend.database.models.finding import Finding
from backend.database.session import get_rls_db
from backend.schemas.findings import MyTaskPage
from backend.schemas.health import ErrorResponse
from backend.services import sla as sla_service
from backend.services.finding import FindingService

router = APIRouter(prefix="/api/findings", tags=["findings"], dependencies=[Depends(get_current_user)])
_UNAUTHORIZED = {401: {"model": ErrorResponse, "description": "Missing or invalid bearer token."}}


def _my_task_dict(record: Finding, project_name: str) -> dict[str, Any]:
    return {
        "id": record.id,
        "project_id": record.project_id,
        "project_name": project_name,
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
    }


@router.get(
    "/my-tasks",
    summary="My Tasks - every Finding assigned to the caller, across every project",
    description="Filterable by status, severity, and overdue. Cross-project by design: any "
    "authenticated user may call this (no per-project membership dependency), and the result "
    "set is always scoped to the caller's own assignee_user_id.",
    response_model=MyTaskPage,
    responses={**_UNAUTHORIZED},
)
async def list_my_tasks(
    status: Optional[str] = Query(default=None),
    severity: Optional[str] = Query(default=None),
    overdue: Optional[bool] = Query(default=None, description="Filter to overdue (or not-overdue) findings only."),
    pagination: PageParams = Depends(page_params),
    session: AsyncSession = Depends(get_rls_db),
    app_user: AppUser = Depends(get_app_user),
) -> dict:
    service = FindingService(session)
    items, total = await service.list_my_tasks(
        actor=app_user,
        status=status,
        severity=severity,
        overdue=overdue,
        page=pagination.page,
        page_size=pagination.page_size,
    )
    return {
        "items": [_my_task_dict(record, project_name) for record, project_name in items],
        "total": total,
        "page": pagination.page,
        "page_size": pagination.page_size,
    }
