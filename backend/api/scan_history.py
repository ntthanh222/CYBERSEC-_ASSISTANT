"""Scan history endpoints.

**Requires a valid Supabase Auth Bearer token on every route** (Phase 2.5B).
Only the caller's own records are visible or mutable - see
``backend.services.scan_history`` and the RLS policy on
``security_scan_history`` in migration 0004.
"""
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import PageParams, page_params
from backend.core.actor import get_current_actor
from backend.core.auth import AuthenticatedUser, get_current_user
from backend.database.models.scan_history import SecurityScanRecord
from backend.database.session import get_rls_db
from backend.schemas.health import ErrorResponse
from backend.schemas.scan_history import (
    ScanHistoryDetail,
    ScanHistoryPage,
    ScanRecordStatus,
    ScanType,
    Severity,
)
from backend.services.scan_history import ScanHistoryService

router = APIRouter(
    prefix="/api/tools", tags=["tools"], dependencies=[Depends(get_current_user)]
)
_UNAUTHORIZED = {401: {"model": ErrorResponse, "description": "Missing or invalid bearer token."}}


def _record_dict(record: SecurityScanRecord) -> dict[str, Any]:
    return {
        "id": record.id,
        "scan_type": record.scan_type,
        "target": record.target,
        "status": record.status,
        "risk_score": record.risk_score,
        "severity": record.severity,
        "summary": record.summary,
        "details": record.details,
        "actor": record.actor,
        "created_at": record.created_at,
    }


@router.get(
    "/scan-history",
    summary="List scan history",
    description=(
        "The caller's own recorded URL scans and CVE lookups, newest first by "
        "default. Password checks never appear here: the password checker is "
        "stateless and writes no row."
    ),
    response_description="A page of scan history records.",
    response_model=ScanHistoryPage,
    responses={
        422: {"model": ErrorResponse, "description": "Invalid query parameters."},
        **_UNAUTHORIZED,
    },
)
async def list_scan_history(
    pagination: PageParams = Depends(page_params),
    scan_type: Optional[ScanType] = Query(default=None),
    status: Optional[ScanRecordStatus] = Query(default=None),
    severity: Optional[Severity] = Query(default=None),
    sort: str = Query(default="desc", pattern="^(asc|desc)$"),
    session: AsyncSession = Depends(get_rls_db),
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict:
    service = ScanHistoryService(session)
    items, total = await service.list(
        user_id=user.id,
        page=pagination.page,
        page_size=pagination.page_size,
        scan_type=scan_type,
        status=status,
        severity=severity,
        sort=sort,
    )
    return {
        "items": [_record_dict(item) for item in items],
        "total": total,
        "page": pagination.page,
        "page_size": pagination.page_size,
    }


@router.get(
    "/scan-history/{record_id}",
    summary="Get one scan history record",
    description="Includes the structured findings/details behind the summary. "
    "Only the owning caller can see it.",
    response_description="The scan history record.",
    response_model=ScanHistoryDetail,
    responses={404: {"model": ErrorResponse, "description": "Record not found."}, **_UNAUTHORIZED},
)
async def get_scan_history_record(
    record_id: UUID,
    session: AsyncSession = Depends(get_rls_db),
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict:
    service = ScanHistoryService(session)
    record = await service.get(record_id, user_id=user.id)
    return _record_dict(record)


@router.delete(
    "/scan-history/{record_id}",
    status_code=204,
    summary="Delete a scan history record",
    description="Emits an audit event. Only the owning caller can delete it.",
    response_description="Deleted; no content.",
    responses={404: {"model": ErrorResponse, "description": "Record not found."}, **_UNAUTHORIZED},
)
async def delete_scan_history_record(
    record_id: UUID,
    session: AsyncSession = Depends(get_rls_db),
    user: AuthenticatedUser = Depends(get_current_user),
    actor: str = Depends(get_current_actor),
) -> None:
    service = ScanHistoryService(session)
    await service.delete(record_id, user_id=user.id, actor=actor)
