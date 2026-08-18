"""Security news service."""

import uuid
from typing import Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.audit import log_audit_event
from backend.core.exceptions import ConflictError, NotFoundError
from backend.repositories.security_news import SecurityNewsRepository


class SecurityNewsService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = SecurityNewsRepository(session)

    async def create(self, *, user_id: uuid.UUID, actor: Optional[str], **values):
        values["url"] = str(values["url"])
        try:
            article = await self._repo.create(user_id=user_id, **values)
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise ConflictError("URL bài viết này đã được lưu.") from exc
        log_audit_event(
            event_type="security_news",
            action="security_news_article_created",
            resource=f"security_news:{article.id}",
            result="success",
            actor=actor,
            metadata={"source": article.source},
        )
        return article

    async def list(self, *, page: int, page_size: int, **filters):
        return await self._repo.list(page=page, page_size=page_size, **filters)

    async def get(self, article_id: uuid.UUID):
        article = await self._repo.get(article_id)
        if article is None:
            raise NotFoundError("Không tìm thấy bài viết tin tức.")
        return article

    async def update_flags(
        self,
        article_id: uuid.UUID,
        *,
        actor: Optional[str],
        values: dict,
    ):
        article = await self._repo.update_flags(article_id, values=values)
        if article is None:
            raise NotFoundError("Không tìm thấy bài viết tin tức.")
        await self._session.commit()
        log_audit_event(
            event_type="security_news",
            action="security_news_article_updated",
            resource=f"security_news:{article.id}",
            result="success",
            actor=actor,
            metadata=values,
        )
        return article
