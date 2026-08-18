"""phase 3 codex: reports center

Revision ID: 0015
Revises: 0014
"""

import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "report_records",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("category", sa.String(length=24), nullable=False),
        sa.Column("format", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("sections", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("scope", sa.Text(), nullable=False, server_default=""),
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
        sa.Column("error_message", sa.String(length=400), nullable=False, server_default=""),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["auth.users.id"],
            name="fk_report_records_user_id",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "category IN ('executive', 'technical', 'compliance', 'incident')",
            name="ck_report_records_category",
        ),
        sa.CheckConstraint("format IN ('markdown', 'csv')", name="ck_report_records_format"),
        sa.CheckConstraint("status IN ('completed', 'failed')", name="ck_report_records_status"),
    )
    op.create_index("ix_report_records_user_id", "report_records", ["user_id"])
    op.create_index("ix_report_records_created_at", "report_records", [sa.text("created_at DESC")])
    op.execute(sa.text("GRANT SELECT, INSERT, UPDATE, DELETE ON report_records TO authenticated"))
    op.execute(sa.text("ALTER TABLE report_records ENABLE ROW LEVEL SECURITY"))
    op.execute(sa.text("ALTER TABLE report_records FORCE ROW LEVEL SECURITY"))
    op.execute(
        sa.text(
            "CREATE POLICY report_records_owner_only ON report_records "
            "FOR ALL USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id)"
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DROP POLICY IF EXISTS report_records_owner_only ON report_records"))
    op.execute(sa.text("ALTER TABLE report_records NO FORCE ROW LEVEL SECURITY"))
    op.execute(sa.text("ALTER TABLE report_records DISABLE ROW LEVEL SECURITY"))
    op.execute(
        sa.text("REVOKE SELECT, INSERT, UPDATE, DELETE ON report_records FROM authenticated")
    )
    op.drop_index("ix_report_records_created_at", table_name="report_records")
    op.drop_index("ix_report_records_user_id", table_name="report_records")
    op.drop_table("report_records")
