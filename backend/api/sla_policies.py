"""SLA policy API (Task 3).

Global defaults (``project_id IS NULL``) are admin-only, same pattern as
``backend/api/admin.py`` - ``Depends(require_admin)``, ``get_db`` (not
``get_rls_db``, matching every other admin route's rationale: this is the
authoritative check, RLS visibility must never gate it).

Project-level overrides follow the project-authorization pattern from
``backend/api/scans.py``/``backend/api/findings.py``: any project member may
read the effective (override-merged-with-default) policy, only
owner/security (or the workspace-owner/admin bypass, or a global admin) may
set/clear an override.
"""
import uuid
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.authorization import require_admin
from backend.core.auth import get_current_user
from backend.core.exceptions import NotFoundError
from backend.core.project_authorization import get_project_member, require_project_role
from backend.database.models.finding import FINDING_SEVERITIES
from backend.database.models.project import ProjectMember
from backend.database.models.sla_policy import SlaPolicy
from backend.database.session import get_db, get_rls_db
from backend.repositories.sla_policies import SlaPolicyRepository
from backend.schemas.health import ErrorResponse
from backend.schemas.sla_policies import (
    EffectiveSlaPolicyItem,
    SlaPolicyGlobalUpdate,
    SlaPolicyItem,
    SlaPolicyProjectUpsert,
)

_UNAUTHORIZED = {401: {"model": ErrorResponse, "description": "Missing or invalid bearer token."}}
_FORBIDDEN = {403: {"model": ErrorResponse, "description": "Insufficient role."}}
_NOT_FOUND = {404: {"model": ErrorResponse, "description": "Project not found."}}
_PROJECT_MANAGE_ROLES = ("owner", "security")

admin_router = APIRouter(
    prefix="/api/admin/sla-policies",
    tags=["sla-policies"],
    dependencies=[Depends(require_admin)],
)
project_router = APIRouter(
    prefix="/api/projects/{project_id}/sla-policies",
    tags=["sla-policies"],
    dependencies=[Depends(get_current_user)],
)


def _policy_dict(record: SlaPolicy) -> dict[str, Any]:
    return {
        "id": record.id,
        "project_id": record.project_id,
        "severity": record.severity,
        "hours_to_deadline": record.hours_to_deadline,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }


@admin_router.get(
    "",
    summary="List global default SLA policies",
    response_model=list[SlaPolicyItem],
    responses={**_UNAUTHORIZED, **_FORBIDDEN},
)
async def list_global_sla_policies(session: AsyncSession = Depends(get_db)) -> list[dict]:
    repo = SlaPolicyRepository(session)
    rows = await repo.list_global()
    return [_policy_dict(row) for row in rows]


@admin_router.patch(
    "/{severity}",
    summary="Set a global default SLA policy's hours_to_deadline",
    description="Upserts - creates the row if this severity has no global default yet (e.g. "
    "seeding a policy for `low`, which ships with none).",
    response_model=SlaPolicyItem,
    responses={
        404: {"model": ErrorResponse, "description": "Unknown severity."},
        422: {"model": ErrorResponse, "description": "Invalid body (hours_to_deadline <= 0)."},
        **_UNAUTHORIZED,
        **_FORBIDDEN,
    },
)
async def update_global_sla_policy(
    severity: str, body: SlaPolicyGlobalUpdate, session: AsyncSession = Depends(get_db)
) -> dict:
    if severity not in FINDING_SEVERITIES:
        raise NotFoundError(f"Unknown severity '{severity}'.")
    repo = SlaPolicyRepository(session)
    record = await repo.upsert_global(severity=severity, hours_to_deadline=body.hours_to_deadline)
    await session.commit()
    return _policy_dict(record)


@project_router.get(
    "",
    summary="Effective SLA policy for a project",
    description="One row per severity: the project's own override if it has one, else the "
    "global default, else `hours_to_deadline: null` (no SLA applies to that severity). Any "
    "project member (including viewer/developer) may view this.",
    response_model=list[EffectiveSlaPolicyItem],
    responses={**_UNAUTHORIZED, **_NOT_FOUND},
)
async def get_effective_sla_policies(
    project_id: uuid.UUID,
    session: AsyncSession = Depends(get_rls_db),
    _member: ProjectMember | None = Depends(get_project_member),
) -> list[dict]:
    repo = SlaPolicyRepository(session)
    globals_by_severity = {row.severity: row for row in await repo.list_global()}
    overrides_by_severity = {
        row.severity: row for row in await repo.list_project_overrides(project_id)
    }

    effective: list[dict] = []
    for severity in FINDING_SEVERITIES:
        if severity in overrides_by_severity:
            effective.append(
                {
                    "severity": severity,
                    "hours_to_deadline": overrides_by_severity[severity].hours_to_deadline,
                    "source": "project_override",
                }
            )
        elif severity in globals_by_severity:
            effective.append(
                {
                    "severity": severity,
                    "hours_to_deadline": globals_by_severity[severity].hours_to_deadline,
                    "source": "global_default",
                }
            )
        else:
            effective.append({"severity": severity, "hours_to_deadline": None, "source": "none"})
    return effective


@project_router.put(
    "/{severity}",
    summary="Set or clear a project-level SLA override",
    description="`hours_to_deadline: null` clears the override (the project reverts to the "
    "global default for this severity). Requires an owner/security project role (or the "
    "workspace-owner/admin bypass, or a global admin).",
    response_model=EffectiveSlaPolicyItem,
    responses={
        422: {"model": ErrorResponse, "description": "Invalid body (hours_to_deadline <= 0)."},
        **_UNAUTHORIZED,
        **_FORBIDDEN,
        **_NOT_FOUND,
    },
)
async def set_project_sla_override(
    project_id: uuid.UUID,
    severity: str,
    body: SlaPolicyProjectUpsert,
    session: AsyncSession = Depends(get_rls_db),
    _member: ProjectMember | None = Depends(require_project_role(*_PROJECT_MANAGE_ROLES)),
) -> dict:
    if severity not in FINDING_SEVERITIES:
        raise NotFoundError(f"Unknown severity '{severity}'.")
    repo = SlaPolicyRepository(session)

    if body.hours_to_deadline is None:
        await repo.delete_project_override(project_id=project_id, severity=severity)
        await session.commit()
        global_policy = await repo.get_global(severity)
        return {
            "severity": severity,
            "hours_to_deadline": global_policy.hours_to_deadline if global_policy else None,
            "source": "global_default" if global_policy else "none",
        }

    record = await repo.upsert_project_override(
        project_id=project_id, severity=severity, hours_to_deadline=body.hours_to_deadline
    )
    await session.commit()
    return {
        "severity": severity,
        "hours_to_deadline": record.hours_to_deadline,
        "source": "project_override",
    }
