import os
import sys
import uuid
from pathlib import Path

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:3000,http://testserver")
# Insulates the suite from a real .env file sitting in the repo root (e.g.
# for live Supabase verification) - APP_ENV=staging there would otherwise
# leak in via pydantic-settings' env_file loading and flip staging-only
# behavior (docs disabled, TLS/explicit-DATABASE_URL required) for every
# test, not just the live scripts that are supposed to see it.
os.environ.setdefault("APP_ENV", "local")
# Same rationale, generalized: pydantic-settings reads .env directly from
# disk (see backend/config/settings.py's env_file config) - an environment
# variable set here (even to "") shadows that file for the whole test
# session, while merely being *absent* would not (only setdefault, not
# delenv, achieves this - see test_embedding_providers.py's
# test_registry_falls_back_to_local_if_gemini_opted_in_without_a_key for the
# bug this pattern was written to prevent). Without this, a real secret
# placed in the repo-root .env for live/Docker verification would silently
# make unit tests attempt real external network calls instead of staying
# hermetic. Individual tests can still monkeypatch.setenv(...) their own
# value to explicitly opt into testing "configured" behavior.
os.environ.setdefault("GEMINI_API_KEY", "")
os.environ.setdefault("VIRUSTOTAL_API_KEY", "")
os.environ.setdefault("NIST_NVD_API_KEY", "")

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.core.auth import AuthenticatedUser, get_current_user
from backend.database.base import Base
from backend.database import models  # noqa: F401 - registers tables on Base.metadata
from backend.database.session import get_db, get_rls_db
from backend.main import app

#: Stable per-test-process user identities. Real ownership/RLS enforcement is
#: exercised against live Postgres in test_rls_isolation.py; these unit tests
#: run on SQLite and only need a consistent `user_id` to plumb through the
#: service/repository layers `get_current_user` normally supplies.
TEST_USER_A = AuthenticatedUser(id=uuid.uuid4(), role="authenticated", claims={})
TEST_USER_B = AuthenticatedUser(id=uuid.uuid4(), role="authenticated", claims={})


@pytest.fixture()
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def db_url(tmp_path) -> str:
    """A fresh SQLite database with the full ORM schema applied.

    The schema is created with a *synchronous* engine so it is ready before the
    TestClient starts its own event loop; the application then talks to the
    same file through aiosqlite. Every test gets its own file, so tests never
    share state.

    SQLite is used rather than a live PostgreSQL because unit tests must not
    depend on a running service. The migration itself is verified for real
    against PostgreSQL by the acceptance script.
    """
    path = tmp_path / "phase2-test.db"
    sync_engine = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(sync_engine)
    sync_engine.dispose()
    return f"sqlite+aiosqlite:///{path}"


@pytest.fixture()
def db_sessionmaker(db_url):
    engine = create_async_engine(db_url)
    yield async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)


def _make_override_get_db(db_sessionmaker):
    async def _override_get_db():
        session = db_sessionmaker()
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

    return _override_get_db


def _make_override_get_rls_db(override_get_db):
    """SQLite stand-in for ``get_rls_db``.

    SQLite has no roles or ``request.jwt.claims`` GUC, so the Postgres-only
    ``SET LOCAL`` statements the real dependency issues would simply error
    here. Unit tests instead rely on the explicit ``user_id`` filtering each
    repository/service performs; real RLS enforcement is verified against
    live Postgres in ``test_rls_isolation.py``.
    """

    async def _override_get_rls_db():
        async for session in override_get_db():
            yield session

    return _override_get_rls_db


@pytest.fixture()
def api_client(db_sessionmaker, monkeypatch) -> TestClient:
    """TestClient wired to the SQLite test database, with rate limiting inert.

    ``get_redis`` is forced to ``None`` so the limiter takes its documented
    "no Redis configured" path instead of spending its connect timeout on an
    unreachable host in every test. Rate-limiting behaviour itself is covered
    by dedicated tests with a fake Redis client.

    Authenticated as ``TEST_USER_A`` by default - most endpoint tests care
    about business behaviour, not token verification itself (that is
    ``test_auth.py``'s job). Use ``unauthenticated_client`` or
    ``as_user_b`` below for the auth-specific cases.
    """
    monkeypatch.setattr("backend.core.rate_limit.get_redis", lambda: None)

    override_get_db = _make_override_get_db(db_sessionmaker)
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_rls_db] = _make_override_get_rls_db(override_get_db)
    app.dependency_overrides[get_current_user] = lambda: TEST_USER_A
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_rls_db, None)
        app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture()
def unauthenticated_client(db_sessionmaker, monkeypatch) -> TestClient:
    """Same wiring as ``api_client`` but with real Bearer-token verification.

    Used for 401 behaviour: no header, malformed header, or a token that
    fails verification for real (no ``get_current_user`` override).
    """
    monkeypatch.setattr("backend.core.rate_limit.get_redis", lambda: None)

    override_get_db = _make_override_get_db(db_sessionmaker)
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_rls_db] = _make_override_get_rls_db(override_get_db)
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_rls_db, None)


@pytest.fixture()
def switch_user(api_client):
    """Returns a callable that re-points ``api_client``'s identity mid-test.

    A fixture that flips the override itself would run its setup before the
    test body executes at all - too early to capture "do this as user A,
    then switch and do that as user B" within one test. Call the returned
    function at the exact point the test needs to change identity.
    """

    def _switch(user: AuthenticatedUser) -> None:
        app.dependency_overrides[get_current_user] = lambda: user

    yield _switch
    app.dependency_overrides[get_current_user] = lambda: TEST_USER_A
