"""Request/response models for scan history."""
from typing import Any, Dict, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from backend.schemas.common import Page, UtcDatetime

ScanType = Literal["url_scan", "cve_lookup"]
ScanRecordStatus = Literal["completed", "failed"]
Severity = Literal["low", "medium", "high", "critical"]


class ScanHistoryItem(BaseModel):
    id: UUID = Field(examples=["7c9e6679-7425-40de-944b-e07fc1f90ae7"])
    scan_type: ScanType = Field(examples=["url_scan"])
    target: str = Field(examples=["https://example.com/login"])
    status: ScanRecordStatus = Field(examples=["completed"])
    risk_score: Optional[int] = Field(default=None, ge=0, le=100, examples=[5])
    severity: Optional[Severity] = Field(default=None, examples=["low"])
    summary: str = Field(examples=["safe (risk 5)"])
    actor: Optional[str] = Field(default=None, examples=["anonymous"])
    created_at: UtcDatetime = Field(examples=["2026-07-29T02:15:00+00:00"])


class ScanHistoryDetail(ScanHistoryItem):
    details: Optional[Dict[str, Any]] = Field(
        default=None, description="Structured findings/factors behind the summary."
    )


class ScanHistoryPage(Page[ScanHistoryItem]):
    pass
