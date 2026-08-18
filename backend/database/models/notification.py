"""Notification center model."""

import uuid

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from backend.database.base import Base, TimestampMixin, UuidPrimaryKeyMixin, UuidType

NOTIFICATION_CATEGORIES = ("alert", "incident", "vulnerability", "system")
NOTIFICATION_SEVERITIES = ("info", "warning", "critical")


class NotificationRecord(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "notification_records"

    user_id: Mapped[uuid.UUID] = mapped_column(UuidType, nullable=False)
    title: Mapped[str] = mapped_column(sa.String(240), nullable=False)
    body: Mapped[str] = mapped_column(sa.Text, nullable=False, default="")
    category: Mapped[str] = mapped_column(sa.String(24), nullable=False)
    severity: Mapped[str] = mapped_column(sa.String(16), nullable=False, default="info")
    is_read: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False)
    source_ref: Mapped[str] = mapped_column(sa.String(200), nullable=False, default="")

    __table_args__ = (
        sa.Index("ix_notification_records_user_id", "user_id"),
        sa.Index("ix_notification_records_created_at", sa.text("created_at DESC")),
        sa.CheckConstraint(
            "category IN ('alert', 'incident', 'vulnerability', 'system')",
            name="ck_notification_records_category",
        ),
        sa.CheckConstraint(
            "severity IN ('info', 'warning', 'critical')",
            name="ck_notification_records_severity",
        ),
    )
