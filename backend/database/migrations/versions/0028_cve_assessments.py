"""Task 6 (CVE Risk Prioritization): cve_assessments

Revision ID: 0028
Revises: 0027

Creates ``cve_assessments`` - one row per ``(project_id, cve_id)`` pair,
persisting the deterministic prioritization result
(``backend.services.cve_priority.assess``) computed from the existing NVD
CVSS lookup plus this task's new EPSS/KEV enrichment data and the project's
own risk context. See ``backend/database/models/cve_assessment.py``'s module
docstring for the upsert semantics.

RLS mirrors 0026's ``findings`` policy exactly (join through
``project_members``/workspace-owner-admin/global-admin) - same visibility
shape, since a CVE assessment is scoped to a project the same way a finding
is. Not FORCEd, for the same reason 0023-0027 document: the route-level
``backend.core.project_authorization`` dependencies are the authoritative
check, RLS here is defense-in-depth.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None

_CVE_ASSESSMENT_VISIBILITY = (
    "EXISTS (SELECT 1 FROM project_members pm WHERE pm.project_id = cve_assessments.project_id "
    "AND pm.user_id = auth.uid()) "
    "OR EXISTS (SELECT 1 FROM projects p JOIN workspace_members wm ON wm.workspace_id = p.workspace_id "
    "WHERE p.id = cve_assessments.project_id AND wm.user_id = auth.uid() "
    "AND wm.workspace_role IN ('owner', 'admin')) "
    "OR EXISTS (SELECT 1 FROM projects p WHERE p.id = cve_assessments.project_id "
    "AND p.owner_user_id = auth.uid()) "
    "OR EXISTS (SELECT 1 FROM user_roles ur WHERE ur.user_id = auth.uid() "
    "AND ur.role IN ('admin', 'super_admin') AND ur.is_active)"
)

_PRIORITY_LABELS = ("patch_now", "high", "medium", "low", "not_affected", "needs_review")


def upgrade() -> None:
    op.create_table(
        "cve_assessments",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("project_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("cve_id", sa.String(length=32), nullable=False),
        sa.Column("cvss_score", sa.Float(), nullable=True),
        sa.Column("epss_score", sa.Float(), nullable=True),
        sa.Column("is_kev", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("affected_version", sa.String(length=100), nullable=True),
        sa.Column("fixed_version", sa.String(length=100), nullable=True),
        sa.Column("technology", sa.String(length=200), nullable=True),
        sa.Column("priority", sa.String(length=16), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column(
            "rationale", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("finding_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name="fk_cve_assessments_project_id", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["finding_id"], ["findings.id"], name="fk_cve_assessments_finding_id", ondelete="SET NULL",
        ),
        sa.UniqueConstraint("project_id", "cve_id", name="uq_cve_assessments_project_cve"),
        sa.CheckConstraint(
            "priority IN (" + ", ".join(f"'{label}'" for label in _PRIORITY_LABELS) + ")",
            name="ck_cve_assessments_priority",
        ),
    )
    op.create_index("ix_cve_assessments_project_id", "cve_assessments", ["project_id"])

    op.execute(sa.text("GRANT SELECT, INSERT, UPDATE, DELETE ON cve_assessments TO authenticated"))
    op.execute(sa.text("ALTER TABLE cve_assessments ENABLE ROW LEVEL SECURITY"))
    op.execute(
        sa.text(
            f"CREATE POLICY cve_assessments_via_project_membership ON cve_assessments "
            f"FOR ALL USING ({_CVE_ASSESSMENT_VISIBILITY}) WITH CHECK ({_CVE_ASSESSMENT_VISIBILITY})"
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text("DROP POLICY IF EXISTS cve_assessments_via_project_membership ON cve_assessments")
    )
    op.execute(sa.text("ALTER TABLE cve_assessments DISABLE ROW LEVEL SECURITY"))
    op.execute(sa.text("REVOKE SELECT, INSERT, UPDATE, DELETE ON cve_assessments FROM authenticated"))

    op.drop_index("ix_cve_assessments_project_id", table_name="cve_assessments")
    op.drop_table("cve_assessments")
