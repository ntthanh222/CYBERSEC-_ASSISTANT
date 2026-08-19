"""Request/response models for SLA policies (Task 3)."""
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from backend.schemas.common import UtcDatetime
from backend.schemas.findings import FindingSeverity


class SlaPolicyItem(BaseModel):
    id: UUID
    project_id: Optional[UUID] = None
    severity: FindingSeverity
    hours_to_deadline: int
    created_at: UtcDatetime
    updated_at: UtcDatetime


class SlaPolicyGlobalUpdate(BaseModel):
    hours_to_deadline: int = Field(gt=0, le=8760, description="Hours until deadline (max 1 year).")


class SlaPolicyProjectUpsert(BaseModel):
    #: ``None`` clears this project's override, reverting the severity back
    #: to the global default (or "no SLA" if there is no global default for
    #: it either, e.g. `low`).
    hours_to_deadline: Optional[int] = Field(
        default=None, gt=0, le=8760, description="Hours until deadline, or null to clear the override."
    )


class EffectiveSlaPolicyItem(BaseModel):
    """One severity's effective policy for a project: the project override
    if one exists, else the global default, else "no SLA applies"."""

    severity: FindingSeverity
    hours_to_deadline: Optional[int] = None
    source: Literal["project_override", "global_default", "none"]
