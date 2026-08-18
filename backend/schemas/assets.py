"""Request/response models for the asset inventory."""
from typing import List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from backend.schemas.common import Page, UtcDatetime

AssetType = Literal["server", "workstation", "cloud_resource", "database", "network_device"]
BusinessCriticality = Literal["low", "medium", "high", "critical"]
PatchStatus = Literal[
    "unknown", "not_started", "in_progress", "patched", "accepted_risk", "not_applicable"
]
ExploitEvidence = Literal[
    "none", "unconfirmed", "public_poc", "active_exploitation", "internal_confirmation"
]


class AssetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200, examples=["Core Finance DB Server"])
    type: AssetType = Field(examples=["database"])
    hostname: str = Field(min_length=1, max_length=255, examples=["fin-db-prod.internal"])
    ip_address: str = Field(min_length=1, max_length=64, examples=["10.100.20.14"])
    operating_system: str = Field(min_length=1, max_length=200, examples=["RHEL 8.6"])
    owner: str = Field(min_length=1, max_length=200, examples=["Finance Dept"])
    department: str = Field(min_length=1, max_length=200, examples=["Finance"])
    business_criticality: BusinessCriticality = Field(examples=["critical"])
    internet_exposed: bool = Field(default=False)
    description: str = Field(default="", max_length=2000)
    linked_cves: List[str] = Field(default_factory=list, max_length=100)
    patch_status: Optional[PatchStatus] = Field(default=None)
    exploit_evidence: Optional[ExploitEvidence] = Field(default=None)


class AssetItem(BaseModel):
    id: UUID = Field(examples=["7c9e6679-7425-40de-944b-e07fc1f90ae7"])
    name: str
    type: AssetType
    hostname: str
    ip_address: str
    operating_system: str
    owner: str
    department: str
    business_criticality: BusinessCriticality
    internet_exposed: bool
    description: str
    linked_cves: List[str]
    patch_status: Optional[PatchStatus] = None
    exploit_evidence: Optional[ExploitEvidence] = None
    created_at: UtcDatetime
    updated_at: UtcDatetime


class AssetPage(Page[AssetItem]):
    pass
