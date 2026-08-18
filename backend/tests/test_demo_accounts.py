"""Demo Mode account bootstrap: idempotent, opt-in, never a hard dependency."""

import uuid

import pytest

from backend.config.settings import get_settings
from backend.core.password_hash import hash_password
from backend.repositories.rbac import RbacRepository
from backend.services import demo_accounts
from backend.services.demo_accounts import seed_demo_accounts


@pytest.fixture(autouse=True)
def _fake_auth_user_creation(monkeypatch):
    """Same rationale as test_rbac_repository_and_services.py: the real
    auth.users insert is Postgres-only raw SQL, absent from the SQLite test
    schema."""

    async def _fake_create_auth_user(session, *, email):
        return uuid.uuid4()

    monkeypatch.setattr("backend.services.demo_accounts.create_auth_user", _fake_create_auth_user)


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _demo_settings(monkeypatch, **env_overrides):
    """Build a real Settings instance via env vars - Settings fields use
    validation_alias (e.g. DEMO_SEED_ENABLED), so constructing Settings(...)
    directly with Python attribute names silently drops them under
    extra="ignore". Going through the environment, like the app itself does,
    is what every other test in this suite that needs a custom Settings
    already relies on (see test_embedding_providers.py)."""
    env = {
        "APP_ENV": "local",
        "DEMO_SEED_ENABLED": "true",
        "DEMO_USER_PASSWORD": "user-pass-123",
        "DEMO_ANALYST_PASSWORD": "analyst-pass-123",
        "DEMO_SUPERADMIN_PASSWORD": "superadmin-pass-123",
    }
    env.update(env_overrides)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()
    return get_settings()


async def test_seed_creates_all_four_accounts_with_correct_roles(db_sessionmaker, monkeypatch):
    async with db_sessionmaker() as session:
        await seed_demo_accounts(session, settings=_demo_settings(monkeypatch))

    async with db_sessionmaker() as session:
        repo = RbacRepository(session)
        expected = {
            "demo_user": ("user", True),
            "demo_analyst": ("security_analyst", True),
            "demo_superadmin": ("super_admin", True),
            "demo_disabled": ("user", False),
        }
        for username, (role, is_active) in expected.items():
            credential = await repo.get_credential_by_username(username)
            assert credential is not None, f"{username} was not created"
            role_row = await repo.get_role(credential.user_id)
            assert role_row.role == role
            assert role_row.is_active is is_active


async def test_seed_no_longer_creates_demo_admin(db_sessionmaker, monkeypatch):
    async with db_sessionmaker() as session:
        await seed_demo_accounts(session, settings=_demo_settings(monkeypatch))

    async with db_sessionmaker() as session:
        repo = RbacRepository(session)
        assert await repo.get_credential_by_username("demo_admin") is None


async def test_seed_retires_a_preexisting_demo_admin_without_deleting_it(
    db_sessionmaker, monkeypatch
):
    """Simulates upgrading from before the consolidation: a demo_admin row
    already exists (active, role=admin). Seeding must disable it in place -
    not delete it (FK safety) and not touch its role - so it can no longer
    log in."""
    settings = _demo_settings(monkeypatch)
    async with db_sessionmaker() as session:
        repo = RbacRepository(session)
        user_id = await demo_accounts.create_auth_user(
            session, email="demo_admin@local.demo.invalid"
        )
        await repo.set_role(user_id, role="admin")
        await repo.create_local_admin_credential(
            user_id=user_id,
            username="demo_admin",
            password_hash=hash_password("legacy-admin-pass"),
        )
        await session.commit()

    async with db_sessionmaker() as session:
        await seed_demo_accounts(session, settings=settings)

    async with db_sessionmaker() as session:
        repo = RbacRepository(session)
        # Row still exists (not deleted)...
        credential = await repo.get_credential_by_username("demo_admin")
        assert credential is not None
        role_row = await repo.get_role(credential.user_id)
        # ...role untouched (still "admin", proving the RBAC role itself was
        # never removed - only the demo account got disabled)...
        assert role_row.role == "admin"
        # ...but now inactive, so it can no longer sign in.
        assert role_row.is_active is False


async def test_seed_retiring_demo_admin_does_not_touch_a_real_admin(db_sessionmaker, monkeypatch):
    """A hand-created admin account with a different username must never be
    affected by the demo_admin retirement - it's keyed strictly on the
    literal username "demo_admin", not on role."""
    settings = _demo_settings(monkeypatch)
    async with db_sessionmaker() as session:
        repo = RbacRepository(session)
        real_admin_id = await demo_accounts.create_auth_user(
            session, email="real.admin@example.com"
        )
        await repo.set_role(real_admin_id, role="admin")
        await repo.create_local_admin_credential(
            user_id=real_admin_id,
            username="real_admin",
            password_hash=hash_password("real-admin-pass"),
        )
        await session.commit()

    async with db_sessionmaker() as session:
        await seed_demo_accounts(session, settings=settings)

    async with db_sessionmaker() as session:
        repo = RbacRepository(session)
        credential = await repo.get_credential_by_username("real_admin")
        role_row = await repo.get_role(credential.user_id)
        assert role_row.role == "admin"
        assert role_row.is_active is True


async def test_seed_is_idempotent_on_second_run(db_sessionmaker, monkeypatch):
    settings = _demo_settings(monkeypatch)
    async with db_sessionmaker() as session:
        await seed_demo_accounts(session, settings=settings)
    async with db_sessionmaker() as session:
        await seed_demo_accounts(session, settings=settings)

    async with db_sessionmaker() as session:
        repo = RbacRepository(session)
        # No duplicate row: get_credential_by_username still resolves to
        # exactly one account, and re-running never raises (a naive second
        # insert would hit the username UNIQUE constraint).
        credential = await repo.get_credential_by_username("demo_superadmin")
        assert credential is not None


async def test_seed_is_a_no_op_outside_local(db_sessionmaker, monkeypatch):
    # app_env="test" (not "staging"/"production") to exercise the is_local
    # check alone, without also triggering the unrelated staging/production
    # DATABASE_URL/TLS validators Settings enforces for those two envs.
    settings = _demo_settings(monkeypatch, APP_ENV="test")
    async with db_sessionmaker() as session:
        await seed_demo_accounts(session, settings=settings)

    async with db_sessionmaker() as session:
        repo = RbacRepository(session)
        assert await repo.get_credential_by_username("demo_user") is None


async def test_seed_is_a_no_op_when_disabled(db_sessionmaker, monkeypatch):
    settings = _demo_settings(monkeypatch, DEMO_SEED_ENABLED="false")
    async with db_sessionmaker() as session:
        await seed_demo_accounts(session, settings=settings)

    async with db_sessionmaker() as session:
        repo = RbacRepository(session)
        assert await repo.get_credential_by_username("demo_user") is None


async def test_seed_skips_an_account_with_no_password_configured(db_sessionmaker, monkeypatch):
    settings = _demo_settings(monkeypatch, DEMO_SUPERADMIN_PASSWORD="")
    async with db_sessionmaker() as session:
        await seed_demo_accounts(session, settings=settings)

    async with db_sessionmaker() as session:
        repo = RbacRepository(session)
        assert await repo.get_credential_by_username("demo_superadmin") is None
        # The other three accounts must still be created - one missing
        # password must not block the rest.
        assert await repo.get_credential_by_username("demo_analyst") is not None
