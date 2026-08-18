"""MITRE ATT&CK coverage endpoints."""

from collections import defaultdict
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import PageParams, page_params
from backend.core.actor import get_current_actor
from backend.core.auth import AuthenticatedUser, get_current_user
from backend.database.models.mitre import MitreTechniqueCoverage
from backend.database.session import get_rls_db
from backend.schemas.health import ErrorResponse
from backend.schemas.mitre import (
    MitreMatrix,
    MitreTechniqueCreate,
    MitreTechniqueItem,
    MitreTechniquePage,
    MitreTechniqueUpdate,
)
from backend.services.mitre import MitreService

router = APIRouter(prefix="/api/mitre", tags=["mitre"], dependencies=[Depends(get_current_user)])
_UNAUTHORIZED = {401: {"model": ErrorResponse, "description": "Missing or invalid bearer token."}}


def _technique_dict(record: MitreTechniqueCoverage) -> dict[str, Any]:
    return {
        "id": record.id,
        "incident_id": record.incident_id,
        "technique_id": record.technique_id,
        "tactic": record.tactic,
        "name": record.name,
        "description": record.description,
        "detection": record.detection,
        "mitigation": record.mitigation,
        "coverage_status": record.coverage_status,
        "data_sources": record.data_sources,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }


@router.post(
    "/techniques", status_code=201, response_model=MitreTechniqueItem, responses={**_UNAUTHORIZED}
)
async def create_technique(
    body: MitreTechniqueCreate,
    session: AsyncSession = Depends(get_rls_db),
    user: AuthenticatedUser = Depends(get_current_user),
    actor: str = Depends(get_current_actor),
) -> dict[str, Any]:
    record = await MitreService(session).create(user_id=user.id, actor=actor, **body.model_dump())
    return _technique_dict(record)


@router.get("/techniques", response_model=MitreTechniquePage, responses={**_UNAUTHORIZED})
async def list_techniques(
    pagination: PageParams = Depends(page_params),
    search: Optional[str] = Query(default=None, max_length=200),
    tactic: Optional[str] = Query(default=None, max_length=80),
    coverage_status: Optional[str] = Query(default=None, pattern="^(planned|partial|covered|gap)$"),
    incident_id: Optional[UUID] = Query(default=None),
    session: AsyncSession = Depends(get_rls_db),
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    items, total = await MitreService(session).list(
        user_id=user.id,
        page=pagination.page,
        page_size=pagination.page_size,
        search=search,
        tactic=tactic,
        coverage_status=coverage_status,
        incident_id=incident_id,
    )
    return {
        "items": [_technique_dict(item) for item in items],
        "total": total,
        "page": pagination.page,
        "page_size": pagination.page_size,
    }


@router.get("/matrix", response_model=MitreMatrix, responses={**_UNAUTHORIZED})
async def get_matrix(
    session: AsyncSession = Depends(get_rls_db),
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    items, _ = await MitreService(session).list(user_id=user.id, page=1, page_size=500)
    tactics: dict[str, list[dict[str, Any]]] = defaultdict(list)
    summary = {"total": 0, "covered": 0, "partial": 0, "planned": 0, "gaps": 0}
    for item in items:
        mapped = _technique_dict(item)
        tactics[item.tactic].append(mapped)
        summary["total"] += 1
        if item.coverage_status == "gap":
            summary["gaps"] += 1
        else:
            summary[item.coverage_status] += 1
    return {"summary": summary, "tactics": dict(tactics)}


@router.get(
    "/techniques/{record_id}",
    response_model=MitreTechniqueItem,
    responses={404: {"model": ErrorResponse}, **_UNAUTHORIZED},
)
async def get_technique(
    record_id: UUID,
    session: AsyncSession = Depends(get_rls_db),
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    return _technique_dict(await MitreService(session).get(record_id, user_id=user.id))


@router.patch(
    "/techniques/{record_id}",
    response_model=MitreTechniqueItem,
    responses={404: {"model": ErrorResponse}, **_UNAUTHORIZED},
)
async def update_technique(
    record_id: UUID,
    body: MitreTechniqueUpdate,
    session: AsyncSession = Depends(get_rls_db),
    user: AuthenticatedUser = Depends(get_current_user),
    actor: str = Depends(get_current_actor),
) -> dict[str, Any]:
    record = await MitreService(session).update(
        record_id,
        user_id=user.id,
        actor=actor,
        values=body.model_dump(),
    )
    return _technique_dict(record)
