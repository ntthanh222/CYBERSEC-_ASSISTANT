"""Local RBAC: role/activation state and admin audit trail.

Deliberately decoupled from ``auth.users`` (never adds columns to it - see
migration 0006's docstring for why). ``UserRole`` is looked up by
``user_id`` on every admin-gated request; the JWT's own ``role`` claim (the
Postgres RLS role, always ``authenticated``) is never treated as an
authorization signal.
"""
import uuid
from typing import Any, Optional

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from backend.database.base import (
    Base,
    CreatedAtMixin,
    JSONVariant,
    TimestampMixin,
    UuidType,
)

# Ordered lowest to highest privilege - ROLE_RANK below relies on this order.
ROLES = ("user", "security_analyst", "admin", "super_admin")

# Numeric rank per role, for "does this role satisfy at least X" checks
# (backend/core/authorization.py) and for the admin-tier/super-admin lockout
# invariants in backend/services/rbac.py. Higher always includes the
# privileges of every lower tier.
ROLE_RANK = {role: index for index, role in enumerate(ROLES)}

# Roles that may reach /api/admin/* - the "administrator tier" the system
# must never be left with zero active members of (see RbacService).
ADMIN_TIER_ROLES = ("admin", "super_admin")


class UserRole(TimestampMixin, Base):
    """Single source of truth for a user's app-level role and active state."""

    __tablename__ = "user_roles"

    user_id: Mapped[uuid.UUID] = mapped_column(UuidType, primary_key=True)
    role: Mapped[str] = mapped_column(sa.String(16), nullable=False, server_default="user")
    is_active: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, server_default=sa.true())

    __table_args__ = (
        sa.CheckConstraint(
            "role IN ('user', 'security_analyst', 'admin', 'super_admin')",
            name="ck_user_roles_role",
        ),
    )


class LocalAdminCredential(TimestampMixin, Base):
    """Username/password (Argon2id hash) for the Local Mode admin login.

    Exists only for accounts created via the local admin bootstrap/setup
    flow - a hosted-Supabase admin has a :class:`UserRole` row but never one
    of these.
    """

    __tablename__ = "local_admin_credentials"

    user_id: Mapped[uuid.UUID] = mapped_column(UuidType, primary_key=True)
    username: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    password_hash: Mapped[str] = mapped_column(sa.String(256), nullable=False)
    last_login_at: Mapped[Optional[sa.DateTime]] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        sa.UniqueConstraint("username", name="uq_local_admin_credentials_username"),
    )


class AdminAuditLog(CreatedAtMixin, Base):
    """Persisted record of an admin-initiated action, independent of logs."""

    __tablename__ = "admin_audit_log"

    id: Mapped[uuid.UUID] = mapped_column(UuidType, primary_key=True, default=uuid.uuid4)
    actor_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(UuidType, nullable=True)
    action: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    target_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(UuidType, nullable=True)
    meta: Mapped[Optional[dict[str, Any]]] = mapped_column(
        "meta", JSONVariant, nullable=True
    )

    __table_args__ = (
        sa.Index("ix_admin_audit_log_created_at", "created_at"),
        sa.Index("ix_admin_audit_log_actor_user_id", "actor_user_id"),
    )
