"""Scan run API - project-scoped, on top of Task 1's project authorization.

Triggering a scan requires an owner/security project role (or the
workspace-owner/admin bypass, or a global admin); any project member
(including viewer/developer) may view scan history. See
``backend.core.project_authorization``.
"""
import uuid
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import PageParams, page_params
from backend.core.authorization import AppUser, get_app_user
from backend.core.auth import get_current_user
from backend.core.exceptions import NotFoundError
from backend.core.project_authorization import get_project_member, require_project_role
from backend.database.models.project import ProjectMember
from backend.database.models.scan import ScanRun
from backend.database.session import get_rls_db
from backend.repositories.scan_runs import ScanRunRepository
from backend.schemas.health import ErrorResponse
from backend.schemas.scans import ScanRunCreate, ScanRunItem, ScanRunPage
from backend.services.scan_orchestrator import ScanOrchestrator

router = APIRouter(
    prefix="/api/projects/{project_id}/scans",
    tags=["scans"],
    dependencies=[Depends(get_current_user)],
)
_UNAUTHORIZED = {401: {"model": ErrorResponse, "description": "Missing or invalid bearer token."}}
_FORBIDDEN = {403: {"model": ErrorResponse, "description": "Insufficient project role."}}
_NOT_FOUND = {404: {"model": ErrorResponse, "description": "Project or scan run not found."}}
_TRIGGER_ROLES = ("owner", "security")


def _scan_dict(record: ScanRun) -> dict[str, Any]:
    return {
        "id": record.id,
        "project_id": record.project_id,
        "triggered_by_user_id": record.triggered_by_user_id,
        "scan_type": record.scan_type,
        "target": record.target,
        "status": record.status,
        "started_at": record.started_at,
        "completed_at": record.completed_at,
        "summary": record.summary,
        "previous_scan_run_id": record.previous_scan_run_id,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }


@router.post(
    "",
    status_code=201,
    summary="Trigger a scan",
    description="Runs the URL scanner synchronously against `target` and creates/updates "
    "Finding rows from its results. Requires an owner/security project role (or the "
    "workspace-owner/admin bypass, or a global admin).",
    response_model=ScanRunItem,
    responses={422: {"model": ErrorResponse, "description": "Invalid body."}, **_UNAUTHORIZED, **_FORBIDDEN, **_NOT_FOUND},
)
async def trigger_scan(
    project_id: uuid.UUID,
    body: ScanRunCreate,
    session: AsyncSession = Depends(get_rls_db),
    app_user: AppUser = Depends(get_app_user),
    _member: ProjectMember | None = Depends(require_project_role(*_TRIGGER_ROLES)),
) -> dict:
    orchestrator = ScanOrchestrator(session)
    record = await orchestrator.run_scan(project_id=project_id, target=body.target, actor=app_user)
    return _scan_dict(record)


@router.get(
    "",
    summary="List scan runs",
    description="Scan history for a project. Any project member (including viewer/developer) "
    "may view this.",
    response_model=ScanRunPage,
    responses={**_UNAUTHORIZED, **_NOT_FOUND},
)
async def list_scans(
    project_id: uuid.UUID,
    pagination: PageParams = Depends(page_params),
    session: AsyncSession = Depends(get_rls_db),
    _member: ProjectMember | None = Depends(get_project_member),
) -> dict:
    repo = ScanRunRepository(session)
    items, total = await repo.list_for_project(
        project_id=project_id, page=pagination.page, page_size=pagination.page_size
    )
    return {
        "items": [_scan_dict(item) for item in items],
        "total": total,
        "page": pagination.page,
        "page_size": pagination.page_size,
    }


@router.get(
    "/{scan_id}",
    summary="Get one scan run",
    response_model=ScanRunItem,
    responses={**_UNAUTHORIZED, **_NOT_FOUND},
)
async def get_scan(
    project_id: uuid.UUID,
    scan_id: uuid.UUID,
    session: AsyncSession = Depends(get_rls_db),
    _member: ProjectMember | None = Depends(get_project_member),
) -> dict:
    repo = ScanRunRepository(session)
    record = await repo.get(scan_id)
    if record is None or record.project_id != project_id:
        raise NotFoundError("Scan run not found.")
    return _scan_dict(record)
