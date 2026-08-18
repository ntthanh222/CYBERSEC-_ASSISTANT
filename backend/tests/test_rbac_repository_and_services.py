"""Direct unit coverage for RbacRepository/RbacService/LocalAdminAuthService
internals not reachable through the HTTP layer (mirrors
``test_assistant_service_unit.py``'s pattern). ``create_auth_user`` is
monkeypatched here to avoid the real ``auth.users`` raw-SQL insert (absent
from the SQLite test schema - see ``repositories/rbac.py``'s ``list_users``
docstring), so the rest of the bootstrap/login logic can still be exercised
directly against SQLite.
"""
import uuid

import pytest

from backend.config.settings import get_settings
from backend.core.exceptions import (
    AuthenticationError,
    AuthorizationError,
    ConflictError,
    InvalidRequestError,
    NotFoundError,
)
from backend.repositories.rbac import RbacRepository
from backend.services import local_admin as local_admin_module
from backend.services.local_admin import LocalAdminAuthService
from backend.services.rbac import RbacService


# --- RbacRepository -----------------------------------------------------


async def test_ensure_role_creates_a_default_user_role_once(db_sessionmaker):
    user_id = uuid.uuid4()
    async with db_sessionmaker() as session:
        repo = RbacRepository(session)
        created = await repo.ensure_role(user_id)
        await session.commit()
        assert created.role == "user"
        assert created.is_active is True

    async with db_sessionmaker() as session:
        repo = RbacRepository(session)
        # Second call must return the *existing* row, not create another.
        again = await repo.ensure_role(user_id, default_role="admin")
        assert again.role == "user"


async def test_any_admin_exists_is_false_until_one_is_created(db_sessionmaker):
    async with db_sessionmaker() as session:
        repo = RbacRepository(session)
        assert await repo.any_admin_exists() is False

        user_id = uuid.uuid4()
        await repo.set_role(user_id, role="admin")
        await session.commit()

    async with db_sessionmaker() as session:
        repo = RbacRepository(session)
        assert await repo.any_admin_exists() is True
        assert await repo.count_active_admins() == 1


async def test_set_active_then_touch_last_login_updates_the_credential(db_sessionmaker):
    user_id = uuid.uuid4()
    async with db_sessionmaker() as session:
        repo = RbacRepository(session)
        await repo.set_role(user_id, role="admin")
        await repo.create_local_admin_credential(
            user_id=user_id, username="direct-test-admin", password_hash="not-checked-here"
        )
        await session.commit()

    async with db_sessionmaker() as session:
        repo = RbacRepository(session)
        by_username = await repo.get_credential_by_username("direct-test-admin")
        assert by_username is not None
        assert by_username.last_login_at is None

        from backend.core.timeutils import utcnow

        now = utcnow()
        await repo.touch_last_login(user_id, when=now)
        await session.commit()

    async with db_sessionmaker() as session:
        repo = RbacRepository(session)
        by_id = await repo.get_credential_by_user_id(user_id)
        # SQLite (test-only backend) round-trips a naive datetime; Postgres
        # keeps the timezone. Compare the wall-clock value, not tzinfo.
        assert by_id.last_login_at.replace(tzinfo=None) == now.replace(tzinfo=None)


async def test_touch_last_login_is_a_no_op_for_a_user_without_credentials(db_sessionmaker):
    async with db_sessionmaker() as session:
        repo = RbacRepository(session)
        from backend.core.timeutils import utcnow

        # Must not raise even though no LocalAdminCredential row exists.
        await repo.touch_last_login(uuid.uuid4(), when=utcnow())


async def test_record_audit_and_list_audit_log_round_trip(db_sessionmaker):
    actor_id = uuid.uuid4()
    target_id = uuid.uuid4()
    async with db_sessionmaker() as session:
        repo = RbacRepository(session)
        await repo.record_audit(
            actor_user_id=actor_id,
            action="role_changed",
            target_user_id=target_id,
            metadata={"from": "user", "to": "admin"},
        )
        await session.commit()

    async with db_sessionmaker() as session:
        repo = RbacRepository(session)
        items, total = await repo.list_audit_log(page=1, page_size=10)
        assert total == 1
        assert items[0].action == "role_changed"
        assert items[0].meta == {"from": "user", "to": "admin"}


