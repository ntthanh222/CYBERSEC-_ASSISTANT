"""Schemas for the notification center."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from backend.schemas.common import Page, UtcDatetime

NotificationCategory = Literal["alert", "incident", "vulnerability", "system"]
NotificationSeverity = Literal["info", "warning", "critical"]


class NotificationCreate(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    body: str = Field(default="", max_length=4000)
    category: NotificationCategory
    severity: NotificationSeverity = "info"
    source_ref: str = Field(default="", max_length=200)


class NotificationItem(BaseModel):
    id: UUID
    title: str
    body: str
    category: NotificationCategory
    severity: NotificationSeverity
    is_read: bool
    source_ref: str
    created_at: UtcDatetime
    updated_at: UtcDatetime


class NotificationPage(Page[NotificationItem]):
    unread_count: int


class NotificationReadUpdate(BaseModel):
    is_read: bool
