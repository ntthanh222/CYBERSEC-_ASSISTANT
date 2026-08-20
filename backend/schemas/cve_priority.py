"""Request/response models for project-scoped CVE risk prioritization (Task 6)."""
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from backend.schemas.common import UtcDatetime

CvePriorityLabel = Literal[
    "patch_now", "high", "medium", "low", "not_affected", "needs_review"
]


class CveAssessmentRequest(BaseModel):
    cve_id: str = Field(examples=["CVE-2021-44228"])
    affected_version: Optional[str] = Field(default=None, examples=["2.14.1"])


class CveAssessmentResponse(BaseModel):
    id: UUID
    project_id: UUID
    cve_id: str
    cvss_score: Optional[float] = None
    epss_score: Optional[float] = None
    is_kev: bool
    affected_version: Optional[str] = None
    fixed_version: Optional[str] = None
    technology: Optional[str] = None
    priority: CvePriorityLabel
    score: float
    rationale: dict[str, Any]
    finding_id: Optional[UUID] = None
    created_at: UtcDatetime
    updated_at: UtcDatetime
