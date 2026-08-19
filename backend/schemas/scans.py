"""Request/response models for scan runs."""
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from backend.schemas.common import Page, UtcDatetime

ScanRunStatus = Literal["queued", "running", "completed", "failed"]
ScanType = Literal["url_scan"]


class ScanRunCreate(BaseModel):
    target: str = Field(min_length=1, max_length=2048, examples=["https://example.com"])
    #: Optional override of the auto-detected "previous scan" used for
    #: rescan diffing (Task 3). Left unset, the orchestrator auto-chains to
    #: the most recent completed scan of the same project+target - this
    #: field exists only for a caller that needs to diff against a
    #: specific, non-default prior run.
    previous_scan_run_id: UUID | None = None


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
