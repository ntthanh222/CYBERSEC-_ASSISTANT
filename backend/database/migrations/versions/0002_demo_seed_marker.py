"""demo seed marker table (extensible seed framework, no fake business data)

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-29
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "demo_seed_marker",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("seed_key", sa.String(length=128), nullable=False, unique=True),
        sa.Column(
            "seeded_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("demo_seed_marker")
