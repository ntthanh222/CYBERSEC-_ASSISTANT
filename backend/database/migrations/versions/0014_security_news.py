"""phase 3 codex: security news

Revision ID: 0014
Revises: 0013
"""

import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "security_news_articles",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("ai_summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("url", sa.String(length=1000), nullable=False),
        sa.Column("source", sa.String(length=200), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("category", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("related_cves", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("bookmarked", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("read", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["auth.users.id"],
            name="fk_security_news_user_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("user_id", "url", name="uq_security_news_owner_url"),
    )
    op.create_index("ix_security_news_user_id", "security_news_articles", ["user_id"])
    op.create_index(
        "ix_security_news_published_at", "security_news_articles", [sa.text("published_at DESC")]
    )
    op.execute(
        sa.text("GRANT SELECT, INSERT, UPDATE, DELETE ON security_news_articles TO authenticated")
    )
    op.execute(sa.text("ALTER TABLE security_news_articles ENABLE ROW LEVEL SECURITY"))
    op.execute(sa.text("ALTER TABLE security_news_articles FORCE ROW LEVEL SECURITY"))
    op.execute(
        sa.text(
            "CREATE POLICY security_news_owner_only ON security_news_articles "
            "FOR ALL USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id)"
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DROP POLICY IF EXISTS security_news_owner_only ON security_news_articles"))
    op.execute(sa.text("ALTER TABLE security_news_articles NO FORCE ROW LEVEL SECURITY"))
    op.execute(sa.text("ALTER TABLE security_news_articles DISABLE ROW LEVEL SECURITY"))
    op.execute(
        sa.text(
            "REVOKE SELECT, INSERT, UPDATE, DELETE ON security_news_articles FROM authenticated"
        )
    )
    op.drop_index("ix_security_news_published_at", table_name="security_news_articles")
    op.drop_index("ix_security_news_user_id", table_name="security_news_articles")
    op.drop_table("security_news_articles")
