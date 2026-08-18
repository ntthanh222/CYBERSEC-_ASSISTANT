"""Shared route dependencies."""
from dataclasses import dataclass

from fastapi import Query

from backend.schemas.common import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE


@dataclass
class PageParams:
    """1-based pagination, bounded so a client cannot request an unbounded page."""

    page: int
    page_size: int


def page_params(
    page: int = Query(default=1, ge=1, description="1-based page number."),
    page_size: int = Query(
        default=DEFAULT_PAGE_SIZE,
        ge=1,
        le=MAX_PAGE_SIZE,
        description=f"Records per page (max {MAX_PAGE_SIZE}).",
    ),
) -> PageParams:
    return PageParams(page=page, page_size=page_size)
