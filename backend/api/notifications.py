"""Notification center endpoints."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import PageParams, page_params
from backend.core.actor import get_current_actor
from backend.core.auth import AuthenticatedUser, get_current_user
from backend.database.models.notification import NotificationRecord
from backend.database.session import get_rls_db
from backend.schemas.health import ErrorResponse
from backend.schemas.notifications import (
    NotificationCreate,
    NotificationItem,
    NotificationPage,
    NotificationReadUpdate,
)
from backend.services.notifications import NotificationService

router = APIRouter(
    prefix="/api/notifications", tags=["notifications"], dependencies=[Depends(get_current_user)]
)
_UNAUTHORIZED = {401: {"model": ErrorResponse, "description": "Missing or invalid bearer token."}}


def _notification_dict(record: NotificationRecord) -> dict[str, Any]:
    return {
        "id": record.id,
        "title": record.title,
        "body": record.body,
        "category": record.category,
        "severity": record.severity,
        "is_read": record.is_read,
        "source_ref": record.source_ref,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }


@router.post("", status_code=201, response_model=NotificationItem, responses={**_UNAUTHORIZED})
async def create_notification(
    body: NotificationCreate,
    session: AsyncSession = Depends(get_rls_db),
    user: AuthenticatedUser = Depends(get_current_user),
    actor: str = Depends(get_current_actor),
) -> dict[str, Any]:
    record = await NotificationService(session).create(
        user_id=user.id, actor=actor, **body.model_dump()
    )
    return _notification_dict(record)


@router.get("", response_model=NotificationPage, responses={**_UNAUTHORIZED})
async def list_notifications(
    pagination: PageParams = Depends(page_params),
    unread_only: bool = Query(default=False),
    session: AsyncSession = Depends(get_rls_db),
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    items, total, unread_count = await NotificationService(session).list(
        user_id=user.id,
        page=pagination.page,
        page_size=pagination.page_size,
        unread_only=unread_only,
    )
    return {
        "items": [_notification_dict(item) for item in items],
        "total": total,
        "page": pagination.page,
        "page_size": pagination.page_size,
        "unread_count": unread_count,
    }


@router.get(
    "/{notification_id}",
    response_model=NotificationItem,
    responses={404: {"model": ErrorResponse}, **_UNAUTHORIZED},
)
async def get_notification(
    notification_id: UUID,
    session: AsyncSession = Depends(get_rls_db),
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    return _notification_dict(
        await NotificationService(session).get(notification_id, user_id=user.id)
    )


@router.patch(
    "/{notification_id}/read",
    response_model=NotificationItem,
    responses={404: {"model": ErrorResponse}, **_UNAUTHORIZED},
)
async def set_notification_read(
    notification_id: UUID,
    body: NotificationReadUpdate,
    session: AsyncSession = Depends(get_rls_db),
    user: AuthenticatedUser = Depends(get_current_user),
    actor: str = Depends(get_current_actor),
) -> dict[str, Any]:
    record = await NotificationService(session).set_read(
        notification_id, user_id=user.id, is_read=body.is_read, actor=actor
    )
    return _notification_dict(record)
