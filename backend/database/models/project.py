"""Project and project-membership models (Task 1: vuln-lifecycle foundation).

A ``Project`` belongs to exactly one ``Workspace`` (CASCADE-deleted with it)
and is the scope every later phase (Scan, Finding, Prioritize, Assign, Fix,
Rescan, Verify, Close) attaches to. Visibility mirrors ``Workspace``: a
caller sees a project if they are a direct ``ProjectMember`` OR an
owner/admin member of the parent workspace (see migration ``0024``'s
join-based RLS policy and ``backend.core.project_authorization``).
"""
import uuid
from datetime import datetime
from typing import Any, List, Optional

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from backend.database.base import Base, JSONVariant, TimestampMixin, UuidPrimaryKeyMixin, UuidType

PROJECT_ENVIRONMENTS = ("development", "staging", "production")
#: Mirrors Asset.business_criticality's value set.
PROJECT_CRITICALITIES = ("low", "medium", "high", "critical")
PROJECT_STATUSES = ("active", "archived")
#: Set-based (not a linear rank) - see backend.core.project_authorization.
PROJECT_MEMBER_ROLES = ("owner", "security", "developer", "viewer")


class Project(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "projects"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UuidType,
        sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    domain: Mapped[Optional[str]] = mapped_column(sa.String(255), nullable=True)
    environment: Mapped[str] = mapped_column(sa.String(16), nullable=False)
    criticality: Mapped[str] = mapped_column(sa.String(16), nullable=False)
    internet_facing: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False)
    # List of {"name": str, "version": str} entries - kept simple exactly
    # like Asset.linked_cves, no join table for this first slice.
    technologies: Mapped[List[dict[str, Any]]] = mapped_column(
        JSONVariant, nullable=False, default=list
    )
    status: Mapped[str] = mapped_column(sa.String(16), nullable=False, default="active")
    archived_at: Mapped[Optional[datetime]] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    # RLS/service-relevant creator column, same role as Workspace.created_by_user_id.
    owner_user_id: Mapped[uuid.UUID] = mapped_column(UuidType, nullable=False)

    __table_args__ = (
        sa.Index("ix_projects_workspace_id", "workspace_id"),
        sa.Index("ix_projects_owner_user_id", "owner_user_id"),
        sa.CheckConstraint(
            "environment IN ('development', 'staging', 'production')",
            name="ck_projects_environment",
        ),
        sa.CheckConstraint(
            "criticality IN ('low', 'medium', 'high', 'critical')",
            name="ck_projects_criticality",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'archived')",
            name="ck_projects_status",
        ),
    )


class ProjectMember(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "project_members"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UuidType,
        sa.ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UuidType, nullable=False)
    project_role: Mapped[str] = mapped_column(sa.String(16), nullable=False)

    __table_args__ = (
        sa.UniqueConstraint("project_id", "user_id", name="uq_project_members_project_user"),
        sa.Index("ix_project_members_project_id", "project_id"),
        sa.Index("ix_project_members_user_id", "user_id"),
        sa.CheckConstraint(
            "project_role IN ('owner', 'security', 'developer', 'viewer')",
            name="ck_project_members_role",
        ),
    )
