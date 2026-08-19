"""Scan run model (Task 2: vuln-lifecycle Scan -> Finding pipeline).

A ``ScanRun`` records one invocation of a scanner (currently only
``url_scan``, wrapping ``backend.services.url_scanner.scan_url``) against a
``Project``. It is deliberately additive/parallel to the pre-existing
``SecurityScanRecord`` (``backend/database/models/scan_history.py``) - that
table is the global, ungoverned Scan History page from Phase 2 and is left
completely untouched; ``ScanRun`` is project-scoped and is what
``Finding`` rows attach to.

``previous_scan_run_id`` exists so a later phase (Task 3) can chain scans for
fingerprint-based diffing (FIXED/STILL_OPEN/NEW_REGRESSION classification).
This task's orchestrator only stores the value it is given - it never reads
it to compute anything.
"""
import uuid
from datetime import datetime
from typing import Any, Optional

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from backend.database.base import Base, JSONVariant, TimestampMixin, UuidPrimaryKeyMixin, UuidType

SCAN_RUN_STATUSES = ("queued", "running", "completed", "failed")
#: Kept narrow on purpose - the only real scan engine wired up so far is the
#: existing SSRF-safe URL scanner. Extend when a real second scanner lands.
SCAN_TYPES = ("url_scan",)


class ScanRun(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "scan_runs"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UuidType,
        sa.ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    triggered_by_user_id: Mapped[uuid.UUID] = mapped_column(UuidType, nullable=False)
    scan_type: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    target: Mapped[str] = mapped_column(sa.String(2048), nullable=False)
    status: Mapped[str] = mapped_column(sa.String(16), nullable=False, default="queued")
    started_at: Mapped[Optional[datetime]] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    # Severity counts of findings touched by this run (Task 2), plus
    # new/still_open placeholders that Task 3's diff algorithm will populate
    # for real - this task only ever writes severity counts here.
    summary: Mapped[dict[str, Any]] = mapped_column(JSONVariant, nullable=False, default=dict)
    previous_scan_run_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UuidType,
        sa.ForeignKey("scan_runs.id", ondelete="SET NULL"),
        nullable=True,
    )

    __table_args__ = (
        sa.Index("ix_scan_runs_project_id", "project_id"),
        sa.Index("ix_scan_runs_project_id_status", "project_id", "status"),
        sa.CheckConstraint(
            "scan_type IN ('url_scan')",
            name="ck_scan_runs_scan_type",
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'failed')",
            name="ck_scan_runs_status",
        ),
    )
