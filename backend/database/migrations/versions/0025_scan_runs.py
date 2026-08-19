"""Task 2 (vuln-lifecycle Scan -> Finding pipeline): scan_runs

Revision ID: 0025
Revises: 0024

Creates ``scan_runs`` - one row per invocation of a scanner (currently only
``url_scan``) against a ``Project``. Additive/parallel to the pre-existing,
untouched ``security_scan_records`` table (the global Scan History page);
this table is what ``findings`` (migration 0026) attaches to.

RLS follows 0024's join pattern: visible to a project's own members OR an
owner/admin member of the project's parent workspace OR a global admin -
the three-hop version (scan_runs -> projects -> workspace_members) of
0024's two-hop project policy. Not FORCEd, for the same reason 0023/0024
document: ``backend.core.project_authorization.get_project_member`` reads
these tables via ``get_db`` as the authoritative check, not RLS.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None

_SCAN_RUN_VISIBILITY = (
    "EXISTS (SELECT 1 FROM project_members pm WHERE pm.project_id = scan_runs.project_id "
    "AND pm.user_id = auth.uid()) "
    "OR EXISTS (SELECT 1 FROM projects p JOIN workspace_members wm ON wm.workspace_id = p.workspace_id "
    "WHERE p.id = scan_runs.project_id AND wm.user_id = auth.uid() "
    "AND wm.workspace_role IN ('owner', 'admin')) "
    "OR EXISTS (SELECT 1 FROM projects p WHERE p.id = scan_runs.project_id "
    "AND p.owner_user_id = auth.uid()) "
    "OR EXISTS (SELECT 1 FROM user_roles ur WHERE ur.user_id = auth.uid() "
    "AND ur.role IN ('admin', 'super_admin') AND ur.is_active)"
)


def upgrade() -> None:
    op.create_table(
        "scan_runs",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("project_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("triggered_by_user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("scan_type", sa.String(length=32), nullable=False),
        sa.Column("target", sa.String(length=2048), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="queued"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "summary", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("previous_scan_run_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name="fk_scan_runs_project_id", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["triggered_by_user_id"], ["auth.users.id"],
            name="fk_scan_runs_triggered_by_user_id", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["previous_scan_run_id"], ["scan_runs.id"],
            name="fk_scan_runs_previous_scan_run_id", ondelete="SET NULL",
        ),
        sa.CheckConstraint("scan_type IN ('url_scan')", name="ck_scan_runs_scan_type"),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'failed')", name="ck_scan_runs_status"
        ),
    )
    op.create_index("ix_scan_runs_project_id", "scan_runs", ["project_id"])
    op.create_index("ix_scan_runs_project_id_status", "scan_runs", ["project_id", "status"])

    op.execute(sa.text("GRANT SELECT, INSERT, UPDATE, DELETE ON scan_runs TO authenticated"))
    op.execute(sa.text("ALTER TABLE scan_runs ENABLE ROW LEVEL SECURITY"))
    op.execute(
        sa.text(
            f"CREATE POLICY scan_runs_via_project_membership ON scan_runs "
            f"FOR ALL USING ({_SCAN_RUN_VISIBILITY}) WITH CHECK ({_SCAN_RUN_VISIBILITY})"
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DROP POLICY IF EXISTS scan_runs_via_project_membership ON scan_runs"))
    op.execute(sa.text("ALTER TABLE scan_runs DISABLE ROW LEVEL SECURITY"))
    op.execute(sa.text("REVOKE SELECT, INSERT, UPDATE, DELETE ON scan_runs FROM authenticated"))

    op.drop_index("ix_scan_runs_project_id_status", table_name="scan_runs")
    op.drop_index("ix_scan_runs_project_id", table_name="scan_runs")
    op.drop_table("scan_runs")