# --- RbacService ----------------------------------------------------------


async def test_service_change_role_rejects_a_role_outside_the_allowed_set(db_sessionmaker):
    async with db_sessionmaker() as session:
        service = RbacService(session)
        with pytest.raises(InvalidRequestError):
            await service.change_role(
                uuid.uuid4(),
                new_role="superuser",
                actor_user_id=uuid.uuid4(),
                actor_role="super_admin",
                actor=None,
            )


async def test_service_change_role_404s_for_an_unknown_target(db_sessionmaker):
    async with db_sessionmaker() as session:
        service = RbacService(session)
        with pytest.raises(NotFoundError):
            await service.change_role(
                uuid.uuid4(),
                new_role="admin",
                actor_user_id=uuid.uuid4(),
                actor_role="super_admin",
                actor=None,
            )


async def test_service_set_active_404s_for_an_unknown_target(db_sessionmaker):
    async with db_sessionmaker() as session:
        service = RbacService(session)
        with pytest.raises(NotFoundError):
            await service.set_active(
                uuid.uuid4(),
                is_active=False,
                actor_user_id=uuid.uuid4(),
                actor_role="admin",
                actor=None,
            )


async def test_service_set_active_true_on_an_already_active_admin_is_a_no_op_allowed(
    db_sessionmaker,
):
    async with db_sessionmaker() as session:
        repo = RbacRepository(session)
        admin_id = uuid.uuid4()
        await repo.set_role(admin_id, role="admin")
        await session.commit()

    async with db_sessionmaker() as session:
        service = RbacService(session)
        # Re-activating an already-active sole admin must not trip the
        # last-admin guard (that guard only fires on *deactivation*).
        result = await service.set_active(
            admin_id, is_active=True, actor_user_id=admin_id, actor_role="admin", actor=None
        )
        assert result["is_active"] is True


async def test_service_change_role_blocks_a_plain_admin_from_creating_a_super_admin(
    db_sessionmaker,
):
    async with db_sessionmaker() as session:
        repo = RbacRepository(session)
        target_id = uuid.uuid4()
        await repo.set_role(target_id, role="user")
        await session.commit()

    async with db_sessionmaker() as session:
        service = RbacService(session)
        with pytest.raises(AuthorizationError):
            await service.change_role(
                target_id,
                new_role="super_admin",
                actor_user_id=uuid.uuid4(),
                actor_role="admin",
                actor=None,
            )


async def test_service_change_role_blocks_self_promotion_to_super_admin(db_sessionmaker):
    async with db_sessionmaker() as session:
        repo = RbacRepository(session)
        admin_id = uuid.uuid4()
        await repo.set_role(admin_id, role="admin")
        await session.commit()

    async with db_sessionmaker() as session:
        service = RbacService(session)
        with pytest.raises(AuthorizationError):
            await service.change_role(
                admin_id,
                new_role="super_admin",
                actor_user_id=admin_id,
                actor_role="admin",
                actor=None,
            )


async def test_service_set_active_blocks_a_plain_admin_from_deactivating_a_super_admin(
    db_sessionmaker,
):
    async with db_sessionmaker() as session:
        repo = RbacRepository(session)
        super_admin_id = uuid.uuid4()
        await repo.set_role(super_admin_id, role="super_admin")
        await session.commit()

    async with db_sessionmaker() as session:
        service = RbacService(session)
        with pytest.raises(AuthorizationError):
            await service.set_active(
                super_admin_id,
                is_active=False,
                actor_user_id=uuid.uuid4(),
                actor_role="admin",
                actor=None,
            )


