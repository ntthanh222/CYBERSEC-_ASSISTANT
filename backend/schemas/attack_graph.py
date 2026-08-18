"""Schemas for attack graph."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from backend.schemas.common import UtcDatetime

NodeType = Literal["attacker", "asset", "database", "gateway", "target"]
NodeStatus = Literal["compromised", "vulnerable", "secure"]
EdgeStatus = Literal["active", "potential", "blocked"]
Severity = Literal["low", "medium", "high", "critical"]


class AttackNodeCreate(BaseModel):
    node_type: NodeType
    label: str = Field(min_length=1, max_length=240)
    ip_address: str = Field(default="", max_length=80)
    status: NodeStatus
    severity: Severity
    description: str = Field(default="", max_length=4000)
    cves: list[str] = Field(default_factory=list, max_length=50)
    position_x: int = Field(default=100, ge=0, le=1200)
    position_y: int = Field(default=100, ge=0, le=800)

    @field_validator("cves")
    @classmethod
    def _bounded_cves(cls, value: list[str]) -> list[str]:
        return [item.strip()[:32] for item in value if item.strip()]


class AttackEdgeCreate(BaseModel):
    source_node_id: UUID
    target_node_id: UUID
    label: str = Field(min_length=1, max_length=240)
    status: EdgeStatus = "potential"


class AttackNodeItem(AttackNodeCreate):
    id: UUID
    created_at: UtcDatetime
    updated_at: UtcDatetime


class AttackEdgeItem(AttackEdgeCreate):
    id: UUID
    created_at: UtcDatetime
    updated_at: UtcDatetime


class AttackGraph(BaseModel):
    nodes: list[AttackNodeItem]
    edges: list[AttackEdgeItem]
