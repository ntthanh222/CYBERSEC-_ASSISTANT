"""Task 1 (vuln-lifecycle foundation): workspaces + membership

Revision ID: 0023
Revises: 0022

Creates ``workspaces`` and ``workspace_members`` - the top-level container
the new vulnerability-management lifecycle (Workspace -> Project -> Scan ->
Finding -> ... -> Close) is built on. Unlike the owner-only tables in
migrations 0004/0007 (``auth.uid() = user_id``), a workspace is visible to
every listed member, not just its creator, so the RLS policy below is
join-based - following the ``messages_via_owning_conversation`` pattern from
0004 - rather than a single-column comparison.

Deliberately **not** FORCEd, unlike 0004/0007's owner-only tables. Both
``backend.core.workspace_authorization.get_workspace_member`` (the
authoritative 404/403 check every workspace route relies on) and
``backend.services.project.ProjectService._authorize_project_creation``
query these tables through ``get_db`` - a plain session that never runs as
the ``authenticated`` role and never sets ``request.jwt.claims`` - precisely
so that check is not itself gated by the very membership row it exists to
look up. Without FORCE, Postgres exempts the connecting (table-owner) role
from RLS by default, so that plain session sees every row while the
``authenticated``-role session used by ``get_rls_db`` still gets full
policy enforcement as defense in depth.
"""
import sqlalchemy as sa
from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None

_MEMBER_VISIBILITY = (
    "created_by_user_id = auth.uid() "
    "OR EXISTS (SELECT 1 FROM workspace_members wm WHERE wm.workspace_id = workspaces.id "
    "AND wm.user_id = auth.uid()) "
    "OR EXISTS (SELECT 1 FROM user_roles ur WHERE ur.user_id = auth.uid() "
    "AND ur.role IN ('admin', 'super_admin') AND ur.is_active)"
)

_MEMBER_ROW_VISIBILITY = (
    "EXISTS (SELECT 1 FROM workspace_members wm2 WHERE wm2.workspace_id = workspace_members.workspace_id "
    "AND wm2.user_id = auth.uid()) "
    "OR EXISTS (SELECT 1 FROM workspaces w WHERE w.id = workspace_members.workspace_id "
    "AND w.created_by_user_id = auth.uid()) "
    "OR EXISTS (SELECT 1 FROM user_roles ur WHERE ur.user_id = auth.uid() "
    "AND ur.role IN ('admin', 'super_admin') AND ur.is_active)"
)


def upgrade() -> None:
    op.create_table(
        "workspaces",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["auth.users.id"],
            name="fk_workspaces_created_by_user_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_workspaces_created_by_user_id", "workspaces", ["created_by_user_id"])

    op.create_table(
        "workspace_members",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("workspace_role", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["workspaces.id"], name="fk_workspace_members_workspace_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["auth.users.id"], name="fk_workspace_members_user_id", ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "workspace_id", "user_id", name="uq_workspace_members_workspace_user"
        ),
        sa.CheckConstraint(
            "workspace_role IN ('owner', 'admin', 'member')", name="ck_workspace_members_role"
        ),
    )
    op.create_index("ix_workspace_members_workspace_id", "workspace_members", ["workspace_id"])
    op.create_index("ix_workspace_members_user_id", "workspace_members", ["user_id"])

    op.execute(sa.text("GRANT SELECT, INSERT, UPDATE, DELETE ON workspaces TO authenticated"))
    op.execute(
        sa.text("GRANT SELECT, INSERT, UPDATE, DELETE ON workspace_members TO authenticated")
    )

    op.execute(sa.text("ALTER TABLE workspaces ENABLE ROW LEVEL SECURITY"))
    op.execute(sa.text("ALTER TABLE workspace_members ENABLE ROW LEVEL SECURITY"))

    op.execute(
        sa.text(
            f"CREATE POLICY workspaces_owner_or_member ON workspaces "
            f"FOR ALL USING ({_MEMBER_VISIBILITY}) WITH CHECK ({_MEMBER_VISIBILITY})"
        )
    )
    op.execute(
        sa.text(
            f"CREATE POLICY workspace_members_via_membership ON workspace_members "
            f"FOR ALL USING ({_MEMBER_ROW_VISIBILITY}) WITH CHECK ({_MEMBER_ROW_VISIBILITY})"
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text("DROP POLICY IF EXISTS workspace_members_via_membership ON workspace_members")
    )
    op.execute(sa.text("DROP POLICY IF EXISTS workspaces_owner_or_member ON workspaces"))

    op.execute(sa.text("ALTER TABLE workspace_members DISABLE ROW LEVEL SECURITY"))
    op.execute(sa.text("ALTER TABLE workspaces DISABLE ROW LEVEL SECURITY"))

    op.execute(
        sa.text("REVOKE SELECT, INSERT, UPDATE, DELETE ON workspace_members FROM authenticated")
    )
    op.execute(sa.text("REVOKE SELECT, INSERT, UPDATE, DELETE ON workspaces FROM authenticated"))

    op.drop_index("ix_workspace_members_user_id", table_name="workspace_members")
    op.drop_index("ix_workspace_members_workspace_id", table_name="workspace_members")
    op.drop_table("workspace_members")

    op.drop_index("ix_workspaces_created_by_user_id", table_name="workspaces")
    op.drop_table("workspaces")
