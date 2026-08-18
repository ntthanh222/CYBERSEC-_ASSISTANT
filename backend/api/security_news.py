"""Security news endpoints."""

from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import PageParams, page_params
from backend.core.actor import get_current_actor
from backend.core.auth import AuthenticatedUser, get_current_user
from backend.core.authorization import AppUser, require_admin
from backend.database.models.security_news import SecurityNewsArticle
from backend.database.session import get_db, get_rls_db
from backend.schemas.health import ErrorResponse
from backend.schemas.security_news import (
    NewsBookmarkUpdate,
    NewsReadUpdate,
    SecurityNewsCreate,
    SecurityNewsItem,
    SecurityNewsPage,
)
from backend.services.security_news import SecurityNewsService

router = APIRouter(
    prefix="/api/news", tags=["security-news"], dependencies=[Depends(get_current_user)]
)
_UNAUTHORIZED = {401: {"model": ErrorResponse, "description": "Missing or invalid bearer token."}}


def _article_dict(article: SecurityNewsArticle) -> dict[str, Any]:
    return {
        "id": article.id,
        "title": article.title,
        "summary": article.summary,
        "ai_summary": article.ai_summary,
        "url": article.url,
        "source": article.source,
        "published_at": article.published_at,
        "category": article.category,
        "related_cves": article.related_cves,
        "bookmarked": article.bookmarked,
        "read": article.read,
        "created_at": article.created_at,
        "updated_at": article.updated_at,
    }


_FORBIDDEN = {403: {"model": ErrorResponse, "description": "Administrator privileges required."}}


@router.post(
    "",
    status_code=201,
    response_model=SecurityNewsItem,
    responses={**_UNAUTHORIZED, **_FORBIDDEN},
)
async def create_article(
    body: SecurityNewsCreate,
    # get_db, not get_rls_db - require_admin's own role lookup shares this
    # request's cached session (FastAPI dependency caching), and get_rls_db's
    # `SET LOCAL ROLE authenticated` would leak into that lookup, causing it
    # to run under a role without the grants it needs (500, not 403). Every
    # other admin-only route in this codebase (backend/api/admin.py) uses
    # get_db for exactly this reason - RLS is bypassed here by design, with
    # require_admin as the real gate, matching that established pattern.
    session: AsyncSession = Depends(get_db),
    admin: AppUser = Depends(require_admin),
    actor: str = Depends(get_current_actor),
) -> dict[str, Any]:
    article = await SecurityNewsService(session).create(
        user_id=admin.id,
        actor=actor,
        title=body.title,
        summary=body.summary,
        ai_summary=body.ai_summary,
        url=body.url,
        source=body.source,
        published_at=body.published_at,
        category=body.category,
        related_cves=body.related_cves,
        bookmarked=body.bookmarked,
        read=body.read,
    )
    return _article_dict(article)


@router.get("", response_model=SecurityNewsPage, responses={**_UNAUTHORIZED})
async def list_articles(
    pagination: PageParams = Depends(page_params),
    search: Optional[str] = Query(default=None, max_length=200),
    bookmarked: Optional[bool] = Query(default=None),
    unread: Optional[bool] = Query(default=None),
    session: AsyncSession = Depends(get_rls_db),
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    items, total = await SecurityNewsService(session).list(
        page=pagination.page,
        page_size=pagination.page_size,
        search=search,
        bookmarked=bookmarked,
        unread=unread,
    )
    return {
        "items": [_article_dict(item) for item in items],
        "total": total,
        "page": pagination.page,
        "page_size": pagination.page_size,
    }


@router.get(
    "/{article_id}",
    response_model=SecurityNewsItem,
    responses={404: {"model": ErrorResponse}, **_UNAUTHORIZED},
)
async def get_article(
    article_id: UUID,
    session: AsyncSession = Depends(get_rls_db),
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    return _article_dict(await SecurityNewsService(session).get(article_id))


@router.patch(
    "/{article_id}/bookmark",
    response_model=SecurityNewsItem,
    responses={404: {"model": ErrorResponse}, **_UNAUTHORIZED},
)
async def set_bookmark(
    article_id: UUID,
    body: NewsBookmarkUpdate,
    session: AsyncSession = Depends(get_rls_db),
    user: AuthenticatedUser = Depends(get_current_user),
    actor: str = Depends(get_current_actor),
) -> dict[str, Any]:
    article = await SecurityNewsService(session).update_flags(
        article_id,
        actor=actor,
        values={"bookmarked": body.bookmarked},
    )
    return _article_dict(article)


@router.patch(
    "/{article_id}/read",
    response_model=SecurityNewsItem,
    responses={404: {"model": ErrorResponse}, **_UNAUTHORIZED},
)
async def set_read(
    article_id: UUID,
    body: NewsReadUpdate,
    session: AsyncSession = Depends(get_rls_db),
    user: AuthenticatedUser = Depends(get_current_user),
    actor: str = Depends(get_current_actor),
) -> dict[str, Any]:
    article = await SecurityNewsService(session).update_flags(
        article_id,
        actor=actor,
        values={"read": body.read},
    )
    return _article_dict(article)
