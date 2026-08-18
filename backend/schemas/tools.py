"""Request/response models for the Security Toolkit (URL scanner, password checker)."""
from typing import Dict, List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from backend.schemas.common import UtcDatetime

ScanStatus = Literal["safe", "suspicious", "critical", "failed"]
FindingSeverity = Literal["low", "medium", "high", "critical"]
PasswordStrength = Literal["weak", "medium", "strong", "very_strong"]


class UrlScanRequest(BaseModel):
    url: str = Field(
        min_length=1,
        max_length=2048,
        description="The URL to scan. http and https only.",
        examples=["https://example.com/login"],
    )


class UrlScanFinding(BaseModel):
    code: str = Field(examples=["no_https"])
    severity: FindingSeverity = Field(examples=["medium"])
    message: str = Field(examples=["The URL uses plain HTTP..."])
    weight: int = Field(examples=[20])


class UrlReputationResult(BaseModel):
    """VirusTotal's verdict, kept entirely separate from the local
    heuristic findings above - a clean local scan and an absent/unavailable
    VirusTotal verdict are never the same thing as "confirmed safe"."""

    configured: bool = Field(examples=[True])
    status: Literal["completed", "pending", "not_configured", "unavailable"] = Field(
        examples=["completed"]
    )
    malicious: int = Field(default=0, examples=[0])
    suspicious: int = Field(default=0, examples=[0])
    harmless: int = Field(default=0, examples=[63])
    undetected: int = Field(default=0, examples=[29])
    permalink: Optional[str] = Field(default=None, examples=[None])
    error_category: Optional[
        Literal["NOT_CONFIGURED", "INVALID_KEY", "RATE_LIMITED", "UNAVAILABLE", "DEGRADED"]
    ] = Field(default=None, examples=[None])


class UrlScanResponse(BaseModel):
    id: UUID = Field(examples=["7c9e6679-7425-40de-944b-e07fc1f90ae7"])
    url: str = Field(examples=["https://example.com/login"])
    normalized_url: str = Field(examples=["https://example.com/login"])
    hostname: str = Field(examples=["example.com"])
    port: int = Field(examples=[443])
    scheme: Literal["http", "https"] = Field(examples=["https"])
    has_https: bool = Field(examples=[True])
    reachable: bool = Field(examples=[True])
    status: ScanStatus = Field(examples=["safe"])
    risk_score: int = Field(ge=0, le=100, examples=[5])
    severity: FindingSeverity = Field(examples=["low"])
    http_status: Optional[int] = Field(default=None, examples=[200])
    final_url: Optional[str] = Field(default=None, examples=["https://example.com/login"])
    redirect_chain: List[str] = Field(default_factory=list)
    redirect_count: int = Field(examples=[0])
    headers: Dict[str, str] = Field(default_factory=dict)
    body_truncated: bool = Field(examples=[False])
    failure_reason: Optional[str] = Field(default=None, examples=[None])
    findings: List[UrlScanFinding] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)
    reputation: UrlReputationResult
    duration_ms: float = Field(examples=[184.2])
    created_at: UtcDatetime = Field(examples=["2026-07-29T02:15:00+00:00"])


class PasswordCheckRequest(BaseModel):
    password: str = Field(
        min_length=1,
        max_length=256,
        description=(
            "Analysed in memory only. Never persisted, logged, or included in any "
            "response, metric label or error message."
        ),
    )

    model_config = {
        "json_schema_extra": {
            "examples": [{"password": "correct horse battery staple"}]
        }
    }


class PasswordCheckResponse(BaseModel):
    strength: PasswordStrength = Field(examples=["very_strong"])
    score: int = Field(ge=0, le=4, examples=[4])
    length: int = Field(examples=[29])
    entropy_bits: float = Field(examples=[95.4])
    crack_time: str = Field(examples=["effectively forever at current attack rates"])
    has_lowercase: bool = Field(examples=[True])
    has_uppercase: bool = Field(examples=[False])
    has_digits: bool = Field(examples=[False])
    has_special: bool = Field(examples=[False])
    character_classes: int = Field(examples=[1])
    longest_repeat_run: int = Field(examples=[1])
    longest_sequential_run: int = Field(examples=[1])
    has_repeated_block: bool = Field(examples=[False])
    is_common: bool = Field(examples=[False])
    warnings: List[str] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)


class PasswordGuidanceResponse(BaseModel):
    strength: PasswordStrength = Field(examples=["weak"])
    headline: str = Field(examples=["This password would not survive an offline attack."])
    feedback: str = Field(examples=["Short, common or highly patterned passwords..."])
    recommendations: List[str] = Field(default_factory=list)
