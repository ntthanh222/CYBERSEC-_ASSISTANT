"""Schemas for incident response workspaces."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from backend.schemas.common import Page, UtcDatetime

IncidentSeverity = Literal["low", "medium", "high", "critical"]
IncidentStatus = Literal[
    "open", "triaged", "in_progress", "contained", "eradicated", "recovered", "closed"
]
IncidentTaskStatus = Literal["pending", "in_progress", "completed", "blocked"]


class IncidentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    description: str = Field(min_length=1, max_length=4000)
    severity: IncidentSeverity
    status: IncidentStatus = "open"
    assignee: str = Field(default="", max_length=160)
    source_alert_id: UUID | None = None
    asset_name: str = Field(default="", max_length=200)
    cve_id: str = Field(default="", max_length=32)


class IncidentStatusUpdate(BaseModel):
    status: IncidentStatus


class IncidentTaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    description: str = Field(default="", max_length=4000)
    status: IncidentTaskStatus = "pending"
    owner: str = Field(default="", max_length=160)


class IncidentTaskStatusUpdate(BaseModel):
    status: IncidentTaskStatus


class IncidentNoteCreate(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


class IncidentItem(IncidentCreate):
    id: UUID
    closed_at: UtcDatetime | None = None
    created_at: UtcDatetime
    updated_at: UtcDatetime


class IncidentTaskItem(IncidentTaskCreate):
    id: UUID
    incident_id: UUID
    created_at: UtcDatetime
    updated_at: UtcDatetime


class IncidentTimelineItem(BaseModel):
    id: UUID
    incident_id: UUID
    event_type: str
    message: str
    actor: str
    created_at: UtcDatetime


class IncidentDetail(IncidentItem):
    tasks: list[IncidentTaskItem]
    timeline: list[IncidentTimelineItem]


class IncidentPage(Page[IncidentItem]):
    pass
