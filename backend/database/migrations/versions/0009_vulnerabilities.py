"""phase 3 codex: vulnerability management

Revision ID: 0009
Revises: 0008
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "vulnerabilities",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("cve_id", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("cvss", sa.Float(), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("published_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "references",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "affected_products",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("remediation", sa.Text(), nullable=False, server_default=""),
        sa.Column("watchlist", sa.Boolean(), nullable=False, server_default=sa.false()),
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
            name="fk_vulnerabilities_user_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("user_id", "cve_id", name="uq_vulnerabilities_owner_cve"),
        sa.CheckConstraint(
            "severity IN ('low', 'medium', 'high', 'critical')",
            name="ck_vulnerabilities_severity",
        ),
        sa.CheckConstraint("cvss >= 0 AND cvss <= 10", name="ck_vulnerabilities_cvss"),
    )
    op.create_index("ix_vulnerabilities_user_id", "vulnerabilities", ["user_id"])
    op.create_index(
        "ix_vulnerabilities_updated_date",
        "vulnerabilities",
        [sa.text("updated_date DESC")],
    )

    op.create_table(
        "vulnerability_patch_tasks",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("vulnerability_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("asset_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("asset_name", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
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
            name="fk_patch_tasks_user_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["vulnerability_id"],
            ["vulnerabilities.id"],
            name="fk_patch_tasks_vulnerability_id",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "status IN ('not_started', 'in_progress', 'patched', 'accepted_risk')",
            name="ck_patch_tasks_status",
        ),
    )
    op.create_index(
        "ix_vulnerability_patch_tasks_user_id",
        "vulnerability_patch_tasks",
        ["user_id"],
    )
    op.create_index(
        "ix_vulnerability_patch_tasks_vulnerability_id",
        "vulnerability_patch_tasks",
        ["vulnerability_id"],
    )

    for table in ("vulnerabilities", "vulnerability_patch_tasks"):
        op.execute(
            sa.text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text -- static schema migration string
                f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO authenticated"
            )
        )
        op.execute(
            sa.text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text -- static schema migration string
                f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"
            )
        )
        op.execute(
            sa.text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text -- static schema migration string
                f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"
            )
        )
        op.execute(
            sa.text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text -- static schema migration string
                f"CREATE POLICY {table}_owner_only ON {table} "
                "FOR ALL USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id)"
            )
        )


def downgrade() -> None:
    for table in ("vulnerability_patch_tasks", "vulnerabilities"):
        op.execute(
            sa.text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text -- static schema migration string
                f"DROP POLICY IF EXISTS {table}_owner_only ON {table}"
            )
        )
        op.execute(
            sa.text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text -- static schema migration string
                f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY"
            )
        )
        op.execute(
            sa.text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text -- static schema migration string
                f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY"
            )
        )
        op.execute(
            sa.text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text -- static schema migration string
                f"REVOKE SELECT, INSERT, UPDATE, DELETE ON {table} FROM authenticated"
            )
        )
    op.drop_index(
        "ix_vulnerability_patch_tasks_vulnerability_id",
        table_name="vulnerability_patch_tasks",
    )
    op.drop_index("ix_vulnerability_patch_tasks_user_id", table_name="vulnerability_patch_tasks")
    op.drop_table("vulnerability_patch_tasks")
    op.drop_index("ix_vulnerabilities_updated_date", table_name="vulnerabilities")
    op.drop_index("ix_vulnerabilities_user_id", table_name="vulnerabilities")
    op.drop_table("vulnerabilities")