async def test_service_change_role_blocks_demoting_the_last_active_super_admin(db_sessionmaker):
    async with db_sessionmaker() as session:
        repo = RbacRepository(session)
        super_admin_id = uuid.uuid4()
        await repo.set_role(super_admin_id, role="super_admin")
        await session.commit()

    async with db_sessionmaker() as session:
        service = RbacService(session)
        with pytest.raises(ConflictError):
            await service.change_role(
                super_admin_id,
                new_role="admin",
                actor_user_id=super_admin_id,
                actor_role="super_admin",
                actor=None,
            )


# --- LocalAdminAuthService --------------------------------------------------


@pytest.fixture(autouse=True)
def _fake_auth_user_creation(monkeypatch):
    """Swap the real (Postgres-only) auth.users insert for an in-memory UUID
    mint, so setup()/login()'s own logic can run end to end on SQLite."""

    async def _fake_create_auth_user(session, *, email):
        return uuid.uuid4()

    monkeypatch.setattr(local_admin_module, "create_auth_user", _fake_create_auth_user)


async def test_setup_creates_an_admin_and_mints_a_session(db_sessionmaker):
    async with db_sessionmaker() as session:
        service = LocalAdminAuthService(session)
        result = await service.setup(
            username="root-admin", password="correct-horse-1", settings=get_settings()
        )
        assert result.access_token
        assert result.user.email.startswith("root-admin@")

    async with db_sessionmaker() as session:
        repo = RbacRepository(session)
        assert await repo.any_admin_exists() is True


async def test_setup_rejects_a_duplicate_username(db_sessionmaker):
    async with db_sessionmaker() as session:
        service = LocalAdminAuthService(session)
        await service.setup(
            username="dup-admin", password="correct-horse-1", settings=get_settings()
        )

    async with db_sessionmaker() as session:
        repo = RbacRepository(session)
        # Deactivate the bootstrapped admin so any_admin_exists() doesn't
        # short-circuit before reaching the username-uniqueness check.
        existing = await repo.get_credential_by_username("dup-admin")
        await repo.set_active(existing.user_id, is_active=False)
        await session.commit()

    async with db_sessionmaker() as session:
        service = LocalAdminAuthService(session)
        with pytest.raises(ConflictError):
            await service.setup(
                username="dup-admin", password="another-pass-1", settings=get_settings()
            )


async def test_login_succeeds_with_the_right_password(db_sessionmaker):
    async with db_sessionmaker() as session:
        service = LocalAdminAuthService(session)
        await service.setup(
            username="login-admin", password="correct-horse-1", settings=get_settings()
        )

    async with db_sessionmaker() as session:
        service = LocalAdminAuthService(session)
        result = await service.login(
            username="login-admin", password="correct-horse-1", settings=get_settings()
        )
        assert result.access_token

    async with db_sessionmaker() as session:
        repo = RbacRepository(session)
        credential = await repo.get_credential_by_username("login-admin")
        assert credential.last_login_at is not None


async def test_login_fails_with_the_wrong_password(db_sessionmaker):
    async with db_sessionmaker() as session:
        service = LocalAdminAuthService(session)
        await service.setup(
            username="wrongpass-admin", password="correct-horse-1", settings=get_settings()
        )

    async with db_sessionmaker() as session:
        service = LocalAdminAuthService(session)
        with pytest.raises(AuthenticationError):
            await service.login(
                username="wrongpass-admin", password="totally-wrong-1", settings=get_settings()
            )


async def test_login_fails_for_a_deactivated_admin(db_sessionmaker):
    async with db_sessionmaker() as session:
        service = LocalAdminAuthService(session)
        await service.setup(
            username="disabled-admin", password="correct-horse-1", settings=get_settings()
        )

    async with db_sessionmaker() as session:
        repo = RbacRepository(session)
        credential = await repo.get_credential_by_username("disabled-admin")
        await repo.set_active(credential.user_id, is_active=False)
        await session.commit()

    async with db_sessionmaker() as session:
        service = LocalAdminAuthService(session)
        with pytest.raises(AuthenticationError):
            await service.login(
                username="disabled-admin", password="correct-horse-1", settings=get_settings()
            )
