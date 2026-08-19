"""PostgreSQL migration round-trip test for 0027 (sla_policies).

Skipped unless MIGRATION_TEST_DATABASE_URL is set, mirroring
test_migration_0004_safety_postgres.py's approach: drives real Alembic
against a disposable PostgreSQL database rather than mocking anything, since
this migration's data-migration seed and RLS policies are exactly the kind
of thing that only means something against a real Postgres instance (SQLite,
used by the rest of the unit suite via Base.metadata.create_all, has no RLS
concept at all - see backend/tests/conftest.py's db_url fixture docstring).
"""
from __future__ import annotations

import os
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

pytestmark = pytest.mark.skipif(
    not ADMIN_DSN,
    reason="MIGRATION_TEST_DATABASE_URL not set - PostgreSQL migration tests skipped",
)


def _quote_ident(name: str) -> str:
    return f'"{name}"'


def _db_url(name: str) -> str:
    url = make_url(ADMIN_DSN)
    return url.set(database=name).render_as_string(hide_password=False)


@pytest.fixture()
def migrated_db():
    db_name = f"codex_0027_{uuid.uuid4().hex[:12]}"
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
        timeout=120,
    )


def _scalar(db_url: str, sql: str, params: dict | None = None):
    engine = create_engine(db_url)
    try:
        with engine.connect() as conn:
            return conn.execute(text(sql), params or {}).scalar_one()
    finally:
        engine.dispose()


def _revision(db_url: str) -> str:
    return _scalar(db_url, "SELECT version_num FROM alembic_version")


def test_clean_database_upgrades_to_0027_and_seeds_defaults(migrated_db):
    result = _run_alembic(migrated_db, "upgrade", "head")
    assert result.returncode == 0, result.stdout + result.stderr
    assert _revision(migrated_db) == "0027"

    rows = _scalar(
        migrated_db,
        "SELECT COUNT(*) FROM sla_policies WHERE project_id IS NULL",
    )
    assert rows == 3  # critical, high, medium - not low

    for severity, hours in (("critical", 24), ("high", 72), ("medium", 168)):
        got = _scalar(
            migrated_db,
            "SELECT hours_to_deadline FROM sla_policies "
            "WHERE project_id IS NULL AND severity = :severity",
            {"severity": severity},
        )
        assert got == hours

    low_rows = _scalar(
        migrated_db,
        "SELECT COUNT(*) FROM sla_policies WHERE project_id IS NULL AND severity = 'low'",
    )
    assert low_rows == 0

    assert (
        _scalar(
            migrated_db,
            "SELECT COUNT(*) FROM pg_class WHERE relname = 'sla_policies' "
            "AND relrowsecurity",
        )
        == 1
    )
    assert (
        _scalar(
            migrated_db,
            "SELECT COUNT(*) FROM pg_policies WHERE tablename = 'sla_policies'",
        )
        == 4
    )
    # Two global-default rows for the same severity must be rejected by the
    # partial unique index - see sla_policy.py's docstring.
    with pytest.raises(Exception):
        engine = create_engine(migrated_db)
        try:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "INSERT INTO sla_policies (id, project_id, severity, hours_to_deadline) "
                        "VALUES (gen_random_uuid(), NULL, 'high', 999)"
                    )
                )
        finally:
            engine.dispose()


def test_downgrade_from_0027_removes_the_table(migrated_db):
    assert _run_alembic(migrated_db, "upgrade", "head").returncode == 0

    result = _run_alembic(migrated_db, "downgrade", "0026")
    assert result.returncode == 0, result.stdout + result.stderr
    assert _revision(migrated_db) == "0026"

    table_exists = _scalar(
        migrated_db,
        "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_name = 'sla_policies')",
    )
    assert table_exists is False


def test_clean_database_can_downgrade_and_upgrade_0027_again(migrated_db):
    assert _run_alembic(migrated_db, "upgrade", "head").returncode == 0

    downgrade = _run_alembic(migrated_db, "downgrade", "0026")
    assert downgrade.returncode == 0, downgrade.stdout + downgrade.stderr
    assert _revision(migrated_db) == "0026"

    upgrade_again = _run_alembic(migrated_db, "upgrade", "0027")
    assert upgrade_again.returncode == 0, upgrade_again.stdout + upgrade_again.stderr
    assert _revision(migrated_db) == "0027"

    # Re-upgrading must not duplicate the seed rows.
    rows = _scalar(migrated_db, "SELECT COUNT(*) FROM sla_policies WHERE project_id IS NULL")
    assert rows == 3
