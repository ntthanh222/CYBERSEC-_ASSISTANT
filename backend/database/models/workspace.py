"""Workspace and workspace-membership models (Task 1: vuln-lifecycle foundation).

A ``Workspace`` is the top-level container the new vulnerability-management
lifecycle (Workspace -> Project -> Scan -> Finding -> ... -> Close) is built
on. Unlike the owner-only tables in ``asset.py``/``conversation.py``, a
workspace is visible to every member listed in ``workspace_members``, not
just its creator - membership, not `user_id == auth.uid()`, is the
visibility rule enforced by the RLS policy in migration ``0023``.

``WorkspaceMember`` deliberately has no direct FK to ``auth.users`` beyond the
raw ``user_id`` column (same posture as ``Asset.user_id``): identity lives in
Supabase, this table only records the membership fact.
"""
import uuid
from typing import Optional

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from backend.database.base import Base, TimestampMixin, UuidPrimaryKeyMixin, UuidType

#: Ordered lowest to highest workspace-scoped privilege.
WORKSPACE_ROLES = ("owner", "admin", "member")


class Workspace(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "workspaces"

    name: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(sa.Text, nullable=True)
    # RLS-relevant owner column, same role as Asset.user_id: the caller who
    # created the workspace, always auto-added as its first "owner" member.
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(UuidType, nullable=False)

    __table_args__ = (sa.Index("ix_workspaces_created_by_user_id", "created_by_user_id"),)


class WorkspaceMember(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "workspace_members"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UuidType,
        sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UuidType, nullable=False)
    workspace_role: Mapped[str] = mapped_column(sa.String(16), nullable=False)

    __table_args__ = (
        sa.UniqueConstraint("workspace_id", "user_id", name="uq_workspace_members_workspace_user"),
        sa.Index("ix_workspace_members_workspace_id", "workspace_id"),
        sa.Index("ix_workspace_members_user_id", "user_id"),
        sa.CheckConstraint(
            "workspace_role IN ('owner', 'admin', 'member')",
            name="ck_workspace_members_role",
        ),
    )
