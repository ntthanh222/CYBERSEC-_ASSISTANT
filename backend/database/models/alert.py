"""Alert center model."""
import uuid

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from backend.database.base import Base, TimestampMixin, UuidPrimaryKeyMixin, UuidType

ALERT_SEVERITIES = ("low", "medium", "high", "critical")
ALERT_STATUSES = ("new", "acknowledged", "investigating", "resolved", "false_positive")


class AlertRecord(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "alerts"

    user_id: Mapped[uuid.UUID] = mapped_column(UuidType, nullable=False)
    title: Mapped[str] = mapped_column(sa.String(240), nullable=False)
    description: Mapped[str] = mapped_column(sa.Text, nullable=False)
    severity: Mapped[str] = mapped_column(sa.String(16), nullable=False)
    source: Mapped[str] = mapped_column(sa.String(160), nullable=False)
    status: Mapped[str] = mapped_column(sa.String(24), nullable=False)
    asset_id: Mapped[uuid.UUID | None] = mapped_column(UuidType, nullable=True)
    vulnerability_id: Mapped[uuid.UUID | None] = mapped_column(UuidType, nullable=True)
    asset_name: Mapped[str] = mapped_column(sa.String(200), nullable=False, default="")
    ioc_value: Mapped[str] = mapped_column(sa.String(512), nullable=False, default="")
    evidence: Mapped[str] = mapped_column(sa.Text, nullable=False, default="")

    __table_args__ = (
        sa.Index("ix_alerts_user_id", "user_id"),
        sa.Index("ix_alerts_created_at", sa.text("created_at DESC")),
        sa.CheckConstraint(
            "severity IN ('low', 'medium', 'high', 'critical')",
            name="ck_alerts_severity",
        ),
        sa.CheckConstraint(
            "status IN ('new', 'acknowledged', 'investigating', 'resolved', 'false_positive')",
            name="ck_alerts_status",
        ),
    )
