"""Schemas for reports center."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from backend.schemas.common import Page, UtcDatetime

ReportCategory = Literal["executive", "technical", "compliance", "incident"]
ReportFormat = Literal["markdown", "pdf", "docx", "csv"]
ReportStatus = Literal["completed", "failed"]


class ReportTemplateItem(BaseModel):
    id: str
    title: str
    description: str
    category: ReportCategory
    sections: list[str]


class ReportCreate(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    category: ReportCategory
    format: ReportFormat = "markdown"
    sections: list[str] = Field(default_factory=list, max_length=20)
    scope: str = Field(default="", max_length=4000)

    @field_validator("sections")
    @classmethod
    def _bounded_sections(cls, value: list[str]) -> list[str]:
        return [item.strip()[:120] for item in value if item.strip()]


class ReportItem(BaseModel):
    id: UUID
    title: str
    category: ReportCategory
    format: ReportFormat
    status: ReportStatus
    sections: list[str]
    scope: str
    content: str
    error_message: str
    created_at: UtcDatetime
    updated_at: UtcDatetime


class ReportPage(Page[ReportItem]):
    pass
