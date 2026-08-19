"""Finding API - project-scoped, on top of Task 1's project authorization.

List/detail: any project member. Manual creation and assignee-setting:
owner/security project role (or the workspace-owner/admin bypass, or a
global admin). Transition: gated at the route level only by
``get_project_member`` (any member may attempt one) - the fine-grained role
check happens inside ``FindingService.transition`` via the state machine,
since which roles may perform a transition depends on which specific
from_status/to_status pair is being attempted, not a single fixed role for
the whole endpoint (e.g. a developer assignee may move in_progress->fixed
but never fixed->verified).
"""
import uuid
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import PageParams, page_params
from backend.core.actor import get_current_actor
from backend.core.authorization import AppUser, get_app_user
from backend.core.auth import get_current_user
from backend.core.project_authorization import get_project_member, require_project_role
from backend.database.models.finding import Finding
from backend.database.models.project import ProjectMember
from backend.database.session import get_rls_db
from backend.schemas.findings import (
    EligibleAssigneeList,
    FindingAssigneeUpdate,
    FindingCreate,
    FindingItem,
    FindingPage,
    FindingTransitionRequest,
)
from backend.schemas.health import ErrorResponse
from backend.services import sla as sla_service
from backend.services.finding import FindingService

router = APIRouter(
    prefix="/api/projects/{project_id}/findings",
    tags=["findings"],
    dependencies=[Depends(get_current_user)],
)
_UNAUTHORIZED = {401: {"model": ErrorResponse, "description": "Missing or invalid bearer token."}}
_FORBIDDEN = {403: {"model": ErrorResponse, "description": "Insufficient project role."}}
_NOT_FOUND = {404: {"model": ErrorResponse, "description": "Project or finding not found."}}
_MANAGE_ROLES = ("owner", "security")


def _finding_dict(record: Finding) -> dict[str, Any]:
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
    }


@router.get(
    "",
    summary="List findings",
    description="Filterable by status, severity, assignee_user_id, and overdue. Any project "
    "member (including viewer/developer) may view this.",
    response_model=FindingPage,
    responses={**_UNAUTHORIZED, **_NOT_FOUND},
)
async def list_findings(
    project_id: uuid.UUID,
    status: Optional[str] = Query(default=None),
    severity: Optional[str] = Query(default=None),
    assignee_user_id: Optional[uuid.UUID] = Query(default=None),
    overdue: Optional[bool] = Query(default=None, description="Filter to overdue (or not-overdue) findings only."),
    pagination: PageParams = Depends(page_params),
    session: AsyncSession = Depends(get_rls_db),
    _member: ProjectMember | None = Depends(get_project_member),
) -> dict:
    service = FindingService(session)
    items, total = await service.list(
        project_id=project_id,
        status=status,
        severity=severity,
        assignee_user_id=assignee_user_id,
        overdue=overdue,
        page=pagination.page,
        page_size=pagination.page_size,
    )
    return {
        "items": [_finding_dict(item) for item in items],
        "total": total,
        "page": pagination.page,
        "page_size": pagination.page_size,
    }


@router.get(
    "/eligible-assignees",
    summary="List eligible Finding assignees for this project",
    description="Project members with project_role in (developer, security, owner) - the "
    "same eligibility set FindingService.set_assignee validates against. Any project member "
    "may view this (it powers the assignee picker).",
    response_model=EligibleAssigneeList,
    responses={**_UNAUTHORIZED, **_NOT_FOUND},
)
async def list_eligible_assignees(
    project_id: uuid.UUID,
    session: AsyncSession = Depends(get_rls_db),
    _member: ProjectMember | None = Depends(get_project_member),
) -> dict:
    service = FindingService(session)
    members = await service.list_eligible_assignees(project_id)
    return {
        "items": [
            {"user_id": member.user_id, "project_role": member.project_role}
            for member in members
        ]
    }


