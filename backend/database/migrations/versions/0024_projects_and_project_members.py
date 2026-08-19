"""Task 1 (vuln-lifecycle foundation): projects + project members + 'developer' role

Revision ID: 0024
Revises: 0023

Creates ``projects`` (FK to ``workspaces.id`` CASCADE) and ``project_members``,
with join-based RLS visible to a project's own members OR an owner/admin
member of its parent workspace - the two-hop version of 0023's
``messages_via_owning_conversation``-style policy. Not FORCEd, for the same
reason 0023 documents: ``backend.core.project_authorization`` reads these
tables via ``get_db`` as the authoritative check.

Also widens ``user_roles.role`` to add ``'developer'`` - copies
0017_unify_rbac_roles's exact idempotent drop/recreate CHECK-constraint
pattern, which works unchanged on both the SQLite test DB and Postgres.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None

_OLD_ROLES = "role IN ('user', 'security_analyst', 'admin', 'super_admin')"
_NEW_ROLES = "role IN ('user', 'developer', 'security_analyst', 'admin', 'super_admin')"

_PROJECT_VISIBILITY = (
    "owner_user_id = auth.uid() "
    "OR EXISTS (SELECT 1 FROM project_members pm WHERE pm.project_id = projects.id "
    "AND pm.user_id = auth.uid()) "
    "OR EXISTS (SELECT 1 FROM workspace_members wm WHERE wm.workspace_id = projects.workspace_id "
    "AND wm.user_id = auth.uid() AND wm.workspace_role IN ('owner', 'admin')) "
    "OR EXISTS (SELECT 1 FROM user_roles ur WHERE ur.user_id = auth.uid() "
    "AND ur.role IN ('admin', 'super_admin') AND ur.is_active)"
)

_PROJECT_MEMBER_ROW_VISIBILITY = (
    "EXISTS (SELECT 1 FROM project_members pm2 WHERE pm2.project_id = project_members.project_id "
    "AND pm2.user_id = auth.uid()) "
    "OR EXISTS (SELECT 1 FROM projects p WHERE p.id = project_members.project_id "
    "AND p.owner_user_id = auth.uid()) "
    "OR EXISTS (SELECT 1 FROM projects p JOIN workspace_members wm ON wm.workspace_id = p.workspace_id "
    "WHERE p.id = project_members.project_id AND wm.user_id = auth.uid() "
    "AND wm.workspace_role IN ('owner', 'admin')) "
    "OR EXISTS (SELECT 1 FROM user_roles ur WHERE ur.user_id = auth.uid() "
    "AND ur.role IN ('admin', 'super_admin') AND ur.is_active)"
)


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("domain", sa.String(length=255), nullable=True),
        sa.Column("environment", sa.String(length=16), nullable=False),
        sa.Column("criticality", sa.String(length=16), nullable=False),
        sa.Column("internet_facing", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "technologies",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("owner_user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["workspaces.id"], name="fk_projects_workspace_id", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["owner_user_id"], ["auth.users.id"], name="fk_projects_owner_user_id", ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "environment IN ('development', 'staging', 'production')", name="ck_projects_environment"
        ),
        sa.CheckConstraint(
            "criticality IN ('low', 'medium', 'high', 'critical')", name="ck_projects_criticality"
        ),
        sa.CheckConstraint("status IN ('active', 'archived')", name="ck_projects_status"),
    )
    op.create_index("ix_projects_workspace_id", "projects", ["workspace_id"])
    op.create_index("ix_projects_owner_user_id", "projects", ["owner_user_id"])

    op.create_table(
        "project_members",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("project_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("project_role", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name="fk_project_members_project_id", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["auth.users.id"], name="fk_project_members_user_id", ondelete="CASCADE",
        ),
        sa.UniqueConstraint("project_id", "user_id", name="uq_project_members_project_user"),
        sa.CheckConstraint(
            "project_role IN ('owner', 'security', 'developer', 'viewer')",
            name="ck_project_members_role",
        ),
    )
    op.create_index("ix_project_members_project_id", "project_members", ["project_id"])
    op.create_index("ix_project_members_user_id", "project_members", ["user_id"])

    op.execute(sa.text("GRANT SELECT, INSERT, UPDATE, DELETE ON projects TO authenticated"))
    op.execute(
        sa.text("GRANT SELECT, INSERT, UPDATE, DELETE ON project_members TO authenticated")
    )

    op.execute(sa.text("ALTER TABLE projects ENABLE ROW LEVEL SECURITY"))
    op.execute(sa.text("ALTER TABLE project_members ENABLE ROW LEVEL SECURITY"))

    op.execute(
        sa.text(
            f"CREATE POLICY projects_member_or_workspace_admin ON projects "
            f"FOR ALL USING ({_PROJECT_VISIBILITY}) WITH CHECK ({_PROJECT_VISIBILITY})"
        )
    )
    op.execute(
        sa.text(
            f"CREATE POLICY project_members_via_membership ON project_members "
            f"FOR ALL USING ({_PROJECT_MEMBER_ROW_VISIBILITY}) WITH CHECK ({_PROJECT_MEMBER_ROW_VISIBILITY})"
        )
    )

    op.drop_constraint("ck_user_roles_role", "user_roles", type_="check")
    op.create_check_constraint("ck_user_roles_role", "user_roles", _NEW_ROLES)


def downgrade() -> None:
    # No pre-check SELECT here either, for the same reason 0017 documents:
    # ADD CONSTRAINT fails naturally with a real CheckViolation if any row
    # still holds 'developer', rather than silently truncating/reassigning it.
    op.drop_constraint("ck_user_roles_role", "user_roles", type_="check")
    op.create_check_constraint("ck_user_roles_role", "user_roles", _OLD_ROLES)

    op.execute(
        sa.text("DROP POLICY IF EXISTS project_members_via_membership ON project_members")
    )
    op.execute(sa.text("DROP POLICY IF EXISTS projects_member_or_workspace_admin ON projects"))

    op.execute(sa.text("ALTER TABLE project_members DISABLE ROW LEVEL SECURITY"))
    op.execute(sa.text("ALTER TABLE projects DISABLE ROW LEVEL SECURITY"))

    op.execute(
        sa.text("REVOKE SELECT, INSERT, UPDATE, DELETE ON project_members FROM authenticated")
    )
    op.execute(sa.text("REVOKE SELECT, INSERT, UPDATE, DELETE ON projects FROM authenticated"))

    op.drop_index("ix_project_members_user_id", table_name="project_members")
    op.drop_index("ix_project_members_project_id", table_name="project_members")
    op.drop_table("project_members")

    op.drop_index("ix_projects_owner_user_id", table_name="projects")
    op.drop_index("ix_projects_workspace_id", table_name="projects")
    op.drop_table("projects")
