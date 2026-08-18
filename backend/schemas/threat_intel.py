"""Request/response schemas for threat intelligence indicators."""
from typing import List, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from backend.schemas.common import Page, UtcDatetime

IOCType = Literal["ip", "domain", "url", "sha256"]
IOCSeverity = Literal["low", "medium", "high", "critical"]
IOCConfidence = Literal["low", "medium", "high"]


class RiskPoint(BaseModel):
    time: str = Field(min_length=1, max_length=40)
    score: int = Field(ge=0, le=100)


class ThreatIOCCreate(BaseModel):
    type: IOCType
    value: str = Field(min_length=1, max_length=512)
    severity: IOCSeverity
    confidence: IOCConfidence = "medium"
    description: str = Field(default="", max_length=2000)
    source: str = Field(min_length=1, max_length=200)
    first_seen: UtcDatetime
    last_seen: UtcDatetime
    watchlist: bool = False
    tags: List[str] = Field(default_factory=list, max_length=50)
    mitre_techniques: List[str] = Field(default_factory=list, max_length=50)
    risk_timeline: List[RiskPoint] = Field(default_factory=list, max_length=48)

    @field_validator("tags", "mitre_techniques")
    @classmethod
    def _bound_strings(cls, values: list[str]) -> list[str]:
        return [value.strip()[:120] for value in values if value.strip()]


class ThreatIOCWatchlistUpdate(BaseModel):
    watchlist: bool


class ThreatIOCItem(BaseModel):
    id: UUID
    type: IOCType
    value: str
    severity: IOCSeverity
    confidence: IOCConfidence
    description: str
    source: str
    first_seen: UtcDatetime
    last_seen: UtcDatetime
    watchlist: bool
    tags: List[str]
    mitre_techniques: List[str]
    risk_timeline: List[RiskPoint]
    created_at: UtcDatetime
    updated_at: UtcDatetime


class ThreatIOCPage(Page[ThreatIOCItem]):
    pass


class ThreatIntelSummary(BaseModel):
    total: int
    critical: int
    watchlist: int
    recent_48h: int
    items: List[ThreatIOCItem]
