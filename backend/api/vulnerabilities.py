"""Vulnerability management endpoints."""
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import PageParams, page_params
from backend.core.actor import get_current_actor
from backend.core.auth import AuthenticatedUser, get_current_user
from backend.database.models.vulnerability import VulnerabilityPatchTask, VulnerabilityRecord
from backend.database.session import get_rls_db
from backend.schemas.health import ErrorResponse
from backend.schemas.vulnerabilities import (
    PatchTaskCreate,
    PatchTaskItem,
    PatchTaskPage,
    PatchTaskStatusUpdate,
    VulnerabilityCreate,
    VulnerabilityItem,
    VulnerabilityPage,
    WatchlistUpdate,
)
from backend.services.vulnerabilities import VulnerabilityService

router = APIRouter(
    prefix="/api/vulnerabilities",
    tags=["vulnerabilities"],
    dependencies=[Depends(get_current_user)],
)
_UNAUTHORIZED = {401: {"model": ErrorResponse, "description": "Missing or invalid bearer token."}}


def _vuln_dict(record: VulnerabilityRecord) -> dict[str, Any]:
    return {
        "id": record.id,
        "asset_id": record.asset_id,
        "cve_id": record.cve_id,
        "title": record.title,
        "description": record.description,
        "cvss": record.cvss,
        "severity": record.severity,
        "published_date": record.published_date,
        "updated_date": record.updated_date,
        "references": record.references,
        "affected_products": record.affected_products,
        "remediation": record.remediation,
        "watchlist": record.watchlist,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }


def _task_dict(task: VulnerabilityPatchTask, vuln: VulnerabilityRecord) -> dict[str, Any]:
    return {
        "id": task.id,
        "vulnerability_id": task.vulnerability_id,
        "cve_id": vuln.cve_id,
        "title": vuln.title,
        "cvss": vuln.cvss,
        "asset_id": task.asset_id,
        "asset_name": task.asset_name,
        "status": task.status,
        "notes": task.notes,
        "created_at": task.created_at,
        "updated_at": task.updated_at,
    }


@router.post("", status_code=201, response_model=VulnerabilityItem, responses={**_UNAUTHORIZED})
async def create_vulnerability(
    body: VulnerabilityCreate,
    session: AsyncSession = Depends(get_rls_db),
    user: AuthenticatedUser = Depends(get_current_user),
    actor: str = Depends(get_current_actor),
) -> dict[str, Any]:
    record = await VulnerabilityService(session).create(
        user_id=user.id,
        actor=actor,
        cve_id=body.cve_id,
        title=body.title,
        description=body.description,
        cvss=body.cvss,
        severity=body.severity,
        published_date=body.published_date,
        updated_date=body.updated_date,
        references=body.references,
        affected_products=body.affected_products,
        remediation=body.remediation,
        watchlist=body.watchlist,
    )
    return _vuln_dict(record)


@router.get("", response_model=VulnerabilityPage, responses={**_UNAUTHORIZED})
async def list_vulnerabilities(
    pagination: PageParams = Depends(page_params),
    search: Optional[str] = Query(default=None, max_length=200),
    severity: Optional[str] = Query(default=None, pattern="^(low|medium|high|critical)$"),
    watchlist: Optional[bool] = Query(default=None),
    session: AsyncSession = Depends(get_rls_db),
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    items, total = await VulnerabilityService(session).list(
        user_id=user.id,
        page=pagination.page,
        page_size=pagination.page_size,
        search=search,
        severity=severity,
        watchlist=watchlist,
    )
    return {
        "items": [_vuln_dict(item) for item in items],
        "total": total,
        "page": pagination.page,
        "page_size": pagination.page_size,
    }


@router.get(
    "/items/{vulnerability_id}",
    response_model=VulnerabilityItem,
    responses={404: {"model": ErrorResponse}, **_UNAUTHORIZED},
)
async def get_vulnerability(
    vulnerability_id: UUID,
    session: AsyncSession = Depends(get_rls_db),
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    return _vuln_dict(await VulnerabilityService(session).get(vulnerability_id, user_id=user.id))


@router.patch(
    "/items/{vulnerability_id}/watchlist",
    response_model=VulnerabilityItem,
    responses={404: {"model": ErrorResponse}, **_UNAUTHORIZED},
)
async def set_watchlist(
    vulnerability_id: UUID,
    body: WatchlistUpdate,
    session: AsyncSession = Depends(get_rls_db),
    user: AuthenticatedUser = Depends(get_current_user),
    actor: str = Depends(get_current_actor),
) -> dict[str, Any]:
    record = await VulnerabilityService(session).set_watchlist(
        vulnerability_id,
        user_id=user.id,
        watchlist=body.watchlist,
        actor=actor,
    )
    return _vuln_dict(record)


@router.post(
    "/patch-tasks",
    status_code=201,
    response_model=PatchTaskItem,
    responses={**_UNAUTHORIZED},
)
async def create_patch_task(
    body: PatchTaskCreate,
    session: AsyncSession = Depends(get_rls_db),
    user: AuthenticatedUser = Depends(get_current_user),
    actor: str = Depends(get_current_actor),
) -> dict[str, Any]:
    task, vuln = await VulnerabilityService(session).create_patch_task(
        user_id=user.id,
        actor=actor,
        **body.model_dump(),
    )
    return _task_dict(task, vuln)


@router.get("/patch-tasks/list", response_model=PatchTaskPage, responses={**_UNAUTHORIZED})
async def list_patch_tasks(
    pagination: PageParams = Depends(page_params),
    session: AsyncSession = Depends(get_rls_db),
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    items, total = await VulnerabilityService(session).list_patch_tasks(
        user_id=user.id,
        page=pagination.page,
        page_size=pagination.page_size,
    )
    return {
        "items": [_task_dict(task, vuln) for task, vuln in items],
        "total": total,
        "page": pagination.page,
        "page_size": pagination.page_size,
    }


@router.patch("/patch-tasks/{task_id}", responses={404: {"model": ErrorResponse}, **_UNAUTHORIZED})
async def set_patch_task_status(
    task_id: UUID,
    body: PatchTaskStatusUpdate,
    session: AsyncSession = Depends(get_rls_db),
    user: AuthenticatedUser = Depends(get_current_user),
    actor: str = Depends(get_current_actor),
) -> dict[str, str]:
    await VulnerabilityService(session).set_patch_status(
        task_id,
        user_id=user.id,
        status=body.status,
        actor=actor,
    )
    return {"status": "updated"}
