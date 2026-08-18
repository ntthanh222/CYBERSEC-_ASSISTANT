"""Live-Postgres integration tests for Phase 2.5B RLS enforcement.

Skipped unless ``LIVE_POSTGRES_DSN`` is set (a Postgres already migrated to
revision 0004, reachable from this process) - these need a real database,
not SQLite, so they cannot run as part of the default unit-test suite.

Each test shells out to its corresponding ``backend/scripts/verify_*``
script via ``subprocess`` rather than importing it directly. That is
deliberate, not a shortcut: ``backend.config.settings.get_settings()`` and
``backend.database.session.get_engine()`` are process-wide
``functools.lru_cache`` singletons, and this test file's own
``conftest.py`` already imports ``backend.main.app`` (with SQLite-oriented
defaults) the moment pytest collects *any* file in this directory - by the
time a test body could set ``DATABASE_URL``/``SUPABASE_URL`` and clear
those caches, the app/engine already exist with the wrong configuration.
A subprocess is a fresh Python process with no such cache to fight.

Run in isolation, e.g.::

    LIVE_POSTGRES_DSN="postgresql+psycopg://user:pass@host:port/db" \\
        pytest -q backend/tests/test_live_postgres_integration.py
"""
import os
import subprocess
import sys

import pytest

LIVE_DSN = os.environ.get("LIVE_POSTGRES_DSN")

pytestmark = pytest.mark.skipif(
    not LIVE_DSN,
    reason="LIVE_POSTGRES_DSN not set - these tests need a real Postgres migrated to 0004",
)


def _run_verifier(module: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", module, LIVE_DSN],
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_pool_isolation_no_claim_leakage_across_pooled_connections():
    """request.jwt.claims set via SET LOCAL never survives to a later
    request that reuses the same physical (pool_size=1) connection."""
    result = _run_verifier("backend.scripts.verify_pool_isolation")
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.count("PASS:") == 3, result.stdout


def test_two_user_rls_isolation_over_the_real_http_request_path():
    """JWT -> FastAPI (get_current_user) -> SQLAlchemy (get_rls_db) ->
    PostgreSQL RLS, exercised over real HTTP requests with real signed
    tokens - nothing in this codebase's own layers is mocked."""
    result = _run_verifier("backend.scripts.verify_http_rls_isolation")
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.count("PASS:") == 8, result.stdout


def test_raw_sql_rls_isolation_matches_the_production_role_mechanism():
    """The same two-user isolation, exercised directly at the SQL level
    with SET LOCAL ROLE authenticated - the exact mechanism
    backend/database/session.py:get_rls_db uses, independent of FastAPI."""
    result = _run_verifier("backend.scripts.verify_rls_isolation")
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.count("PASS:") == 6, result.stdout
