"""Make security news a shared feed instead of a per-user private list.

The News page is meant to be a read-first feed every user sees (crawled
CISA/NVD articles + anything an admin adds), but the original RLS policy
(``security_news_owner_only``, ``auth.uid() = user_id``) and the app-level
``user_id`` filtering scoped every article to whoever created it. In
practice that meant a normal user's feed was always empty - the admin who
ran the crawler was the only account that could ever see the results.

This migration makes ``security_news_articles`` readable by any
authenticated caller. Write authorization (only admin/super_admin may
create/delete articles) is enforced app-side via
``backend.core.authorization.require_admin`` - same pattern already used by
every other admin-only route in this codebase - not via a DB role claim,
since the JWT's RLS role claim is always ``authenticated`` and is never
trusted for app-role decisions (see backend/core/authorization.py).

Revision ID: 0022
Revises: 0021_mitre_incident_reuse
"""

import sqlalchemy as sa
from alembic import op

revision = "0022"
down_revision = "0021_mitre_incident_reuse"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("DROP POLICY IF EXISTS security_news_owner_only ON security_news_articles"))
    op.drop_constraint("uq_security_news_owner_url", "security_news_articles", type_="unique")
    op.create_unique_constraint(
        "uq_security_news_url", "security_news_articles", ["url"]
    )
    op.execute(
        sa.text(
            "CREATE POLICY security_news_read_all ON security_news_articles "
            "FOR SELECT USING (true)"
        )
    )
    op.execute(
        sa.text(
            "CREATE POLICY security_news_insert_authenticated ON security_news_articles "
            "FOR INSERT WITH CHECK (true)"
        )
    )
    op.execute(
        sa.text(
            "CREATE POLICY security_news_update_authenticated ON security_news_articles "
            "FOR UPDATE USING (true) WITH CHECK (true)"
        )
    )
    op.execute(
        sa.text(
            "CREATE POLICY security_news_delete_authenticated ON security_news_articles "
            "FOR DELETE USING (true)"
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DROP POLICY IF EXISTS security_news_delete_authenticated ON security_news_articles"))
    op.execute(sa.text("DROP POLICY IF EXISTS security_news_update_authenticated ON security_news_articles"))
    op.execute(sa.text("DROP POLICY IF EXISTS security_news_insert_authenticated ON security_news_articles"))
    op.execute(sa.text("DROP POLICY IF EXISTS security_news_read_all ON security_news_articles"))
    op.drop_constraint("uq_security_news_url", "security_news_articles", type_="unique")
    op.create_unique_constraint(
        "uq_security_news_owner_url", "security_news_articles", ["user_id", "url"]
    )
    op.execute(
        sa.text(
            "CREATE POLICY security_news_owner_only ON security_news_articles "
            "FOR ALL USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id)"
        )
    )
