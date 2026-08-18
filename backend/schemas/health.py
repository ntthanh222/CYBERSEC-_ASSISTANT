"""Response models for the health/system-health endpoints (OpenAPI docs only)."""
from typing import Literal, Optional

from pydantic import BaseModel, Field

Status = Literal["healthy", "degraded", "unavailable", "unknown"]


class LivenessResponse(BaseModel):
    status: Literal["healthy"] = Field(examples=["healthy"])
    service: Literal["backend"] = Field(examples=["backend"])


class DependencyCheck(BaseModel):
    status: Status = Field(examples=["healthy"])
    latency_ms: Optional[float] = Field(default=None, examples=[1.23])


EmbeddingStatus = Literal["not_started", "warming", "ready", "failed"]


class EmbeddingReadiness(BaseModel):
    status: EmbeddingStatus = Field(examples=["ready"])
    elapsed_seconds: Optional[float] = Field(default=None, examples=[24.3])
    error: Optional[str] = Field(default=None, examples=[None])


class SystemHealthChecks(BaseModel):
    backend: DependencyCheck
    database: DependencyCheck
    redis: DependencyCheck
    migration: DependencyCheck
    pgvector: DependencyCheck
    local_auth_secret: DependencyCheck


class SystemHealthResponse(BaseModel):
    status: Status = Field(examples=["healthy"])
    timestamp: str = Field(examples=["2026-07-29T12:00:00+00:00"])
    request_id: Optional[str] = Field(default=None, examples=["a1b2c3d4-..."])
    checks: SystemHealthChecks
    embedding: EmbeddingReadiness


class ErrorResponse(BaseModel):
    error: str = Field(examples=["internal_server_error"])
    message: str = Field(examples=["An unexpected error occurred. Please try again later."])
    request_id: str = Field(examples=["a1b2c3d4-..."])
