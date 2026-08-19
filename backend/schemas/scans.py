"""Request/response models for scan runs."""
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from backend.schemas.common import Page, UtcDatetime

ScanRunStatus = Literal["queued", "running", "completed", "failed"]
ScanType = Literal["url_scan"]


class ScanRunCreate(BaseModel):
    target: str = Field(min_length=1, max_length=2048, examples=["https://example.com"])


class ScanRunItem(BaseModel):
    id: UUID
    project_id: UUID
    triggered_by_user_id: UUID
    scan_type: ScanType
    target: str
    status: ScanRunStatus
    started_at: UtcDatetime | None = None
    completed_at: UtcDatetime | None = None
    summary: dict[str, Any]
    previous_scan_run_id: UUID | None = None
    created_at: UtcDatetime
    updated_at: UtcDatetime


class ScanRunPage(Page[ScanRunItem]):
    pass
