"""Security news persistence."""

import uuid
from typing import Any, Optional, Sequence

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database.models.security_news import SecurityNewsArticle


class SecurityNewsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, *, user_id: uuid.UUID, **values: Any) -> SecurityNewsArticle:
        article = SecurityNewsArticle(user_id=user_id, **values)
        self._session.add(article)
        await self._session.flush()
        return article

    async def get(self, article_id: uuid.UUID) -> Optional[SecurityNewsArticle]:
        return await self._session.scalar(
            sa.select(SecurityNewsArticle).where(SecurityNewsArticle.id == article_id)
        )

    async def get_by_url(self, url: str) -> Optional[SecurityNewsArticle]:
        return await self._session.scalar(
            sa.select(SecurityNewsArticle).where(SecurityNewsArticle.url == url)
        )

    async def list(
        self,
        *,
        page: int,
        page_size: int,
        search: Optional[str] = None,
        bookmarked: Optional[bool] = None,
        unread: Optional[bool] = None,
    ) -> tuple[Sequence[SecurityNewsArticle], int]:
        filters: list[Any] = []
        if search:
            pattern = f"%{search.lower()}%"
            filters.append(
                sa.or_(
                    sa.func.lower(SecurityNewsArticle.title).like(pattern),
                    sa.func.lower(SecurityNewsArticle.summary).like(pattern),
                    sa.func.lower(SecurityNewsArticle.source).like(pattern),
                )
            )
        if bookmarked is not None:
            filters.append(SecurityNewsArticle.bookmarked == bookmarked)
        if unread:
            filters.append(SecurityNewsArticle.read.is_(False))
        total = await self._session.scalar(
            sa.select(sa.func.count()).select_from(SecurityNewsArticle).where(*filters)
        )
        rows = await self._session.scalars(
            sa.select(SecurityNewsArticle)
            .where(*filters)
            .order_by(SecurityNewsArticle.published_at.desc(), SecurityNewsArticle.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(rows), int(total or 0)

    async def update_flags(
        self,
        article_id: uuid.UUID,
        *,
        values: dict[str, Any],
    ) -> Optional[SecurityNewsArticle]:
        article = await self.get(article_id)
        if article is None:
            return None
        for key, value in values.items():
            setattr(article, key, value)
        await self._session.flush()
        return article
