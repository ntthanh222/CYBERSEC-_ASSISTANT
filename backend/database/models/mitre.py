"""MITRE ATT&CK coverage model."""

import uuid
from typing import List

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from backend.database.base import Base, JSONVariant, TimestampMixin, UuidPrimaryKeyMixin, UuidType

MITRE_COVERAGE_STATUSES = ("planned", "partial", "covered", "gap")


class MitreTechniqueCoverage(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "mitre_technique_coverage"

    user_id: Mapped[uuid.UUID] = mapped_column(UuidType, nullable=False)
    incident_id: Mapped[uuid.UUID | None] = mapped_column(UuidType, nullable=True)
    technique_id: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    tactic: Mapped[str] = mapped_column(sa.String(80), nullable=False)
    name: Mapped[str] = mapped_column(sa.String(240), nullable=False)
    description: Mapped[str] = mapped_column(sa.Text, nullable=False, default="")
    detection: Mapped[str] = mapped_column(sa.Text, nullable=False, default="")
    mitigation: Mapped[str] = mapped_column(sa.Text, nullable=False, default="")
    coverage_status: Mapped[str] = mapped_column(sa.String(16), nullable=False)
    data_sources: Mapped[List[str]] = mapped_column(JSONVariant, nullable=False, default=list)

    __table_args__ = (
        sa.Index("ix_mitre_coverage_user_id", "user_id"),
        sa.Index("ix_mitre_coverage_tactic", "tactic"),
        sa.Index("ix_mitre_coverage_user_technique", "user_id", "technique_id"),
        sa.CheckConstraint(
            "coverage_status IN ('planned', 'partial', 'covered', 'gap')",
            name="ck_mitre_coverage_status",
        ),
    )
