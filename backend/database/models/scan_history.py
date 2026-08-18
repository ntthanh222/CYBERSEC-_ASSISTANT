"""Security scan history.

Only scans that have a meaningful, non-sensitive target are recorded: URL
scans and CVE lookups. **Password checks are never written here** - the
password checker is stateless by design, so there is no row, no target and no
derived fingerprint of the submitted secret anywhere in this table.
"""
import uuid
from typing import Any, Optional

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from backend.database.base import Base, CreatedAtMixin, JSONVariant, UuidPrimaryKeyMixin, UuidType

SCAN_TYPES = ("url_scan", "cve_lookup")
SCAN_STATUSES = ("completed", "failed")
SEVERITIES = ("low", "medium", "high", "critical")


class SecurityScanRecord(UuidPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "security_scan_history"

    scan_type: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    target: Mapped[str] = mapped_column(sa.String(2048), nullable=False)
    status: Mapped[str] = mapped_column(sa.String(16), nullable=False)
    risk_score: Mapped[Optional[int]] = mapped_column(sa.Integer, nullable=True)
    severity: Mapped[Optional[str]] = mapped_column(sa.String(16), nullable=True)
    summary: Mapped[str] = mapped_column(sa.String(500), nullable=False)
    # Structured findings/factors. docs/05_DATA_MODEL.md requires storing the
    # factors behind a risk score, not just the number.
    details: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONVariant, nullable=True)
    actor: Mapped[Optional[str]] = mapped_column(sa.String(128), nullable=True)
    # Ownership: the Supabase Auth user this scan belongs to. Always set from
    # the verified token, never from client input. See conversation.py.
    user_id: Mapped[uuid.UUID] = mapped_column(UuidType, nullable=False)

    __table_args__ = (
        sa.Index("ix_security_scan_history_user_id", "user_id"),
        sa.CheckConstraint(
            "scan_type IN ('url_scan', 'cve_lookup')",
            name="ck_security_scan_history_scan_type",
        ),
        sa.CheckConstraint(
            "status IN ('completed', 'failed')",
            name="ck_security_scan_history_status",
        ),
        sa.CheckConstraint(
            "risk_score IS NULL OR (risk_score >= 0 AND risk_score <= 100)",
            name="ck_security_scan_history_risk_score_range",
        ),
        sa.CheckConstraint(
            "severity IS NULL OR severity IN ('low', 'medium', 'high', 'critical')",
            name="ck_security_scan_history_severity",
        ),
        sa.Index("ix_security_scan_history_created_at", sa.text("created_at DESC")),
        sa.Index("ix_security_scan_history_scan_type", "scan_type"),
        sa.Index("ix_security_scan_history_status", "status"),
    )
