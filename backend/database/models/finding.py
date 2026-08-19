"""Finding models (Task 2: vuln-lifecycle Scan -> Finding pipeline).

A ``Finding`` is a single structured vulnerability/issue row belonging to a
``Project``, produced either by a ``ScanRun`` (``scan_run_id`` set) or
created manually by security/admin (``scan_run_id`` left ``NULL``). Its
``status`` moves through the server-enforced state machine implemented in
``backend.services.finding_state_machine`` - never edit ``status`` directly
outside ``backend.services.finding.FindingService.transition``.

Every transition is recorded as an immutable ``FindingTransition`` row,
mirroring the timeline-of-events pattern in
``backend/database/models/incident.py``'s ``IncidentTimelineEvent`` (a new,
separate table - that file is not modified).

**Fingerprint (Task 2, simplified):** ``sha256(f"{project_id}:{rule_id}:
{category}:{target}")`` using the raw ``target`` string, no normalization.
Task 3 adds target normalization on top of this same formula - the column
and its uniqueness constraint already exist here so that change needs no
migration.
"""
import uuid
from datetime import datetime
from typing import Any, Optional

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from backend.database.base import (
    Base,
    CreatedAtMixin,
    JSONVariant,
    TimestampMixin,
    UuidPrimaryKeyMixin,
    UuidType,
)

FINDING_SEVERITIES = ("low", "medium", "high", "critical")
FINDING_STATUSES = (
    "open",
    "confirmed",
    "in_progress",
    "fixed",
    "verified",
    "closed",
    "false_positive",
    "accepted_risk",
    "reopened",
)


class Finding(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "findings"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UuidType,
        sa.ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Nullable: a manually-created finding has no originating scan.
    scan_run_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UuidType,
        sa.ForeignKey("scan_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    fingerprint: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    rule_id: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    category: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    title: Mapped[str] = mapped_column(sa.String(240), nullable=False)
    evidence: Mapped[str] = mapped_column(sa.Text, nullable=False, default="")
    impact: Mapped[str] = mapped_column(sa.Text, nullable=False, default="")
    remediation: Mapped[str] = mapped_column(sa.Text, nullable=False, default="")
    severity: Mapped[str] = mapped_column(sa.String(16), nullable=False)
    status: Mapped[str] = mapped_column(sa.String(24), nullable=False, default="open")
    target: Mapped[str] = mapped_column(sa.String(2048), nullable=False)
    cve_id: Mapped[Optional[str]] = mapped_column(sa.String(32), nullable=True)
    assignee_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(UuidType, nullable=True)
    # Task 3 computes this via the SLA service - always NULL until then.
    deadline: Mapped[Optional[datetime]] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    verification_notes: Mapped[str] = mapped_column(sa.Text, nullable=False, default="")
    # Required by the state machine for false_positive/accepted_risk.
    resolution_reason: Mapped[Optional[str]] = mapped_column(sa.Text, nullable=True)
    first_seen_scan_run_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UuidType,
        sa.ForeignKey("scan_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    last_seen_scan_run_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UuidType,
        sa.ForeignKey("scan_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    closed_at: Mapped[Optional[datetime]] = mapped_column(sa.DateTime(timezone=True), nullable=True)

    __table_args__ = (
        sa.UniqueConstraint("project_id", "fingerprint", name="uq_findings_project_fingerprint"),
        sa.Index("ix_findings_project_id_status", "project_id", "status"),
        sa.Index("ix_findings_assignee_user_id_status", "assignee_user_id", "status"),
        sa.CheckConstraint(
            "severity IN ('low', 'medium', 'high', 'critical')",
            name="ck_findings_severity",
        ),
        sa.CheckConstraint(
            "status IN ("
            "'open', 'confirmed', 'in_progress', 'fixed', 'verified', 'closed', "
            "'false_positive', 'accepted_risk', 'reopened'"
            ")",
            name="ck_findings_status",
        ),
    )


class FindingTransition(UuidPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "finding_transitions"

    finding_id: Mapped[uuid.UUID] = mapped_column(
        UuidType,
        sa.ForeignKey("findings.id", ondelete="CASCADE"),
        nullable=False,
    )
    from_status: Mapped[str] = mapped_column(sa.String(24), nullable=False)
    to_status: Mapped[str] = mapped_column(sa.String(24), nullable=False)
    actor_user_id: Mapped[uuid.UUID] = mapped_column(UuidType, nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(sa.Text, nullable=True)
    meta: Mapped[dict[str, Any]] = mapped_column(JSONVariant, nullable=False, default=dict)

    __table_args__ = (
        sa.Index("ix_finding_transitions_finding_id", "finding_id"),
    )
