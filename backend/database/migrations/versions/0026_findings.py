"""Task 2 (vuln-lifecycle Scan -> Finding pipeline): findings + finding_transitions

Revision ID: 0026
Revises: 0025

Creates ``findings`` (structured vulnerability rows moving through the
server-enforced state machine in ``backend.services.finding_state_machine``)
and ``finding_transitions`` (an immutable timeline of every status change,
mirroring ``IncidentTimelineEvent``'s pattern without touching that table).

RLS mirrors 0025's scan_runs policy (join through project_members), applied
to both tables - ``finding_transitions`` joins through its parent
``findings`` row the same way 0004's ``messages_via_owning_conversation``
pattern joins through its parent conversation.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None

_FINDING_VISIBILITY = (
    "EXISTS (SELECT 1 FROM project_members pm WHERE pm.project_id = findings.project_id "
    "AND pm.user_id = auth.uid()) "
    "OR EXISTS (SELECT 1 FROM projects p JOIN workspace_members wm ON wm.workspace_id = p.workspace_id "
    "WHERE p.id = findings.project_id AND wm.user_id = auth.uid() "
    "AND wm.workspace_role IN ('owner', 'admin')) "
    "OR EXISTS (SELECT 1 FROM projects p WHERE p.id = findings.project_id "
    "AND p.owner_user_id = auth.uid()) "
    "OR EXISTS (SELECT 1 FROM user_roles ur WHERE ur.user_id = auth.uid() "
    "AND ur.role IN ('admin', 'super_admin') AND ur.is_active)"
)

_FINDING_TRANSITION_VISIBILITY = (
    "EXISTS (SELECT 1 FROM findings f JOIN project_members pm ON pm.project_id = f.project_id "
    "WHERE f.id = finding_transitions.finding_id AND pm.user_id = auth.uid()) "
    "OR EXISTS (SELECT 1 FROM findings f JOIN projects p ON p.id = f.project_id "
    "JOIN workspace_members wm ON wm.workspace_id = p.workspace_id "
    "WHERE f.id = finding_transitions.finding_id AND wm.user_id = auth.uid() "
    "AND wm.workspace_role IN ('owner', 'admin')) "
    "OR EXISTS (SELECT 1 FROM findings f JOIN projects p ON p.id = f.project_id "
    "WHERE f.id = finding_transitions.finding_id AND p.owner_user_id = auth.uid()) "
    "OR EXISTS (SELECT 1 FROM user_roles ur WHERE ur.user_id = auth.uid() "
    "AND ur.role IN ('admin', 'super_admin') AND ur.is_active)"
)


def upgrade() -> None:
    op.create_table(
        "findings",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("project_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("scan_run_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("rule_id", sa.String(length=100), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=False),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("evidence", sa.Text(), nullable=False, server_default=""),
        sa.Column("impact", sa.Text(), nullable=False, server_default=""),
        sa.Column("remediation", sa.Text(), nullable=False, server_default=""),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="open"),
        sa.Column("target", sa.String(length=2048), nullable=False),
        sa.Column("cve_id", sa.String(length=32), nullable=True),
        sa.Column("assignee_user_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("deadline", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verification_notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("resolution_reason", sa.Text(), nullable=True),
        sa.Column("first_seen_scan_run_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("last_seen_scan_run_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name="fk_findings_project_id", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["scan_run_id"], ["scan_runs.id"], name="fk_findings_scan_run_id", ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["assignee_user_id"], ["auth.users.id"],
            name="fk_findings_assignee_user_id", ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["first_seen_scan_run_id"], ["scan_runs.id"],
            name="fk_findings_first_seen_scan_run_id", ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["last_seen_scan_run_id"], ["scan_runs.id"],
            name="fk_findings_last_seen_scan_run_id", ondelete="SET NULL",
        ),
        sa.UniqueConstraint("project_id", "fingerprint", name="uq_findings_project_fingerprint"),
        sa.CheckConstraint(
            "severity IN ('low', 'medium', 'high', 'critical')", name="ck_findings_severity"
        ),
        sa.CheckConstraint(
            "status IN ("
            "'open', 'confirmed', 'in_progress', 'fixed', 'verified', 'closed', "
            "'false_positive', 'accepted_risk', 'reopened'"
            ")",
            name="ck_findings_status",
        ),
    )
    op.create_index("ix_findings_project_id_status", "findings", ["project_id", "status"])
    op.create_index(
        "ix_findings_assignee_user_id_status", "findings", ["assignee_user_id", "status"]
    )

    op.create_table(
        "finding_transitions",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("finding_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("from_status", sa.String(length=24), nullable=False),
        sa.Column("to_status", sa.String(length=24), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "meta", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["finding_id"], ["findings.id"], name="fk_finding_transitions_finding_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"], ["auth.users.id"],
            name="fk_finding_transitions_actor_user_id", ondelete="CASCADE",
        ),
    )
    op.create_index("ix_finding_transitions_finding_id", "finding_transitions", ["finding_id"])

    op.execute(sa.text("GRANT SELECT, INSERT, UPDATE, DELETE ON findings TO authenticated"))
    op.execute(
        sa.text("GRANT SELECT, INSERT, UPDATE, DELETE ON finding_transitions TO authenticated")
    )
    op.execute(sa.text("ALTER TABLE findings ENABLE ROW LEVEL SECURITY"))
    op.execute(sa.text("ALTER TABLE finding_transitions ENABLE ROW LEVEL SECURITY"))

    op.execute(
        sa.text(
            f"CREATE POLICY findings_via_project_membership ON findings "
            f"FOR ALL USING ({_FINDING_VISIBILITY}) WITH CHECK ({_FINDING_VISIBILITY})"
        )
    )
    op.execute(
        sa.text(
            f"CREATE POLICY finding_transitions_via_finding_project ON finding_transitions "
            f"FOR ALL USING ({_FINDING_TRANSITION_VISIBILITY}) "
            f"WITH CHECK ({_FINDING_TRANSITION_VISIBILITY})"
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text("DROP POLICY IF EXISTS finding_transitions_via_finding_project ON finding_transitions")
    )
    op.execute(sa.text("DROP POLICY IF EXISTS findings_via_project_membership ON findings"))

    op.execute(sa.text("ALTER TABLE finding_transitions DISABLE ROW LEVEL SECURITY"))
    op.execute(sa.text("ALTER TABLE findings DISABLE ROW LEVEL SECURITY"))

    op.execute(
        sa.text("REVOKE SELECT, INSERT, UPDATE, DELETE ON finding_transitions FROM authenticated")
    )
    op.execute(sa.text("REVOKE SELECT, INSERT, UPDATE, DELETE ON findings FROM authenticated"))

    op.drop_index("ix_finding_transitions_finding_id", table_name="finding_transitions")
    op.drop_table("finding_transitions")

    op.drop_index("ix_findings_assignee_user_id_status", table_name="findings")
    op.drop_index("ix_findings_project_id_status", table_name="findings")
    op.drop_table("findings")
