"""Threat intelligence IOC models."""
import uuid
from typing import List

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from backend.database.base import Base, JSONVariant, TimestampMixin, UuidPrimaryKeyMixin, UuidType

IOC_TYPES = ("ip", "domain", "url", "sha256")
IOC_SEVERITIES = ("low", "medium", "high", "critical")
IOC_CONFIDENCE = ("low", "medium", "high")


class ThreatIOC(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "threat_iocs"

    user_id: Mapped[uuid.UUID] = mapped_column(UuidType, nullable=False)
    type: Mapped[str] = mapped_column(sa.String(16), nullable=False)
    value: Mapped[str] = mapped_column(sa.String(512), nullable=False)
    severity: Mapped[str] = mapped_column(sa.String(16), nullable=False)
    confidence: Mapped[str] = mapped_column(sa.String(16), nullable=False)
    description: Mapped[str] = mapped_column(sa.Text, nullable=False, default="")
    source: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    first_seen: Mapped[sa.DateTime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
    last_seen: Mapped[sa.DateTime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
    watchlist: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False)
    tags: Mapped[List[str]] = mapped_column(JSONVariant, nullable=False, default=list)
    mitre_techniques: Mapped[List[str]] = mapped_column(JSONVariant, nullable=False, default=list)
    risk_timeline: Mapped[List[dict]] = mapped_column(JSONVariant, nullable=False, default=list)

    __table_args__ = (
        sa.Index("ix_threat_iocs_user_id", "user_id"),
        sa.Index("ix_threat_iocs_last_seen", sa.text("last_seen DESC")),
        sa.UniqueConstraint("user_id", "type", "value", name="uq_threat_iocs_owner_type_value"),
        sa.CheckConstraint("type IN ('ip', 'domain', 'url', 'sha256')", name="ck_threat_iocs_type"),
        sa.CheckConstraint(
            "severity IN ('low', 'medium', 'high', 'critical')",
            name="ck_threat_iocs_severity",
        ),
        sa.CheckConstraint(
            "confidence IN ('low', 'medium', 'high')",
            name="ck_threat_iocs_confidence",
        ),
    )
