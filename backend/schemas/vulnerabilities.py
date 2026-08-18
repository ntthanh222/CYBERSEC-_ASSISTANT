"""Schemas for vulnerability management."""
from typing import List, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from backend.schemas.common import Page, UtcDatetime

Severity = Literal["low", "medium", "high", "critical"]
PatchStatus = Literal["not_started", "in_progress", "patched", "accepted_risk"]


class VulnerabilityCreate(BaseModel):
    asset_id: UUID | None = None
    cve_id: str = Field(min_length=4, max_length=32, pattern=r"^CVE-\d{4}-\d{4,}$")
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(min_length=1, max_length=5000)
    cvss: float = Field(ge=0, le=10)
    severity: Severity
    published_date: UtcDatetime
    updated_date: UtcDatetime
    references: List[str] = Field(default_factory=list, max_length=50)
    affected_products: List[str] = Field(default_factory=list, max_length=100)
    remediation: str = Field(default="", max_length=3000)
    watchlist: bool = False

    @field_validator("cve_id")
    @classmethod
    def _uppercase_cve(cls, value: str) -> str:
        return value.upper()


class WatchlistUpdate(BaseModel):
    watchlist: bool


class VulnerabilityItem(VulnerabilityCreate):
    id: UUID
    created_at: UtcDatetime
    updated_at: UtcDatetime


class VulnerabilityPage(Page[VulnerabilityItem]):
    pass


class PatchTaskCreate(BaseModel):
    vulnerability_id: UUID
    asset_id: UUID | None = None
    asset_name: str = Field(default="", max_length=200)
    status: PatchStatus = "not_started"
    notes: str = Field(default="", max_length=2000)


class PatchTaskStatusUpdate(BaseModel):
    status: PatchStatus


class PatchTaskItem(BaseModel):
    id: UUID
    vulnerability_id: UUID
    cve_id: str
    title: str
    cvss: float
    asset_id: UUID | None
    asset_name: str
    status: PatchStatus
    notes: str
    created_at: UtcDatetime
    updated_at: UtcDatetime


class PatchTaskPage(Page[PatchTaskItem]):
    pass
