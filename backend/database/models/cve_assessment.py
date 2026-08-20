"""CveAssessment model (Task 6: CVE Risk Prioritization).

A ``CveAssessment`` is the persisted result of running
``backend.services.cve_priority.assess`` for one ``(project_id, cve_id)``
pair - the CVSS/EPSS/KEV inputs gathered at assessment time, the resulting
``priority`` label + numeric ``score``, and the full ``rationale`` dict
(so the frontend and a later AI-copilot phase can render the "why" without
recomputing it).

One row per ``(project_id, cve_id)`` (see the unique constraint below) -
re-assessing the same CVE for the same project **updates** the existing row
rather than creating a new one, since EPSS/KEV/CVSS data changes over time
and only the latest assessment is meaningful (``backend.services.
project_cve.ProjectCveService.assess_cve`` implements the upsert).
"""
import uuid
from typing import Any, Optional

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from backend.database.base import Base, JSONVariant, TimestampMixin, UuidPrimaryKeyMixin, UuidType
from backend.services.cve_priority import CVE_PRIORITY_LABELS


class CveAssessment(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "cve_assessments"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UuidType,
        sa.ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    cve_id: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    cvss_score: Mapped[Optional[float]] = mapped_column(sa.Float, nullable=True)
    epss_score: Mapped[Optional[float]] = mapped_column(sa.Float, nullable=True)
    is_kev: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False)
    affected_version: Mapped[Optional[str]] = mapped_column(sa.String(100), nullable=True)
    fixed_version: Mapped[Optional[str]] = mapped_column(sa.String(100), nullable=True)
    technology: Mapped[Optional[str]] = mapped_column(sa.String(200), nullable=True)
    priority: Mapped[str] = mapped_column(sa.String(16), nullable=False)
    score: Mapped[float] = mapped_column(sa.Float, nullable=False)
    rationale: Mapped[dict[str, Any]] = mapped_column(JSONVariant, nullable=False, default=dict)
    # Nullable: only set when the priority engine's output was high enough
    # to auto-create/link a Finding (see ProjectCveService.assess_cve step 8).
    finding_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UuidType,
        sa.ForeignKey("findings.id", ondelete="SET NULL"),
        nullable=True,
    )

    __table_args__ = (
        sa.UniqueConstraint("project_id", "cve_id", name="uq_cve_assessments_project_cve"),
        sa.Index("ix_cve_assessments_project_id", "project_id"),
        sa.CheckConstraint(
            "priority IN ("
            + ", ".join(f"'{label}'" for label in CVE_PRIORITY_LABELS)
            + ")",
            name="ck_cve_assessments_priority",
        ),
    )
