"""Schemas for MITRE ATT&CK coverage."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from backend.schemas.common import Page, UtcDatetime

CoverageStatus = Literal["planned", "partial", "covered", "gap"]


class MitreTechniqueCreate(BaseModel):
    incident_id: UUID | None = None
    technique_id: str = Field(min_length=2, max_length=32, pattern=r"^T[0-9]{4}(?:\.[0-9]{3})?$")
    tactic: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=240)
    description: str = Field(default="", max_length=4000)
    detection: str = Field(default="", max_length=4000)
    mitigation: str = Field(default="", max_length=4000)
    coverage_status: CoverageStatus = "planned"
    data_sources: list[str] = Field(default_factory=list, max_length=50)

    @field_validator("data_sources")
    @classmethod
    def _bounded_sources(cls, value: list[str]) -> list[str]:
        return [item.strip()[:160] for item in value if item.strip()]


class MitreTechniqueUpdate(BaseModel):
    incident_id: UUID | None = None
    detection: str = Field(default="", max_length=4000)
    mitigation: str = Field(default="", max_length=4000)
    coverage_status: CoverageStatus
    data_sources: list[str] = Field(default_factory=list, max_length=50)


class MitreTechniqueItem(MitreTechniqueCreate):
    id: UUID
    created_at: UtcDatetime
    updated_at: UtcDatetime
    created_at: UtcDatetime
    updated_at: UtcDatetime


class MitreCoverageSummary(BaseModel):
    total: int
    covered: int
    partial: int
    planned: int
    gaps: int


class MitreMatrix(BaseModel):
    summary: MitreCoverageSummary
    tactics: dict[str, list[MitreTechniqueItem]]


class MitreTechniquePage(Page[MitreTechniqueItem]):
    pass
