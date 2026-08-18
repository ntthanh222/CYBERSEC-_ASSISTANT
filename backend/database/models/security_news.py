"""Security news article model."""

import uuid
from typing import List

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from backend.database.base import Base, JSONVariant, TimestampMixin, UuidPrimaryKeyMixin, UuidType


class SecurityNewsArticle(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "security_news_articles"

    user_id: Mapped[uuid.UUID] = mapped_column(UuidType, nullable=False)
    title: Mapped[str] = mapped_column(sa.String(300), nullable=False)
    summary: Mapped[str] = mapped_column(sa.Text, nullable=False)
    ai_summary: Mapped[str] = mapped_column(sa.Text, nullable=False, default="")
    url: Mapped[str] = mapped_column(sa.String(1000), nullable=False)
    source: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    published_at: Mapped[sa.DateTime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
    category: Mapped[str] = mapped_column(sa.String(120), nullable=False, default="")
    related_cves: Mapped[List[str]] = mapped_column(JSONVariant, nullable=False, default=list)
    bookmarked: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False)
    read: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False)

    __table_args__ = (
        sa.Index("ix_security_news_user_id", "user_id"),
        sa.Index("ix_security_news_published_at", sa.text("published_at DESC")),
        # Shared feed - dedup is global by URL, not per-creator. See migration 0022.
        sa.UniqueConstraint("url", name="uq_security_news_url"),
    )
