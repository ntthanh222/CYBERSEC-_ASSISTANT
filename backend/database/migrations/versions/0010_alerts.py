"""phase 3 codex: alerts

Revision ID: 0010
Revises: 0009
"""
import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "alerts",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("source", sa.String(length=160), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("asset_name", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("ioc_value", sa.String(length=512), nullable=False, server_default=""),
        sa.Column("evidence", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["auth.users.id"],
            name="fk_alerts_user_id",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "severity IN ('low', 'medium', 'high', 'critical')",
            name="ck_alerts_severity",
        ),
        sa.CheckConstraint(
            "status IN ('new', 'acknowledged', 'investigating', 'resolved', 'false_positive')",
            name="ck_alerts_status",
        ),
    )
    op.create_index("ix_alerts_user_id", "alerts", ["user_id"])
    op.create_index("ix_alerts_created_at", "alerts", [sa.text("created_at DESC")])
    op.execute(sa.text("GRANT SELECT, INSERT, UPDATE, DELETE ON alerts TO authenticated"))
    op.execute(sa.text("ALTER TABLE alerts ENABLE ROW LEVEL SECURITY"))
    op.execute(sa.text("ALTER TABLE alerts FORCE ROW LEVEL SECURITY"))
    op.execute(
        sa.text(
            "CREATE POLICY alerts_owner_only ON alerts "
            "FOR ALL USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id)"
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DROP POLICY IF EXISTS alerts_owner_only ON alerts"))
    op.execute(sa.text("ALTER TABLE alerts NO FORCE ROW LEVEL SECURITY"))
    op.execute(sa.text("ALTER TABLE alerts DISABLE ROW LEVEL SECURITY"))
    op.execute(sa.text("REVOKE SELECT, INSERT, UPDATE, DELETE ON alerts FROM authenticated"))
    op.drop_index("ix_alerts_created_at", table_name="alerts")
    op.drop_index("ix_alerts_user_id", table_name="alerts")
    op.drop_table("alerts")
