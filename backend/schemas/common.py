"""Shared schema building blocks for Phase 2 responses."""
from datetime import datetime
from typing import Annotated, Generic, List, TypeVar

from pydantic import BaseModel, Field, PlainSerializer

from backend.core.timeutils import to_iso_utc

#: Every timestamp the API emits is ISO-8601 UTC. Values read back from SQLite
#: (test suite) come back naive; ``to_iso_utc`` normalizes them so the wire
#: format is identical on every backend.
UtcDatetime = Annotated[datetime, PlainSerializer(to_iso_utc, return_type=str)]

ItemT = TypeVar("ItemT")

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


class Page(BaseModel, Generic[ItemT]):
    """Envelope for every paginated list endpoint."""

    items: List[ItemT] = Field(description="The records on this page.")
    total: int = Field(description="Total records matching the filters.", examples=[42])
    page: int = Field(description="1-based page number.", examples=[1])
    page_size: int = Field(description="Records per page.", examples=[20])
