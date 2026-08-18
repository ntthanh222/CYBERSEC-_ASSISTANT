"""phase 2.5b: user ownership columns + row level security

Revision ID: 0004
Revises: 0003

Written fresh for Phase 2.5B - unrelated to and does not restore the
quarantined ``0004_auth_users`` migration (tag
``quarantine/auth-rbac-phase3-cd5bda2``), which created its own ``users``
table and application-issued JWTs. This migration instead assumes Supabase
Auth as the identity source (``auth.users`` / ``auth.uid()``) and never
creates a competing user table on a real Supabase target.

Local Docker Postgres has no Supabase ``auth`` schema, so this migration
bootstraps a minimal, Supabase-shaped emulation (``auth.users``,
``auth.uid()``, the ``authenticated``/``anon`` roles) *only when that schema
does not already exist* - i.e. only on local/test targets. On a real
Supabase project the ``auth`` schema is always already present, so that
block is a no-op there and nothing Supabase-managed is touched.

No anonymous data is preserved or silently rewritten: if legacy rows exist
before ownership columns are added, the migration hard-fails before any DDL
runs. Operators must resolve ownership explicitly and retry.
"""
import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

_LOCAL_AUTH_SHIM = """
DO $migration_0004$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'auth') THEN
        CREATE SCHEMA auth;

        CREATE TABLE auth.users (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            email text UNIQUE,
            created_at timestamptz NOT NULL DEFAULT now()
        );

        CREATE FUNCTION auth.uid() RETURNS uuid
            LANGUAGE sql STABLE
            AS $auth_uid$
                SELECT NULLIF(
                    current_setting('request.jwt.claims', true)::json ->> 'sub', ''
                )::uuid
            $auth_uid$;

        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
            CREATE ROLE authenticated NOLOGIN;
        END IF;
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
            CREATE ROLE anon NOLOGIN;
        END IF;

        GRANT authenticated TO CURRENT_USER;
        GRANT USAGE ON SCHEMA public TO authenticated;
        GRANT USAGE ON SCHEMA auth TO authenticated;
    END IF;
END
$migration_0004$;
"""

_LOCAL_AUTH_SHIM_DOWN = """
DO $migration_0004_down$
BEGIN
    -- Only ever drop the shim this migration itself created. A real
    -- Supabase `auth` schema is never touched by this migration (it never
    -- ran the block above there), so this mirrors that: only tear down a
    -- shim if the seed marker table we control says we made it.
    IF EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'auth')
        AND EXISTS (
            SELECT 1 FROM information_schema.routines
            WHERE routine_schema = 'auth' AND routine_name = 'uid'
        )
        AND EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'auth' AND table_name = 'users' AND column_name = 'email'
        )
        AND NOT EXISTS (
            -- A real Supabase auth.users has many more columns than our shim;
            -- this count check keeps the downgrade from ever touching a real
            -- Supabase project even if someone runs it there by mistake.
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'auth' AND table_name = 'users'
            GROUP BY table_name HAVING count(*) > 3
        )
    THEN
        DROP FUNCTION IF EXISTS auth.uid();
        DROP TABLE IF EXISTS auth.users;
        DROP SCHEMA IF EXISTS auth;
    END IF;
END
$migration_0004_down$;
"""


class LegacyRowsWithoutOwnerError(RuntimeError):
    """Raised when 0004 would otherwise need to infer or destroy ownership."""


_LEGACY_COUNT_QUERIES = {
    "conversations": sa.text("SELECT COUNT(*) FROM conversations"),
    "messages": sa.text("SELECT COUNT(*) FROM messages"),
    "security_scan_history": sa.text("SELECT COUNT(*) FROM security_scan_history"),
}


def _legacy_row_counts() -> dict[str, int]:
    bind = op.get_bind()
    return {
        table: int(bind.execute(query).scalar_one())
        for table, query in _LEGACY_COUNT_QUERIES.items()
    }


def _block_if_legacy_rows_exist() -> None:
    counts = _legacy_row_counts()
    if any(counts.values()):
        raise LegacyRowsWithoutOwnerError(
            "Migration 0004 blocked: legacy rows without an authenticated owner exist. "
            f"conversations={counts['conversations']}, messages={counts['messages']}, "
            f"security_scan_history={counts['security_scan_history']}. "
            "No data was modified. Resolve ownership manually before retrying."
        )


