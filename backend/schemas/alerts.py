"""Schemas for alert center."""
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from backend.schemas.common import Page, UtcDatetime

AlertSeverity = Literal["low", "medium", "high", "critical"]
AlertStatus = Literal["new", "acknowledged", "investigating", "resolved", "false_positive"]


class AlertCreate(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    description: str = Field(min_length=1, max_length=4000)
    severity: AlertSeverity
    source: str = Field(min_length=1, max_length=160)
    status: AlertStatus = "new"
    asset_id: UUID | None = None
    vulnerability_id: UUID | None = None
    asset_name: str = Field(default="", max_length=200)
    ioc_value: str = Field(default="", max_length=512)
    evidence: str = Field(default="", max_length=4000)


class AlertStatusUpdate(BaseModel):
    status: AlertStatus


class AlertItem(AlertCreate):
    id: UUID
    created_at: UtcDatetime
    updated_at: UtcDatetime


class AlertPage(Page[AlertItem]):
    pass
