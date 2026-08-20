"""PostgreSQL migration round-trip test for 0028 (cve_assessments).

Skipped unless MIGRATION_TEST_DATABASE_URL is set - mirrors
test_migration_0027_sla_policies.py's approach exactly (real Alembic against
a disposable PostgreSQL database, since RLS has no SQLite equivalent).
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
    db_name = f"codex_0028_{uuid.uuid4().hex[:12]}"
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


def test_clean_database_upgrades_to_0028(migrated_db):
    result = _run_alembic(migrated_db, "upgrade", "head")
    assert result.returncode == 0, result.stdout + result.stderr
    assert _revision(migrated_db) == "0028"

    assert (
        _scalar(
            migrated_db,
            "SELECT COUNT(*) FROM pg_class WHERE relname = 'cve_assessments' "
            "AND relrowsecurity",
        )
        == 1
    )
    assert (
        _scalar(
            migrated_db,
            "SELECT COUNT(*) FROM pg_policies WHERE tablename = 'cve_assessments'",
        )
        == 1
    )

    # A bad priority label must be rejected by the CHECK constraint (no FK
    # setup needed - the CHECK fires before the FK constraint is even
    # evaluated for an obviously-bogus row).
    with pytest.raises(Exception):
        engine = create_engine(migrated_db)
        try:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "INSERT INTO cve_assessments "
                        "(id, project_id, cve_id, is_kev, priority, score, rationale) "
                        "VALUES (gen_random_uuid(), gen_random_uuid(), 'CVE-2021-44228', "
                        "false, 'not_a_real_label', 5.0, '{}'::jsonb)"
                    )
                )
        finally:
            engine.dispose()


def test_downgrade_from_0028_removes_the_table(migrated_db):
    assert _run_alembic(migrated_db, "upgrade", "head").returncode == 0

    result = _run_alembic(migrated_db, "downgrade", "0027")
    assert result.returncode == 0, result.stdout + result.stderr
    assert _revision(migrated_db) == "0027"

    table_exists = _scalar(
        migrated_db,
        "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_name = 'cve_assessments')",
    )
    assert table_exists is False


def test_clean_database_can_downgrade_and_upgrade_0028_again(migrated_db):
    assert _run_alembic(migrated_db, "upgrade", "head").returncode == 0

    downgrade = _run_alembic(migrated_db, "downgrade", "0027")
    assert downgrade.returncode == 0, downgrade.stdout + downgrade.stderr
    assert _revision(migrated_db) == "0027"

    upgrade_again = _run_alembic(migrated_db, "upgrade", "0028")
    assert upgrade_again.returncode == 0, upgrade_again.stdout + upgrade_again.stderr
    assert _revision(migrated_db) == "0028"
