"""phase 3 codex: threat intelligence iocs

Revision ID: 0008
Revises: 0007
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "threat_iocs",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("type", sa.String(length=16), nullable=False),
        sa.Column("value", sa.String(length=512), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("confidence", sa.String(length=16), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("source", sa.String(length=200), nullable=False),
        sa.Column("first_seen", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=False),
        sa.Column("watchlist", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "tags",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "mitre_techniques",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "risk_timeline",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
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
            ["user_id"], ["auth.users.id"], name="fk_threat_iocs_user_id", ondelete="CASCADE"
        ),
        sa.UniqueConstraint("user_id", "type", "value", name="uq_threat_iocs_owner_type_value"),
        sa.CheckConstraint("type IN ('ip', 'domain', 'url', 'sha256')", name="ck_threat_iocs_type"),
        sa.CheckConstraint(
            "severity IN ('low', 'medium', 'high', 'critical')",
            name="ck_threat_iocs_severity",
        ),
        sa.CheckConstraint(
            "confidence IN ('low', 'medium', 'high')",
            name="ck_threat_iocs_confidence",
        ),
    )
    op.create_index("ix_threat_iocs_user_id", "threat_iocs", ["user_id"])
    op.create_index("ix_threat_iocs_last_seen", "threat_iocs", [sa.text("last_seen DESC")])

    op.execute(sa.text("GRANT SELECT, INSERT, UPDATE, DELETE ON threat_iocs TO authenticated"))
    op.execute(sa.text("ALTER TABLE threat_iocs ENABLE ROW LEVEL SECURITY"))
    op.execute(sa.text("ALTER TABLE threat_iocs FORCE ROW LEVEL SECURITY"))
    op.execute(
        sa.text(
            "CREATE POLICY threat_iocs_owner_only ON threat_iocs "
            "FOR ALL USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id)"
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DROP POLICY IF EXISTS threat_iocs_owner_only ON threat_iocs"))
    op.execute(sa.text("ALTER TABLE threat_iocs NO FORCE ROW LEVEL SECURITY"))
    op.execute(sa.text("ALTER TABLE threat_iocs DISABLE ROW LEVEL SECURITY"))
    op.execute(sa.text("REVOKE SELECT, INSERT, UPDATE, DELETE ON threat_iocs FROM authenticated"))
    op.drop_index("ix_threat_iocs_last_seen", table_name="threat_iocs")
    op.drop_index("ix_threat_iocs_user_id", table_name="threat_iocs")
    op.drop_table("threat_iocs")