def upgrade() -> None:
    # Must run before _any_ DDL, grants, or policy changes. Legacy rows from
    # revision 0003 have no authenticated owner, and this migration must
    # neither delete them nor invent one.
    _block_if_legacy_rows_exist()

    op.execute(_LOCAL_AUTH_SHIM)

    op.add_column(
        "conversations",
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
    )
    op.create_foreign_key(
        "fk_conversations_user_id",
        "conversations",
        "users",
        ["user_id"],
        ["id"],
        source_schema=None,
        referent_schema="auth",
        ondelete="CASCADE",
    )
    op.create_index("ix_conversations_user_id", "conversations", ["user_id"])

    op.add_column(
        "security_scan_history",
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
    )
    op.create_foreign_key(
        "fk_security_scan_history_user_id",
        "security_scan_history",
        "users",
        ["user_id"],
        ["id"],
        source_schema=None,
        referent_schema="auth",
        ondelete="CASCADE",
    )
    op.create_index("ix_security_scan_history_user_id", "security_scan_history", ["user_id"])

    # Table-level DML for the RLS-scoped role. Policies below narrow this to
    # each caller's own rows; without this GRANT the role could see nothing
    # even for its own data.
    op.execute(sa.text("GRANT SELECT, INSERT, UPDATE, DELETE ON conversations TO authenticated"))
    op.execute(sa.text("GRANT SELECT, INSERT, UPDATE, DELETE ON messages TO authenticated"))
    op.execute(
        sa.text(
            "GRANT SELECT, INSERT, UPDATE, DELETE ON security_scan_history TO authenticated"
        )
    )

    for table in ("conversations", "messages", "security_scan_history"):
        op.execute(
            sa.text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text -- static schema migration string
                f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"
            )
        )
        # FORCE so even the table owner is subject to policy - this
        # application never queries as the owner role for user data (see
        # backend/database/session.py:get_rls_db), but FORCE keeps that true
        # even if a future change accidentally reintroduces an owner-role query.
        op.execute(
            sa.text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text -- static schema migration string
                f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"
            )
        )

    op.execute(
        sa.text(
            "CREATE POLICY conversations_owner_only ON conversations "
            "FOR ALL "
            "USING (auth.uid() = user_id) "
            "WITH CHECK (auth.uid() = user_id)"
        )
    )
    op.execute(
        sa.text(
            "CREATE POLICY security_scan_history_owner_only ON security_scan_history "
            "FOR ALL "
            "USING (auth.uid() = user_id) "
            "WITH CHECK (auth.uid() = user_id)"
        )
    )
    # messages has no user_id of its own - ownership is derived through the
    # parent conversation, exactly as required: a caller may never read,
    # write, or delete a message row without also owning its conversation.
    op.execute(
        sa.text(
            "CREATE POLICY messages_via_owning_conversation ON messages "
            "FOR ALL "
            "USING (EXISTS ("
            "  SELECT 1 FROM conversations c "
            "  WHERE c.id = messages.conversation_id AND c.user_id = auth.uid()"
            ")) "
            "WITH CHECK (EXISTS ("
            "  SELECT 1 FROM conversations c "
            "  WHERE c.id = messages.conversation_id AND c.user_id = auth.uid()"
            "))"
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DROP POLICY IF EXISTS messages_via_owning_conversation ON messages"))
    op.execute(
        sa.text(
            "DROP POLICY IF EXISTS security_scan_history_owner_only ON security_scan_history"
        )
    )
    op.execute(sa.text("DROP POLICY IF EXISTS conversations_owner_only ON conversations"))

    for table in ("conversations", "messages", "security_scan_history"):
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
        sa.text("REVOKE SELECT, INSERT, UPDATE, DELETE ON conversations FROM authenticated")
    )
    op.execute(sa.text("REVOKE SELECT, INSERT, UPDATE, DELETE ON messages FROM authenticated"))
    op.execute(
        sa.text(
            "REVOKE SELECT, INSERT, UPDATE, DELETE ON security_scan_history FROM authenticated"
        )
    )

    op.drop_index("ix_security_scan_history_user_id", table_name="security_scan_history")
    op.drop_constraint(
        "fk_security_scan_history_user_id", "security_scan_history", type_="foreignkey"
    )
    op.drop_column("security_scan_history", "user_id")

    op.drop_index("ix_conversations_user_id", table_name="conversations")
    op.drop_constraint("fk_conversations_user_id", "conversations", type_="foreignkey")
    op.drop_column("conversations", "user_id")

    op.execute(_LOCAL_AUTH_SHIM_DOWN)
