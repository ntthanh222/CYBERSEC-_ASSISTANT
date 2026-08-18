"""Reports center model."""

import uuid
from typing import List

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from backend.database.base import Base, JSONVariant, TimestampMixin, UuidPrimaryKeyMixin, UuidType

REPORT_CATEGORIES = ("executive", "technical", "compliance", "incident")
REPORT_FORMATS = ("markdown", "pdf", "docx", "csv")
REPORT_STATUSES = ("completed", "failed")


class ReportRecord(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "report_records"

    user_id: Mapped[uuid.UUID] = mapped_column(UuidType, nullable=False)
    title: Mapped[str] = mapped_column(sa.String(240), nullable=False)
    category: Mapped[str] = mapped_column(sa.String(24), nullable=False)
    format: Mapped[str] = mapped_column(sa.String(16), nullable=False)
    status: Mapped[str] = mapped_column(sa.String(16), nullable=False)
    sections: Mapped[List[str]] = mapped_column(JSONVariant, nullable=False, default=list)
    scope: Mapped[str] = mapped_column(sa.Text, nullable=False, default="")
    content: Mapped[str] = mapped_column(sa.Text, nullable=False, default="")
    error_message: Mapped[str] = mapped_column(sa.String(400), nullable=False, default="")

    __table_args__ = (
        sa.Index("ix_report_records_user_id", "user_id"),
        sa.Index("ix_report_records_created_at", sa.text("created_at DESC")),
        sa.CheckConstraint(
            "category IN ('executive', 'technical', 'compliance', 'incident')",
            name="ck_report_records_category",
        ),
        sa.CheckConstraint(
            "format IN ('markdown', 'pdf', 'docx', 'csv')",
            name="ck_report_records_format",
        ),
        sa.CheckConstraint("status IN ('completed', 'failed')", name="ck_report_records_status"),
    )
