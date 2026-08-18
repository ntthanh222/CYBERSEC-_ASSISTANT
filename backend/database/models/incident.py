"""Incident response models."""

import uuid

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from backend.database.base import (
    Base,
    CreatedAtMixin,
    TimestampMixin,
    UuidPrimaryKeyMixin,
    UuidType,
)

INCIDENT_SEVERITIES = ("low", "medium", "high", "critical")
INCIDENT_STATUSES = (
    "open",
    "triaged",
    "in_progress",
    "contained",
    "eradicated",
    "recovered",
    "closed",
)
INCIDENT_TASK_STATUSES = ("pending", "in_progress", "completed", "blocked")


class IncidentRecord(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "incidents"

    user_id: Mapped[uuid.UUID] = mapped_column(UuidType, nullable=False)
    title: Mapped[str] = mapped_column(sa.String(240), nullable=False)
    description: Mapped[str] = mapped_column(sa.Text, nullable=False)
    severity: Mapped[str] = mapped_column(sa.String(16), nullable=False)
    status: Mapped[str] = mapped_column(sa.String(24), nullable=False)
    assignee: Mapped[str] = mapped_column(sa.String(160), nullable=False, default="")
    source_alert_id: Mapped[uuid.UUID | None] = mapped_column(UuidType, nullable=True)
    asset_name: Mapped[str] = mapped_column(sa.String(200), nullable=False, default="")
    cve_id: Mapped[str] = mapped_column(sa.String(32), nullable=False, default="")
    closed_at: Mapped[sa.DateTime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)

    __table_args__ = (
        sa.Index("ix_incidents_user_id", "user_id"),
        sa.Index("ix_incidents_created_at", sa.text("created_at DESC")),
        sa.CheckConstraint(
            "severity IN ('low', 'medium', 'high', 'critical')",
            name="ck_incidents_severity",
        ),
        sa.CheckConstraint(
            "status IN ("
            "'open', 'triaged', 'in_progress', 'contained', 'eradicated', 'recovered', 'closed'"
            ")",
            name="ck_incidents_status",
        ),
    )


class IncidentTask(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "incident_tasks"

    user_id: Mapped[uuid.UUID] = mapped_column(UuidType, nullable=False)
    incident_id: Mapped[uuid.UUID] = mapped_column(UuidType, nullable=False)
    title: Mapped[str] = mapped_column(sa.String(240), nullable=False)
    description: Mapped[str] = mapped_column(sa.Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(sa.String(24), nullable=False, default="pending")
    owner: Mapped[str] = mapped_column(sa.String(160), nullable=False, default="")

    __table_args__ = (
        sa.Index("ix_incident_tasks_user_id", "user_id"),
        sa.Index("ix_incident_tasks_incident_id", "incident_id"),
        sa.ForeignKeyConstraint(
            ["incident_id"],
            ["incidents.id"],
            name="fk_incident_tasks_incident_id",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'in_progress', 'completed', 'blocked')",
            name="ck_incident_tasks_status",
        ),
    )


class IncidentTimelineEvent(UuidPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "incident_timeline_events"

    user_id: Mapped[uuid.UUID] = mapped_column(UuidType, nullable=False)
    incident_id: Mapped[uuid.UUID] = mapped_column(UuidType, nullable=False)
    event_type: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    message: Mapped[str] = mapped_column(sa.Text, nullable=False)
    actor: Mapped[str] = mapped_column(sa.String(240), nullable=False, default="")

    __table_args__ = (
        sa.Index("ix_incident_timeline_user_id", "user_id"),
        sa.Index("ix_incident_timeline_incident_id", "incident_id"),
        sa.Index("ix_incident_timeline_created_at", sa.text("created_at DESC")),
        sa.ForeignKeyConstraint(
            ["incident_id"],
            ["incidents.id"],
            name="fk_incident_timeline_incident_id",
            ondelete="CASCADE",
        ),
    )