@router.get(
    "/{finding_id}",
    summary="Get one finding",
    response_model=FindingItem,
    responses={**_UNAUTHORIZED, **_NOT_FOUND},
)
async def get_finding(
    project_id: uuid.UUID,
    finding_id: uuid.UUID,
    session: AsyncSession = Depends(get_rls_db),
    _member: ProjectMember | None = Depends(get_project_member),
) -> dict:
    service = FindingService(session)
    record = await service.get(finding_id, project_id=project_id)
    return _finding_dict(record)


@router.post(
    "",
    status_code=201,
    summary="Create a finding manually",
    description="Requires an owner/security project role (or the workspace-owner/admin "
    "bypass, or a global admin). scan_run_id is left null - this finding was not produced "
    "by a scan.",
    response_model=FindingItem,
    responses={422: {"model": ErrorResponse, "description": "Invalid body."}, **_UNAUTHORIZED, **_FORBIDDEN, **_NOT_FOUND},
)
async def create_finding(
    project_id: uuid.UUID,
    body: FindingCreate,
    session: AsyncSession = Depends(get_rls_db),
    app_user: AppUser = Depends(get_app_user),
    actor_label: str = Depends(get_current_actor),
    _member: ProjectMember | None = Depends(require_project_role(*_MANAGE_ROLES)),
) -> dict:
    service = FindingService(session)
    record = await service.create_manual(
        project_id=project_id,
        rule_id=body.rule_id,
        category=body.category,
        title=body.title,
        evidence=body.evidence,
        impact=body.impact,
        remediation=body.remediation,
        severity=body.severity,
        target=body.target,
        cve_id=body.cve_id,
        assignee_user_id=body.assignee_user_id,
        actor=app_user,
        actor_label=actor_label,
    )
    return _finding_dict(record)


@router.post(
    "/{finding_id}/transition",
    summary="Transition a finding's status",
    description="The state machine (backend.services.finding_state_machine) enforces which "
    "roles may perform this specific from_status->to_status transition - see its module "
    "docstring. A developer project-role actor can never transition fixed->verified or "
    "verified->closed, even as the assignee.",
    response_model=FindingItem,
    responses={
        **_UNAUTHORIZED,
        **_FORBIDDEN,
        **_NOT_FOUND,
        422: {"model": ErrorResponse, "description": "Invalid transition or missing reason."},
    },
)
async def transition_finding(
    project_id: uuid.UUID,
    finding_id: uuid.UUID,
    body: FindingTransitionRequest,
    session: AsyncSession = Depends(get_rls_db),
    app_user: AppUser = Depends(get_app_user),
    actor_label: str = Depends(get_current_actor),
    _member: ProjectMember | None = Depends(get_project_member),
) -> dict:
    service = FindingService(session)
    record = await service.transition(
        finding_id,
        project_id=project_id,
        to_status=body.to_status,
        reason=body.reason,
        actor=app_user,
        actor_label=actor_label,
    )
    return _finding_dict(record)


@router.patch(
    "/{finding_id}/assignee",
    summary="Set a finding's assignee",
    description="Callable only by owner/security (or the workspace-owner/admin bypass, or a "
    "global admin). assignee_user_id must be an active project member with role developer, "
    "security, or owner (never viewer) - see FindingService.set_assignee. Passing null always "
    "succeeds (unassigning is always safe).",
    response_model=FindingItem,
    responses={
        **_UNAUTHORIZED,
        **_FORBIDDEN,
        **_NOT_FOUND,
        422: {"model": ErrorResponse, "description": "assignee_user_id is not an eligible project member."},
    },
)
async def set_finding_assignee(
    project_id: uuid.UUID,
    finding_id: uuid.UUID,
    body: FindingAssigneeUpdate,
    session: AsyncSession = Depends(get_rls_db),
    app_user: AppUser = Depends(get_app_user),
    actor_label: str = Depends(get_current_actor),
    _member: ProjectMember | None = Depends(require_project_role(*_MANAGE_ROLES)),
) -> dict:
    service = FindingService(session)
    record = await service.set_assignee(
        finding_id,
        project_id=project_id,
        assignee_user_id=body.assignee_user_id,
        actor=app_user,
        actor_label=actor_label,
    )
    return _finding_dict(record)
