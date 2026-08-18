"""phase 2 assistant conversations and security scan history

Revision ID: 0003
Revises: 0002
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "conversations",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("actor", sa.String(length=128), nullable=True),
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
    )
    op.create_index(
        "ix_conversations_actor_updated_at",
        "conversations",
        ["actor", sa.text("updated_at DESC")],
    )

    op.create_table(
        "messages",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("conversation_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        # Content is redacted by the application before it is written here.
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=True),
        sa.Column("intent", sa.String(length=64), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name="fk_messages_conversation_id",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "role IN ('user', 'assistant', 'system')",
            name="ck_messages_role",
        ),
    )
    op.create_index(
        "ix_messages_conversation_id_created_at",
        "messages",
        ["conversation_id", "created_at"],
    )

    op.create_table(
        "security_scan_history",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("scan_type", sa.String(length=32), nullable=False),
        sa.Column("target", sa.String(length=2048), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("risk_score", sa.Integer(), nullable=True),
        sa.Column("severity", sa.String(length=16), nullable=True),
        sa.Column("summary", sa.String(length=500), nullable=False),
        sa.Column("details", postgresql.JSONB(), nullable=True),
        sa.Column("actor", sa.String(length=128), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        # Password checks are deliberately absent from scan_type: the password
        # checker is stateless and writes no row at all.
        sa.CheckConstraint(
            "scan_type IN ('url_scan', 'cve_lookup')",
            name="ck_security_scan_history_scan_type",
        ),
        sa.CheckConstraint(
            "status IN ('completed', 'failed')",
            name="ck_security_scan_history_status",
        ),
        sa.CheckConstraint(
            "risk_score IS NULL OR (risk_score >= 0 AND risk_score <= 100)",
            name="ck_security_scan_history_risk_score_range",
        ),
        sa.CheckConstraint(
            "severity IS NULL OR severity IN ('low', 'medium', 'high', 'critical')",
            name="ck_security_scan_history_severity",
        ),
    )
    op.create_index(
        "ix_security_scan_history_created_at",
        "security_scan_history",
        [sa.text("created_at DESC")],
    )
    op.create_index(
        "ix_security_scan_history_scan_type",
        "security_scan_history",
        ["scan_type"],
    )
    op.create_index(
        "ix_security_scan_history_status",
        "security_scan_history",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index("ix_security_scan_history_status", table_name="security_scan_history")
    op.drop_index("ix_security_scan_history_scan_type", table_name="security_scan_history")
    op.drop_index("ix_security_scan_history_created_at", table_name="security_scan_history")
    op.drop_table("security_scan_history")

    op.drop_index("ix_messages_conversation_id_created_at", table_name="messages")
    op.drop_table("messages")

    op.drop_index("ix_conversations_actor_updated_at", table_name="conversations")
    op.drop_table("conversations")
