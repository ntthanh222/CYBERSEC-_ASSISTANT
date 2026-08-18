"""Alert center endpoints."""
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import PageParams, page_params
from backend.core.actor import get_current_actor
from backend.core.auth import AuthenticatedUser, get_current_user
from backend.database.models.alert import AlertRecord
from backend.database.session import get_rls_db
from backend.schemas.alerts import AlertCreate, AlertItem, AlertPage, AlertStatusUpdate
from backend.schemas.health import ErrorResponse
from backend.services.alerts import AlertService

router = APIRouter(prefix="/api/alerts", tags=["alerts"], dependencies=[Depends(get_current_user)])
_UNAUTHORIZED = {401: {"model": ErrorResponse, "description": "Missing or invalid bearer token."}}


def _alert_dict(record: AlertRecord) -> dict[str, Any]:
    return {
        "id": record.id,
        "title": record.title,
        "description": record.description,
        "severity": record.severity,
        "source": record.source,
        "status": record.status,
        "asset_id": record.asset_id,
        "vulnerability_id": record.vulnerability_id,
        "asset_name": record.asset_name,
        "ioc_value": record.ioc_value,
        "evidence": record.evidence,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }


@router.post("", status_code=201, response_model=AlertItem, responses={**_UNAUTHORIZED})
async def create_alert(
    body: AlertCreate,
    session: AsyncSession = Depends(get_rls_db),
    user: AuthenticatedUser = Depends(get_current_user),
    actor: str = Depends(get_current_actor),
) -> dict[str, Any]:
    record = await AlertService(session).create(user_id=user.id, actor=actor, **body.model_dump())
    return _alert_dict(record)


@router.get("", response_model=AlertPage, responses={**_UNAUTHORIZED})
async def list_alerts(
    pagination: PageParams = Depends(page_params),
    search: Optional[str] = Query(default=None, max_length=200),
    severity: Optional[str] = Query(default=None, pattern="^(low|medium|high|critical)$"),
    status: Optional[str] = Query(
        default=None,
        pattern="^(new|acknowledged|investigating|resolved|false_positive)$",
    ),
    session: AsyncSession = Depends(get_rls_db),
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    items, total = await AlertService(session).list(
        user_id=user.id,
        page=pagination.page,
        page_size=pagination.page_size,
        search=search,
        severity=severity,
        status=status,
    )
    return {
        "items": [_alert_dict(item) for item in items],
        "total": total,
        "page": pagination.page,
        "page_size": pagination.page_size,
    }


@router.get(
    "/{alert_id}",
    response_model=AlertItem,
    responses={404: {"model": ErrorResponse}, **_UNAUTHORIZED},
)
async def get_alert(
    alert_id: UUID,
    session: AsyncSession = Depends(get_rls_db),
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    return _alert_dict(await AlertService(session).get(alert_id, user_id=user.id))


@router.patch(
    "/{alert_id}/status",
    response_model=AlertItem,
    responses={404: {"model": ErrorResponse}, **_UNAUTHORIZED},
)
async def set_alert_status(
    alert_id: UUID,
    body: AlertStatusUpdate,
    session: AsyncSession = Depends(get_rls_db),
    user: AuthenticatedUser = Depends(get_current_user),
    actor: str = Depends(get_current_actor),
) -> dict[str, Any]:
    record = await AlertService(session).set_status(
        alert_id,
        user_id=user.id,
        status=body.status,
        actor=actor,
    )
    return _alert_dict(record)
