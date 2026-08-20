"""Project-scoped CVE risk prioritization API (Task 6).

Additive layer on top of the existing generic `/api/cves` lookup - this
router calls into `CveLookupService` via `ProjectCveService`, it does not
replace or modify `backend/api/cves.py`. Authorization follows the same
`backend.core.project_authorization` pattern every prior task's project-
scoped routes use: triggering a new assessment is gated to
owner/security (a security-analyst-tier action, consistent with how
scan-triggering was gated in Task 2); listing/reading is open to any
project member.
"""
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.actor import get_current_actor
from backend.core.auth import get_current_user
from backend.core.authorization import AppUser, get_app_user
from backend.core.project_authorization import get_project_member, require_project_role
from backend.database.models.cve_assessment import CveAssessment
from backend.database.models.project import ProjectMember
from backend.database.session import get_rls_db
from backend.schemas.cve_priority import CveAssessmentRequest, CveAssessmentResponse
from backend.schemas.health import ErrorResponse
from backend.services.project_cve import ProjectCveService

_UNAUTHORIZED = {401: {"model": ErrorResponse, "description": "Missing or invalid bearer token."}}
_FORBIDDEN = {403: {"model": ErrorResponse, "description": "Insufficient project role."}}
_NOT_FOUND = {404: {"model": ErrorResponse, "description": "Project or assessment not found."}}
_ASSESS_ROLES = ("owner", "security")

router = APIRouter(
    prefix="/api/projects/{project_id}/cve-assessments",
    tags=["cve-priority"],
    dependencies=[Depends(get_current_user)],
)


def _to_response(record: CveAssessment) -> dict:
    return {
        "id": record.id,
        "project_id": record.project_id,
        "cve_id": record.cve_id,
        "cvss_score": record.cvss_score,
        "epss_score": record.epss_score,
        "is_kev": record.is_kev,
        "affected_version": record.affected_version,
        "fixed_version": record.fixed_version,
        "technology": record.technology,
        "priority": record.priority,
        "score": record.score,
        "rationale": record.rationale,
        "finding_id": record.finding_id,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }


@router.post(
    "",
    summary="Run a project-aware CVE risk assessment",
    description=(
        "Looks up the CVE via the existing NVD-backed lookup, enriches it with EPSS "
        "exploit-probability and CISA KEV status, blends in this project's criticality/"
        "internet-facing context, and persists the deterministic priority label + "
        "rationale. Re-running for the same CVE updates the existing assessment "
        "(upsert) rather than creating a duplicate. May auto-create/link a Finding "
        "for patch_now/high priority results."
    ),
    response_model=CveAssessmentResponse,
    status_code=201,
    responses={
        400: {"model": ErrorResponse, "description": "Malformed CVE id."},
        404: {"model": ErrorResponse, "description": "CVE or project not found."},
        **_UNAUTHORIZED,
        **_FORBIDDEN,
    },
)
async def assess_cve(
    project_id: uuid.UUID,
    body: CveAssessmentRequest,
    session: AsyncSession = Depends(get_rls_db),
    app_user: AppUser = Depends(get_app_user),
    actor: str = Depends(get_current_actor),
    _member: ProjectMember | None = Depends(require_project_role(*_ASSESS_ROLES)),
) -> dict:
    service = ProjectCveService(session)
    record = await service.assess_cve(
        project_id=project_id,
        cve_id=body.cve_id,
        affected_version=body.affected_version,
        actor=app_user,
        actor_label=actor,
    )
    return _to_response(record)


@router.get(
    "",
    summary="List CVE assessments for a project",
    response_model=list[CveAssessmentResponse],
    responses={**_UNAUTHORIZED, **_NOT_FOUND},
)
async def list_cve_assessments(
    project_id: uuid.UUID,
    session: AsyncSession = Depends(get_rls_db),
    _member: ProjectMember | None = Depends(get_project_member),
) -> list[dict]:
    service = ProjectCveService(session)
    records = await service.list_for_project(project_id)
    return [_to_response(record) for record in records]


@router.get(
    "/{cve_id}",
    summary="Get a project's CVE assessment detail",
    response_model=CveAssessmentResponse,
    responses={**_UNAUTHORIZED, **_NOT_FOUND},
)
async def get_cve_assessment(
    project_id: uuid.UUID,
    cve_id: str,
    session: AsyncSession = Depends(get_rls_db),
    _member: ProjectMember | None = Depends(get_project_member),
) -> dict:
    service = ProjectCveService(session)
    record = await service.get_for_project(project_id, cve_id)
    return _to_response(record)
