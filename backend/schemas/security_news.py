"""Schemas for security news center."""

from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl, field_validator

from backend.schemas.common import Page, UtcDatetime


class SecurityNewsCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    summary: str = Field(min_length=1, max_length=4000)
    ai_summary: str = Field(default="", max_length=4000)
    url: HttpUrl
    source: str = Field(min_length=1, max_length=200)
    published_at: UtcDatetime
    category: str = Field(default="", max_length=120)
    related_cves: list[str] = Field(default_factory=list, max_length=50)
    bookmarked: bool = False
    read: bool = False

    @field_validator("related_cves")
    @classmethod
    def _bounded_cves(cls, value: list[str]) -> list[str]:
        return [item.strip()[:32] for item in value if item.strip()]


class NewsBookmarkUpdate(BaseModel):
    bookmarked: bool


class NewsReadUpdate(BaseModel):
    read: bool


class SecurityNewsItem(BaseModel):
    id: UUID
    title: str
    summary: str
    ai_summary: str
    url: str
    source: str
    published_at: UtcDatetime
    category: str
    related_cves: list[str]
    bookmarked: bool
    read: bool
    created_at: UtcDatetime
    updated_at: UtcDatetime


class SecurityNewsPage(Page[SecurityNewsItem]):
    pass
