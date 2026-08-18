"""Response models for the live dashboard summary endpoint."""
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class DashboardCounts(BaseModel):
    documents: int = Field(examples=[3])
    conversations: int = Field(examples=[2])
    messages: int = Field(examples=[14])
    scans: int = Field(examples=[7])


ActivityType = Literal["conversation", "document", "scan"]


class DashboardActivityItem(BaseModel):
    type: ActivityType
    id: str
    title: str
    detail: Optional[str] = None
    created_at: datetime
    href: str


class DashboardSummaryResponse(BaseModel):
    counts: DashboardCounts
    recent_activity: list[DashboardActivityItem]
