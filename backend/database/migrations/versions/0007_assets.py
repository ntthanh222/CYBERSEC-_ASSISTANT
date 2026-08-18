"""phase 3 task #5: asset inventory

Revision ID: 0007
Revises: 0006

Creates ``assets`` — analyst-entered inventory data, owner-scoped exactly
like ``conversations``/``security_scan_history`` (migration 0004): a
``user_id`` column, RLS enabled + forced, and an owner-only policy. Combined
into a single migration (create + RLS) since, unlike 0004, this is a brand
new table rather than retrofitting RLS onto pre-existing rows.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "assets",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("hostname", sa.String(length=255), nullable=False),
        sa.Column("ip_address", sa.String(length=64), nullable=False),
        sa.Column("operating_system", sa.String(length=200), nullable=False),
        sa.Column("owner", sa.String(length=200), nullable=False),
        sa.Column("department", sa.String(length=200), nullable=False),
        sa.Column("business_criticality", sa.String(length=16), nullable=False),
        sa.Column("internet_exposed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "linked_cves", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
        sa.Column("patch_status", sa.String(length=16), nullable=True),
        sa.Column("exploit_evidence", sa.String(length=32), nullable=True),
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
            name="fk_assets_user_id",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "type IN ('server', 'workstation', 'cloud_resource', 'database', 'network_device')",
            name="ck_assets_type",
        ),
        sa.CheckConstraint(
            "business_criticality IN ('low', 'medium', 'high', 'critical')",
            name="ck_assets_business_criticality",
        ),
        sa.CheckConstraint(
            "patch_status IS NULL OR patch_status IN "
            "('unknown', 'not_started', 'in_progress', 'patched', "
            "'accepted_risk', 'not_applicable')",
            name="ck_assets_patch_status",
        ),
        sa.CheckConstraint(
            "exploit_evidence IS NULL OR exploit_evidence IN "
            "('none', 'unconfirmed', 'public_poc', 'active_exploitation', 'internal_confirmation')",
            name="ck_assets_exploit_evidence",
        ),
    )
    op.create_index("ix_assets_user_id", "assets", ["user_id"])
    op.create_index("ix_assets_created_at", "assets", [sa.text("created_at DESC")])

    op.execute(sa.text("GRANT SELECT, INSERT, UPDATE, DELETE ON assets TO authenticated"))
    op.execute(sa.text("ALTER TABLE assets ENABLE ROW LEVEL SECURITY"))
    op.execute(sa.text("ALTER TABLE assets FORCE ROW LEVEL SECURITY"))
    op.execute(
        sa.text(
            "CREATE POLICY assets_owner_only ON assets "
            "FOR ALL "
            "USING (auth.uid() = user_id) "
            "WITH CHECK (auth.uid() = user_id)"
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DROP POLICY IF EXISTS assets_owner_only ON assets"))
    op.execute(sa.text("ALTER TABLE assets NO FORCE ROW LEVEL SECURITY"))
    op.execute(sa.text("ALTER TABLE assets DISABLE ROW LEVEL SECURITY"))
    op.execute(sa.text("REVOKE SELECT, INSERT, UPDATE, DELETE ON assets FROM authenticated"))

    op.drop_index("ix_assets_created_at", table_name="assets")
    op.drop_index("ix_assets_user_id", table_name="assets")
    op.drop_table("assets")
