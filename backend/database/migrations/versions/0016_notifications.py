"""phase 3 codex: notification center

Revision ID: 0016
Revises: 0015
"""

import sqlalchemy as sa
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notification_records",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("body", sa.Text(), nullable=False, server_default=""),
        sa.Column("category", sa.String(length=24), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False, server_default="info"),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("source_ref", sa.String(length=200), nullable=False, server_default=""),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["auth.users.id"],
            name="fk_notification_records_user_id",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "category IN ('alert', 'incident', 'vulnerability', 'system')",
            name="ck_notification_records_category",
        ),
        sa.CheckConstraint(
            "severity IN ('info', 'warning', 'critical')",
            name="ck_notification_records_severity",
        ),
    )
    op.create_index("ix_notification_records_user_id", "notification_records", ["user_id"])
    op.create_index(
        "ix_notification_records_created_at", "notification_records", [sa.text("created_at DESC")]
    )
    op.execute(
        sa.text("GRANT SELECT, INSERT, UPDATE, DELETE ON notification_records TO authenticated")
    )
    op.execute(sa.text("ALTER TABLE notification_records ENABLE ROW LEVEL SECURITY"))
    op.execute(sa.text("ALTER TABLE notification_records FORCE ROW LEVEL SECURITY"))
    op.execute(
        sa.text(
            "CREATE POLICY notification_records_owner_only ON notification_records "
            "FOR ALL USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id)"
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text("DROP POLICY IF EXISTS notification_records_owner_only ON notification_records")
    )
    op.execute(sa.text("ALTER TABLE notification_records NO FORCE ROW LEVEL SECURITY"))
    op.execute(sa.text("ALTER TABLE notification_records DISABLE ROW LEVEL SECURITY"))
    op.execute(
        sa.text("REVOKE SELECT, INSERT, UPDATE, DELETE ON notification_records FROM authenticated")
    )
    op.drop_index("ix_notification_records_created_at", table_name="notification_records")
    op.drop_index("ix_notification_records_user_id", table_name="notification_records")
    op.drop_table("notification_records")
