"""baseline schema bootstrap table

Revision ID: 0001
Revises:
Create Date: 2026-07-29
"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "schema_bootstrap",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "applied_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("schema_bootstrap")
