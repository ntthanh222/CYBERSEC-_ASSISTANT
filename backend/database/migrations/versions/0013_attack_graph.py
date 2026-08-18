"""phase 3 codex: attack graph

Revision ID: 0013
Revises: 0012
"""

import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "attack_graph_nodes",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("node_type", sa.String(length=24), nullable=False),
        sa.Column("label", sa.String(length=240), nullable=False),
        sa.Column("ip_address", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("cves", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("position_x", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("position_y", sa.Integer(), nullable=False, server_default="100"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["auth.users.id"], name="fk_attack_graph_nodes_user_id", ondelete="CASCADE"
        ),
        sa.CheckConstraint(
            "node_type IN ('attacker', 'asset', 'database', 'gateway', 'target')",
            name="ck_attack_graph_nodes_type",
        ),
        sa.CheckConstraint(
            "status IN ('compromised', 'vulnerable', 'secure')",
            name="ck_attack_graph_nodes_status",
        ),
        sa.CheckConstraint(
            "severity IN ('low', 'medium', 'high', 'critical')",
            name="ck_attack_graph_nodes_severity",
        ),
    )
    op.create_index("ix_attack_graph_nodes_user_id", "attack_graph_nodes", ["user_id"])
    op.create_table(
        "attack_graph_edges",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("source_node_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("target_node_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("label", sa.String(length=240), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["auth.users.id"], name="fk_attack_graph_edges_user_id", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["source_node_id"],
            ["attack_graph_nodes.id"],
            name="fk_attack_graph_edges_source",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["target_node_id"],
            ["attack_graph_nodes.id"],
            name="fk_attack_graph_edges_target",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'potential', 'blocked')",
            name="ck_attack_graph_edges_status",
        ),
    )
    op.create_index("ix_attack_graph_edges_user_id", "attack_graph_edges", ["user_id"])
    op.create_index("ix_attack_graph_edges_source", "attack_graph_edges", ["source_node_id"])
    op.create_index("ix_attack_graph_edges_target", "attack_graph_edges", ["target_node_id"])
    for table in ("attack_graph_nodes", "attack_graph_edges"):
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
    for table in ("attack_graph_edges", "attack_graph_nodes"):
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
    op.drop_index("ix_attack_graph_edges_target", table_name="attack_graph_edges")
    op.drop_index("ix_attack_graph_edges_source", table_name="attack_graph_edges")
    op.drop_index("ix_attack_graph_edges_user_id", table_name="attack_graph_edges")
    op.drop_table("attack_graph_edges")
    op.drop_index("ix_attack_graph_nodes_user_id", table_name="attack_graph_nodes")
    op.drop_table("attack_graph_nodes")
