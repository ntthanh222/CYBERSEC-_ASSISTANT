"""Threat intelligence IOC endpoints."""
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import PageParams, page_params
from backend.core.actor import get_current_actor
from backend.core.auth import AuthenticatedUser, get_current_user
from backend.database.models.threat_intel import ThreatIOC
from backend.database.session import get_rls_db
from backend.schemas.health import ErrorResponse
from backend.schemas.threat_intel import (
    ThreatIOCCreate,
    ThreatIOCItem,
    ThreatIOCPage,
    ThreatIOCWatchlistUpdate,
    ThreatIntelSummary,
)
from backend.services.threat_intel import ThreatIOCService

router = APIRouter(
    prefix="/api/threat-intel", tags=["threat-intel"], dependencies=[Depends(get_current_user)]
)
_UNAUTHORIZED = {401: {"model": ErrorResponse, "description": "Missing or invalid bearer token."}}


def _ioc_dict(record: ThreatIOC) -> dict[str, Any]:
    return {
        "id": record.id,
        "type": record.type,
        "value": record.value,
        "severity": record.severity,
        "confidence": record.confidence,
        "description": record.description,
        "source": record.source,
        "first_seen": record.first_seen,
        "last_seen": record.last_seen,
        "watchlist": record.watchlist,
        "tags": record.tags,
        "mitre_techniques": record.mitre_techniques,
        "risk_timeline": record.risk_timeline,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }


@router.post(
    "/iocs",
    status_code=201,
    response_model=ThreatIOCItem,
    responses={409: {"model": ErrorResponse}, 422: {"model": ErrorResponse}, **_UNAUTHORIZED},
)
async def create_ioc(
    body: ThreatIOCCreate,
    session: AsyncSession = Depends(get_rls_db),
    user: AuthenticatedUser = Depends(get_current_user),
    actor: str = Depends(get_current_actor),
) -> dict[str, Any]:
    record = await ThreatIOCService(session).create(
        user_id=user.id,
        actor=actor,
        type=body.type,
        value=body.value,
        severity=body.severity,
        confidence=body.confidence,
        description=body.description,
        source=body.source,
        first_seen=body.first_seen,
        last_seen=body.last_seen,
        watchlist=body.watchlist,
        tags=body.tags,
        mitre_techniques=body.mitre_techniques,
        risk_timeline=[point.model_dump() for point in body.risk_timeline],
    )
    return _ioc_dict(record)


@router.get("/iocs", response_model=ThreatIOCPage, responses={**_UNAUTHORIZED})
async def list_iocs(
    pagination: PageParams = Depends(page_params),
    search: Optional[str] = Query(default=None, max_length=200),
    type: Optional[str] = Query(default=None, pattern="^(ip|domain|url|sha256)$"),
    severity: Optional[str] = Query(default=None, pattern="^(low|medium|high|critical)$"),
    watchlist: Optional[bool] = Query(default=None),
    session: AsyncSession = Depends(get_rls_db),
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    items, total = await ThreatIOCService(session).list(
        user_id=user.id,
        page=pagination.page,
        page_size=pagination.page_size,
        search=search,
        type=type,
        severity=severity,
        watchlist=watchlist,
    )
    return {
        "items": [_ioc_dict(item) for item in items],
        "total": total,
        "page": pagination.page,
        "page_size": pagination.page_size,
    }


@router.get("/summary", response_model=ThreatIntelSummary, responses={**_UNAUTHORIZED})
async def threat_intel_summary(
    session: AsyncSession = Depends(get_rls_db),
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    stats, items = await ThreatIOCService(session).summary(user_id=user.id)
    return {**stats, "items": [_ioc_dict(item) for item in items]}


@router.get(
    "/iocs/{ioc_id}",
    response_model=ThreatIOCItem,
    responses={404: {"model": ErrorResponse}, **_UNAUTHORIZED},
)
async def get_ioc(
    ioc_id: UUID,
    session: AsyncSession = Depends(get_rls_db),
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    return _ioc_dict(await ThreatIOCService(session).get(ioc_id, user_id=user.id))


@router.patch(
    "/iocs/{ioc_id}/watchlist",
    response_model=ThreatIOCItem,
    responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}, **_UNAUTHORIZED},
)
async def set_ioc_watchlist(
    ioc_id: UUID,
    body: ThreatIOCWatchlistUpdate,
    session: AsyncSession = Depends(get_rls_db),
    user: AuthenticatedUser = Depends(get_current_user),
    actor: str = Depends(get_current_actor),
) -> dict[str, Any]:
    record = await ThreatIOCService(session).set_watchlist(
        ioc_id, user_id=user.id, watchlist=body.watchlist, actor=actor
    )
    return _ioc_dict(record)
