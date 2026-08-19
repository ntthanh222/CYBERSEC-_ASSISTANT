"""SLA / deadline policy model (Task 3: vuln-lifecycle Fingerprinting +
Rescan Diff + SLA).

An ``SlaPolicy`` row maps a ``severity`` to how many hours a ``Finding`` of
that severity gets before its deadline, once confirmed
(``backend.services.finding.FindingService.transition`` sets
``Finding.deadline`` the moment a transition's ``to_status == "confirmed"``
- see ``backend.services.sla.compute_deadline``).

``project_id IS NULL`` rows are the global default (seeded by migration
``0027``: critical=24h, high=72h, medium=168h, and deliberately no row for
``low`` - ``compute_deadline`` returns ``None`` for a severity with no
applicable policy, meaning "no SLA deadline applies"). A non-NULL
``project_id`` row overrides the global default for that one project+severity
pair.

**Nullable-column uniqueness note:** ``UniqueConstraint(project_id, severity)``
alone does NOT prevent two global-default rows (``project_id IS NULL``) for
the same severity - both Postgres and SQLite treat every ``NULL`` as distinct
from every other ``NULL`` for uniqueness purposes, so two ``(NULL, "high")``
rows would both satisfy a plain unique constraint. There is no existing
nullable-FK-in-a-unique-constraint precedent elsewhere in this codebase to
follow (checked 0024's project/workspace-membership uniqueness - those FKs
are always non-null), so this model adds a second, partial unique index
covering only the ``project_id IS NULL`` rows (``uq_sla_policies_global_severity``),
enforced identically on Postgres and SQLite via ``postgresql_where``/
``sqlite_where``. The base ``UniqueConstraint`` still does its job for every
non-NULL ``project_id`` row.
"""
import uuid
from typing import Optional

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from backend.database.base import Base, TimestampMixin, UuidPrimaryKeyMixin, UuidType

#: Kept as a local literal (not imported from backend.database.models.finding)
#: to avoid a model-to-model import purely for a tuple of strings; both are
#: defined from the same plan-mandated severity set and must be kept in sync
#: if that set ever changes.
SLA_POLICY_SEVERITIES = ("low", "medium", "high", "critical")


class SlaPolicy(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "sla_policies"

    # Nullable: NULL = global default, applied to every project with no
    # override of its own for this severity.
    project_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UuidType,
        sa.ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=True,
    )
    severity: Mapped[str] = mapped_column(sa.String(16), nullable=False)
    hours_to_deadline: Mapped[int] = mapped_column(sa.Integer, nullable=False)

    __table_args__ = (
        sa.UniqueConstraint(
            "project_id", "severity", name="uq_sla_policies_project_severity"
        ),
        sa.Index(
            "uq_sla_policies_global_severity",
            "severity",
            unique=True,
            postgresql_where=sa.text("project_id IS NULL"),
            sqlite_where=sa.text("project_id IS NULL"),
        ),
        sa.CheckConstraint(
            "severity IN ('low', 'medium', 'high', 'critical')",
            name="ck_sla_policies_severity",
        ),
        sa.CheckConstraint("hours_to_deadline > 0", name="ck_sla_policies_hours_positive"),
    )
