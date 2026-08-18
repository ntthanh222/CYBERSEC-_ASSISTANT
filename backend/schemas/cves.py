"""Request/response models for CVE lookup."""
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

from backend.schemas.common import UtcDatetime

Severity = Literal["low", "medium", "high", "critical"]


class CveResponse(BaseModel):
    cve_id: str = Field(examples=["CVE-2021-44228"])
    description: str = Field(examples=["Apache Log4j2 JNDI features..."])
    published_at: Optional[UtcDatetime] = Field(
        default=None, examples=["2021-12-10T00:00:00+00:00"]
    )
    modified_at: Optional[UtcDatetime] = Field(
        default=None, examples=["2023-11-07T00:00:00+00:00"]
    )
    cvss_score: Optional[float] = Field(default=None, ge=0, le=10, examples=[10.0])
    severity: Optional[Severity] = Field(default=None, examples=["critical"])
    vector: Optional[str] = Field(
        default=None, examples=["CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:C/C:H/I:H/A:H"]
    )
    affected_products: List[str] = Field(default_factory=list)
    references: List[str] = Field(default_factory=list)
    source: str = Field(examples=["nvd"])
    cached: bool = Field(examples=[False])
    fetched_at: UtcDatetime = Field(examples=["2026-07-29T02:15:00+00:00"])


class CveSearchResponse(BaseModel):
    query: str = Field(examples=["log4j"])
    results: List[CveResponse] = Field(default_factory=list)
    count: int = Field(examples=[1])
