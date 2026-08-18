"""phase 3.1: local RBAC (user_roles, local_admin_credentials, admin_audit_log)

Revision ID: 0006
Revises: 0005

Adds application-level role/authorization state, decoupled from identity.
``auth.users`` (real Supabase, or the local shim migration 0004 creates) stays
untouched - no columns are added to it, so this remains compatible with a
real hosted Supabase project were one ever configured. Instead:

* ``user_roles`` is the single source of truth for ``role`` (``user`` /
  ``admin``) and ``is_active``, keyed by ``user_id`` (the JWT ``sub`` /
  ``auth.uid()`` value) regardless of *how* that identity was established
  (Local Mode demo session or a real Supabase session). A request's JWT
  ``role`` claim is never trusted for authorization - every admin-gated
  endpoint re-reads this table on every request (see
  ``backend/core/authorization.py``), so a role change or deactivation takes
  effect immediately, not just after the token expires.
* ``local_admin_credentials`` holds the username/password Argon2id hash for
  the Local Mode password-based admin login - a *separate* concern from
  ``user_roles``. It only ever exists for accounts created via the local
  admin bootstrap/setup flow; a hosted-Supabase-authenticated admin has a
  ``user_roles`` row but no row here.
* ``admin_audit_log`` persists admin-initiated actions (role changes,
  activation/deactivation, admin login) so they survive a restart and are
  independently queryable - the existing ``log_audit_event`` (Phase 1.5) is
  structured-log-only and was explicitly scoped to not need a persistence
  store; this migration is what closes that gap for admin actions
  specifically, not a blanket audit table for every request.

This migration does not restore, and is unrelated to, the quarantined
``0004_auth_users`` migration (tag ``quarantine/auth-rbac-phase3-cd5bda2``),
which created its own competing ``users`` identity table and
application-issued JWTs. Identity here still comes only from
:mod:`backend.core.auth` (Supabase-verified or the local-shim JWT); this
migration only adds *authorization* state layered on top of that identity.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_roles",
        sa.Column("user_id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("role", sa.String(16), nullable=False, server_default="user"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint("role IN ('user', 'admin')", name="ck_user_roles_role"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["auth.users.id"], name="fk_user_roles_user_id", ondelete="CASCADE"
        ),
    )
    op.create_index("ix_user_roles_role", "user_roles", ["role"])

    op.create_table(
        "local_admin_credentials",
        sa.Column("user_id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("username", sa.String(64), nullable=False),
        sa.Column("password_hash", sa.String(256), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("username", name="uq_local_admin_credentials_username"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["auth.users.id"],
            name="fk_local_admin_credentials_user_id",
            ondelete="CASCADE",
        ),
    )

    op.create_table(
        "admin_audit_log",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("actor_user_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("target_user_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("meta", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["auth.users.id"],
            name="fk_admin_audit_log_actor_user_id",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["target_user_id"],
            ["auth.users.id"],
            name="fk_admin_audit_log_target_user_id",
            ondelete="SET NULL",
        ),
    )
    op.create_index("ix_admin_audit_log_created_at", "admin_audit_log", ["created_at"])
    op.create_index("ix_admin_audit_log_actor_user_id", "admin_audit_log", ["actor_user_id"])


def downgrade() -> None:
    op.drop_index("ix_admin_audit_log_actor_user_id", table_name="admin_audit_log")
    op.drop_index("ix_admin_audit_log_created_at", table_name="admin_audit_log")
    op.drop_table("admin_audit_log")
    op.drop_table("local_admin_credentials")
    op.drop_index("ix_user_roles_role", table_name="user_roles")
    op.drop_table("user_roles")
