"""phase 3 codex: mitre coverage

Revision ID: 0012
Revises: 0011
"""

import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mitre_technique_coverage",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("technique_id", sa.String(length=32), nullable=False),
        sa.Column("tactic", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=240), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("detection", sa.Text(), nullable=False, server_default=""),
        sa.Column("mitigation", sa.Text(), nullable=False, server_default=""),
        sa.Column("coverage_status", sa.String(length=16), nullable=False),
        sa.Column("data_sources", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["auth.users.id"],
            name="fk_mitre_coverage_user_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("user_id", "technique_id", name="uq_mitre_coverage_owner_technique"),
        sa.CheckConstraint(
            "coverage_status IN ('planned', 'partial', 'covered', 'gap')",
            name="ck_mitre_coverage_status",
        ),
    )
    op.create_index("ix_mitre_coverage_user_id", "mitre_technique_coverage", ["user_id"])
    op.create_index("ix_mitre_coverage_tactic", "mitre_technique_coverage", ["tactic"])
    op.execute(
        sa.text("GRANT SELECT, INSERT, UPDATE, DELETE ON mitre_technique_coverage TO authenticated")
    )
    op.execute(sa.text("ALTER TABLE mitre_technique_coverage ENABLE ROW LEVEL SECURITY"))
    op.execute(sa.text("ALTER TABLE mitre_technique_coverage FORCE ROW LEVEL SECURITY"))
    op.execute(
        sa.text(
            "CREATE POLICY mitre_coverage_owner_only ON mitre_technique_coverage "
            "FOR ALL USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id)"
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text("DROP POLICY IF EXISTS mitre_coverage_owner_only ON mitre_technique_coverage")
    )
    op.execute(sa.text("ALTER TABLE mitre_technique_coverage NO FORCE ROW LEVEL SECURITY"))
    op.execute(sa.text("ALTER TABLE mitre_technique_coverage DISABLE ROW LEVEL SECURITY"))
    op.execute(
        sa.text(
            "REVOKE SELECT, INSERT, UPDATE, DELETE ON mitre_technique_coverage FROM authenticated"
        )
    )
    op.drop_index("ix_mitre_coverage_tactic", table_name="mitre_technique_coverage")
    op.drop_index("ix_mitre_coverage_user_id", table_name="mitre_technique_coverage")
    op.drop_table("mitre_technique_coverage")
