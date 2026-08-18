"""PostgreSQL regression tests for migration 0004's non-destructive guard.

Skipped unless MIGRATION_TEST_DATABASE_URL is set. These intentionally drive
Alembic in subprocesses against disposable PostgreSQL databases: the migration
transaction, revision table and schema state are all real, not mocked.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


ADMIN_DSN = os.environ.get("MIGRATION_TEST_DATABASE_URL")
REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
MIGRATION_FILE = (
    BACKEND_DIR / "database" / "migrations" / "versions" / "0004_auth_ownership_and_rls.py"
)

pytestmark = pytest.mark.skipif(
    not ADMIN_DSN,
    reason="MIGRATION_TEST_DATABASE_URL not set - PostgreSQL migration safety tests skipped",
)


def _quote_ident(name: str) -> str:
    if not re.fullmatch(r"[a-z0-9_]+", name):
        raise ValueError(f"unsafe database name: {name!r}")
    return f'"{name}"'


def _db_url(name: str) -> str:
    url = make_url(ADMIN_DSN)
    return url.set(database=name).render_as_string(hide_password=False)


@pytest.fixture()
def migrated_db():
    db_name = f"codex_0004_{uuid.uuid4().hex[:12]}"
    admin_engine = create_engine(ADMIN_DSN, isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as conn:
        conn.execute(text(f"CREATE DATABASE {_quote_ident(db_name)}"))
    admin_engine.dispose()
    try:
        yield _db_url(db_name)
    finally:
        cleanup_engine = create_engine(ADMIN_DSN, isolation_level="AUTOCOMMIT")
        with cleanup_engine.connect() as conn:
            conn.execute(text(f"DROP DATABASE IF EXISTS {_quote_ident(db_name)} WITH (FORCE)"))
        cleanup_engine.dispose()


def _run_alembic(db_url: str, *args: str) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env.update(
        {
            "APP_ENV": "local",
            "DATABASE_URL": db_url,
            "DATABASE_MIGRATION_URL": db_url,
            "PYTHONPATH": str(REPO_ROOT),
            "PYTHONDONTWRITEBYTECODE": "1",
        }
    )
    return subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", *args],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


def _upgrade(db_url: str, revision: str) -> subprocess.CompletedProcess:
    return _run_alembic(db_url, "upgrade", revision)


def _downgrade(db_url: str, revision: str) -> subprocess.CompletedProcess:
    return _run_alembic(db_url, "downgrade", revision)


def _scalar(db_url: str, sql: str, params: dict | None = None):
    engine = create_engine(db_url)
    try:
        with engine.connect() as conn:
            return conn.execute(text(sql), params or {}).scalar_one()
    finally:
        engine.dispose()


def _execute(db_url: str, sql: str, params: dict | None = None) -> None:
    engine = create_engine(db_url)
    try:
        with engine.begin() as conn:
            conn.execute(text(sql), params or {})
    finally:
        engine.dispose()


def _revision(db_url: str) -> str:
    return _scalar(db_url, "SELECT version_num FROM alembic_version")


def _table_count(db_url: str, table: str) -> int:
    return int(_scalar(db_url, f"SELECT COUNT(*) FROM {table}"))


def _has_column(db_url: str, table: str, column: str) -> bool:
    return bool(
        _scalar(
            db_url,
            """
            SELECT EXISTS (
              SELECT 1 FROM information_schema.columns
              WHERE table_schema = 'public' AND table_name = :table AND column_name = :column
            )
            """,
            {"table": table, "column": column},
        )
    )


def _assert_blocked(result: subprocess.CompletedProcess, **counts: int) -> None:
    assert result.returncode != 0, result.stdout + result.stderr
    output = result.stdout + result.stderr
    assert "Migration 0004 blocked: legacy rows without an authenticated owner exist." in output
    assert "No data was modified. Resolve ownership manually before retrying." in output
    for table in ("conversations", "messages", "security_scan_history"):
        assert f"{table}={counts.get(table, 0)}" in output


def _seed_conversation(db_url: str) -> str:
    conv_id = str(uuid.uuid4())
    _execute(
        db_url,
        "INSERT INTO conversations (id, title, actor) VALUES (:id, 'legacy conversation', 'test')",
        {"id": conv_id},
    )
    return conv_id


def _seed_message(db_url: str) -> None:
    conv_id = _seed_conversation(db_url)
    _execute(
        db_url,
        """
        INSERT INTO messages (id, conversation_id, role, content)
        VALUES (:id, :conversation_id, 'user', 'legacy message')
        """,
        {"id": str(uuid.uuid4()), "conversation_id": conv_id},
    )


def _seed_scan(db_url: str) -> None:
    _execute(
        db_url,
        """
        INSERT INTO security_scan_history (id, scan_type, target, status, summary)
        VALUES (:id, 'url_scan', 'https://example.com', 'completed', 'legacy scan')
        """,
        {"id": str(uuid.uuid4())},
    )


def test_clean_database_upgrades_to_0004_with_rls_and_constraints(migrated_db):
    result = _upgrade(migrated_db, "head")
    assert result.returncode == 0, result.stdout + result.stderr
    assert _revision(migrated_db) == "0004"

    assert _scalar(
        migrated_db,
        """
        SELECT is_nullable FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'conversations' AND column_name = 'user_id'
        """,
    ) == "NO"
    assert _scalar(
        migrated_db,
        """
        SELECT is_nullable FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'security_scan_history'
          AND column_name = 'user_id'
        """,
    ) == "NO"
    assert _scalar(
        migrated_db,
        "SELECT COUNT(*) FROM pg_constraint WHERE conname IN "
        "('fk_conversations_user_id', 'fk_security_scan_history_user_id')",
    ) == 2
    assert _scalar(
        migrated_db,
        """
        SELECT COUNT(*) FROM pg_class
        WHERE relname IN ('conversations', 'messages', 'security_scan_history')
          AND relrowsecurity AND relforcerowsecurity
        """,
    ) == 3
    assert _scalar(
        migrated_db,
        """
        SELECT COUNT(*) FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename IN ('conversations', 'messages', 'security_scan_history')
        """,
    ) == 3


@pytest.mark.parametrize(
    ("seed", "counts"),
    [
        (_seed_conversation, {"conversations": 1, "messages": 0, "security_scan_history": 0}),
        (_seed_scan, {"conversations": 0, "messages": 0, "security_scan_history": 1}),
        (_seed_message, {"conversations": 1, "messages": 1, "security_scan_history": 0}),
    ],
)
def test_legacy_rows_block_0004_without_partial_schema_changes(migrated_db, seed, counts):
    assert _upgrade(migrated_db, "0003").returncode == 0
    seed(migrated_db)

    result = _upgrade(migrated_db, "0004")

    _assert_blocked(result, **counts)
    assert _revision(migrated_db) == "0003"
    assert not _has_column(migrated_db, "conversations", "user_id")
    assert not _has_column(migrated_db, "security_scan_history", "user_id")
    for table, count in counts.items():
        assert _table_count(migrated_db, table) == count


def test_multi_table_legacy_rows_report_all_counts_and_leave_database_unchanged(migrated_db):
    assert _upgrade(migrated_db, "0003").returncode == 0
    _seed_message(migrated_db)
    _seed_scan(migrated_db)

    result = _upgrade(migrated_db, "0004")

    _assert_blocked(
        result, conversations=1, messages=1, security_scan_history=1
    )
    assert _revision(migrated_db) == "0003"
    assert not _has_column(migrated_db, "conversations", "user_id")
    assert _table_count(migrated_db, "conversations") == 1
    assert _table_count(migrated_db, "messages") == 1
    assert _table_count(migrated_db, "security_scan_history") == 1


def test_downgrade_from_0004_to_0003_preserves_application_rows(migrated_db):
    assert _upgrade(migrated_db, "head").returncode == 0
    user_id = str(uuid.uuid4())
    conv_id = str(uuid.uuid4())
    scan_id = str(uuid.uuid4())
    msg_id = str(uuid.uuid4())
    engine = create_engine(migrated_db)
    try:
        with engine.begin() as conn:
            conn.execute(
                text("INSERT INTO auth.users (id, email) VALUES (:id, 'codex@example.com')"),
                {"id": user_id},
            )
        with engine.begin() as conn:
            conn.execute(text("SET LOCAL ROLE authenticated"))
            conn.execute(
                text("SELECT set_config('request.jwt.claims', :claims, true)"),
                {"claims": f'{{"sub":"{user_id}","role":"authenticated"}}'},
            )
            conn.execute(
                text(
                    "INSERT INTO conversations (id, title, actor, user_id) "
                    "VALUES (:id, 'owned', 'test', :user_id)"
                ),
                {"id": conv_id, "user_id": user_id},
            )
            conn.execute(
                text(
                    "INSERT INTO messages (id, conversation_id, role, content) "
                    "VALUES (:id, :conversation_id, 'user', 'owned message')"
                ),
                {"id": msg_id, "conversation_id": conv_id},
            )
            conn.execute(
                text(
                    "INSERT INTO security_scan_history "
                    "(id, scan_type, target, status, summary, user_id) "
                    "VALUES (:id, 'url_scan', 'https://example.com', "
                    "'completed', 'owned', :user_id)"
                ),
                {"id": scan_id, "user_id": user_id},
            )
    finally:
        engine.dispose()

    result = _downgrade(migrated_db, "0003")
    assert result.returncode == 0, result.stdout + result.stderr
    assert _revision(migrated_db) == "0003"
    assert not _has_column(migrated_db, "conversations", "user_id")
    assert _table_count(migrated_db, "conversations") == 1
    assert _table_count(migrated_db, "messages") == 1
    assert _table_count(migrated_db, "security_scan_history") == 1


def test_clean_database_can_downgrade_and_upgrade_0004_again(migrated_db):
    assert _upgrade(migrated_db, "head").returncode == 0

    downgrade = _downgrade(migrated_db, "0003")
    assert downgrade.returncode == 0, downgrade.stdout + downgrade.stderr
    assert _revision(migrated_db) == "0003"

    upgrade_again = _upgrade(migrated_db, "0004")
    assert upgrade_again.returncode == 0, upgrade_again.stdout + upgrade_again.stderr
    assert _revision(migrated_db) == "0004"


def test_static_migration_contains_no_destructive_sql_or_default_owner_assignment():
    text_body = MIGRATION_FILE.read_text(encoding="utf-8").lower()
    assert "delete from" not in text_body
    assert "truncate" not in text_body
    assert "default_user" not in text_body
    assert "00000000-0000-0000-0000-000000000000" not in text_body
