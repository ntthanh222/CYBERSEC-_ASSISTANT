"""Incident response endpoints."""

from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import PageParams, page_params
from backend.core.actor import get_current_actor
from backend.core.auth import AuthenticatedUser, get_current_user
from backend.database.models.incident import IncidentRecord, IncidentTask, IncidentTimelineEvent
from backend.database.session import get_rls_db
from backend.schemas.health import ErrorResponse
from backend.schemas.incidents import (
    IncidentCreate,
    IncidentDetail,
    IncidentItem,
    IncidentNoteCreate,
    IncidentPage,
    IncidentStatusUpdate,
    IncidentTaskCreate,
    IncidentTaskItem,
    IncidentTaskStatusUpdate,
    IncidentTimelineItem,
)
from backend.services.incidents import IncidentService

router = APIRouter(
    prefix="/api/incidents", tags=["incidents"], dependencies=[Depends(get_current_user)]
)
_UNAUTHORIZED = {401: {"model": ErrorResponse, "description": "Missing or invalid bearer token."}}


def _incident_dict(record: IncidentRecord) -> dict[str, Any]:
    return {
        "id": record.id,
        "title": record.title,
        "description": record.description,
        "severity": record.severity,
        "status": record.status,
        "assignee": record.assignee,
        "source_alert_id": record.source_alert_id,
        "asset_name": record.asset_name,
        "cve_id": record.cve_id,
        "closed_at": record.closed_at,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }


def _task_dict(task: IncidentTask) -> dict[str, Any]:
    return {
        "id": task.id,
        "incident_id": task.incident_id,
        "title": task.title,
        "description": task.description,
        "status": task.status,
        "owner": task.owner,
        "created_at": task.created_at,
        "updated_at": task.updated_at,
    }


def _timeline_dict(event: IncidentTimelineEvent) -> dict[str, Any]:
    return {
        "id": event.id,
        "incident_id": event.incident_id,
        "event_type": event.event_type,
        "message": event.message,
        "actor": event.actor,
        "created_at": event.created_at,
    }


@router.post("", status_code=201, response_model=IncidentItem, responses={**_UNAUTHORIZED})
async def create_incident(
    body: IncidentCreate,
    session: AsyncSession = Depends(get_rls_db),
    user: AuthenticatedUser = Depends(get_current_user),
    actor: str = Depends(get_current_actor),
) -> dict[str, Any]:
    record = await IncidentService(session).create(
        user_id=user.id, actor=actor, **body.model_dump()
    )
    return _incident_dict(record)


@router.get("", response_model=IncidentPage, responses={**_UNAUTHORIZED})
async def list_incidents(
    pagination: PageParams = Depends(page_params),
    search: Optional[str] = Query(default=None, max_length=200),
    severity: Optional[str] = Query(default=None, pattern="^(low|medium|high|critical)$"),
    status: Optional[str] = Query(
        default=None,
        pattern="^(open|triaged|in_progress|contained|eradicated|recovered|closed)$",
    ),
    session: AsyncSession = Depends(get_rls_db),
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    items, total = await IncidentService(session).list(
        user_id=user.id,
        page=pagination.page,
        page_size=pagination.page_size,
        search=search,
        severity=severity,
        status=status,
    )
    return {
        "items": [_incident_dict(item) for item in items],
        "total": total,
        "page": pagination.page,
        "page_size": pagination.page_size,
    }


@router.get(
    "/{incident_id}",
    response_model=IncidentDetail,
    responses={404: {"model": ErrorResponse}, **_UNAUTHORIZED},
)
async def get_incident(
    incident_id: UUID,
    session: AsyncSession = Depends(get_rls_db),
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    incident, tasks, timeline = await IncidentService(session).get_detail(
        incident_id, user_id=user.id
    )
    return {
        **_incident_dict(incident),
        "tasks": [_task_dict(task) for task in tasks],
        "timeline": [_timeline_dict(event) for event in timeline],
    }


@router.patch(
    "/{incident_id}/status",
    response_model=IncidentItem,
    responses={404: {"model": ErrorResponse}, **_UNAUTHORIZED},
)
async def set_incident_status(
    incident_id: UUID,
    body: IncidentStatusUpdate,
    session: AsyncSession = Depends(get_rls_db),
    user: AuthenticatedUser = Depends(get_current_user),
    actor: str = Depends(get_current_actor),
) -> dict[str, Any]:
    record = await IncidentService(session).set_status(
        incident_id,
        user_id=user.id,
        status=body.status,
        actor=actor,
    )
    return _incident_dict(record)


@router.post(
    "/{incident_id}/tasks",
    status_code=201,
    response_model=IncidentTaskItem,
    responses={404: {"model": ErrorResponse}, **_UNAUTHORIZED},
)
async def create_incident_task(
    incident_id: UUID,
    body: IncidentTaskCreate,
    session: AsyncSession = Depends(get_rls_db),
    user: AuthenticatedUser = Depends(get_current_user),
    actor: str = Depends(get_current_actor),
) -> dict[str, Any]:
    task = await IncidentService(session).create_task(
        incident_id,
        user_id=user.id,
        actor=actor,
        **body.model_dump(),
    )
    return _task_dict(task)


@router.patch(
    "/tasks/{task_id}",
    response_model=IncidentTaskItem,
    responses={404: {"model": ErrorResponse}, **_UNAUTHORIZED},
)
async def set_incident_task_status(
    task_id: UUID,
    body: IncidentTaskStatusUpdate,
    session: AsyncSession = Depends(get_rls_db),
    user: AuthenticatedUser = Depends(get_current_user),
    actor: str = Depends(get_current_actor),
) -> dict[str, Any]:
    task = await IncidentService(session).set_task_status(
        task_id,
        user_id=user.id,
        status=body.status,
        actor=actor,
    )
    return _task_dict(task)


@router.post(
    "/{incident_id}/notes",
    status_code=201,
    response_model=IncidentTimelineItem,
    responses={404: {"model": ErrorResponse}, **_UNAUTHORIZED},
)
async def add_incident_note(
    incident_id: UUID,
    body: IncidentNoteCreate,
    session: AsyncSession = Depends(get_rls_db),
    user: AuthenticatedUser = Depends(get_current_user),
    actor: str = Depends(get_current_actor),
) -> dict[str, Any]:
    event = await IncidentService(session).add_note(
        incident_id,
        user_id=user.id,
        actor=actor,
        message=body.message,
    )
    return _timeline_dict(event)
