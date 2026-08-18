"""Local admin bootstrap/login: gating, validation, and generic-failure paths
that don't require a real ``auth.users`` table (SQLite has none - see
``backend/repositories/rbac.py``'s ``list_users`` docstring). The full
successful setup/login round trip against a real ``auth.users`` row is
verified live against Postgres in the disposable-stack acceptance pass.
"""
from backend.config.settings import Settings, get_settings
from backend.database.models.rbac import UserRole
from backend.main import app

from .conftest import TEST_USER_A


def _settings_with_app_env(app_env: str) -> Settings:
    kwargs = {
        "_env_file": None,
        "app_env": app_env,
        "jwt_secret": "x",
        "secret_key": "x",
        "db_password": "x",
    }
    if app_env in {"staging", "production"}:
        kwargs["DATABASE_URL"] = "postgresql+psycopg://x:x@example.test:5432/x"
        kwargs["DATABASE_SSL_MODE"] = "require"
    return Settings(**kwargs)


def _as_staging():
    app.dependency_overrides[get_settings] = lambda: _settings_with_app_env("staging")


def _clear_settings_override():
    app.dependency_overrides.pop(get_settings, None)


def test_setup_status_404s_outside_local(unauthenticated_client):
    _as_staging()
    try:
        assert unauthenticated_client.get("/api/auth/local-admin/setup-status").status_code == 404
    finally:
        _clear_settings_override()


def test_setup_404s_outside_local(unauthenticated_client):
    _as_staging()
    try:
        response = unauthenticated_client.post(
            "/api/auth/local-admin/setup",
            json={"username": "admin", "password": "correct-horse-1"},
        )
        assert response.status_code == 404
    finally:
        _clear_settings_override()


def test_login_404s_outside_local(unauthenticated_client):
    _as_staging()
    try:
        response = unauthenticated_client.post(
            "/api/auth/local-admin/login", json={"username": "admin", "password": "x"}
        )
        assert response.status_code == 404
    finally:
        _clear_settings_override()


def test_setup_status_reports_false_when_no_admin_exists(unauthenticated_client):
    body = unauthenticated_client.get("/api/auth/local-admin/setup-status").json()
    assert body == {"admin_exists": False}


async def test_setup_status_reports_true_once_an_admin_exists(
    unauthenticated_client, db_sessionmaker
):
    async with db_sessionmaker() as session:
        session.add(UserRole(user_id=TEST_USER_A.id, role="admin", is_active=True))
        await session.commit()

    body = unauthenticated_client.get("/api/auth/local-admin/setup-status").json()
    assert body == {"admin_exists": True}


def test_setup_rejects_a_too_short_username(unauthenticated_client):
    response = unauthenticated_client.post(
        "/api/auth/local-admin/setup", json={"username": "ab", "password": "correct-horse-1"}
    )
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_request"


def test_setup_rejects_a_too_short_password(unauthenticated_client):
    response = unauthenticated_client.post(
        "/api/auth/local-admin/setup", json={"username": "administrator", "password": "short"}
    )
    assert response.status_code == 400


async def test_setup_is_blocked_once_an_admin_already_exists(
    unauthenticated_client, db_sessionmaker
):
    async with db_sessionmaker() as session:
        session.add(UserRole(user_id=TEST_USER_A.id, role="admin", is_active=True))
        await session.commit()

    response = unauthenticated_client.post(
        "/api/auth/local-admin/setup",
        json={"username": "second-admin", "password": "correct-horse-1"},
    )
    assert response.status_code == 409
    assert response.json()["error"] == "conflict"


def test_login_with_an_unknown_username_is_a_generic_401(unauthenticated_client):
    response = unauthenticated_client.post(
        "/api/auth/local-admin/login", json={"username": "nobody", "password": "whatever123"}
    )
    assert response.status_code == 401
    body = response.json()
    assert body["error"] == "unauthorized"
    # The message must not distinguish "unknown user" from "wrong password".
    assert "password" not in body["message"].lower() or "invalid" in body["message"].lower()


# --- unified /api/auth/local-login (any role, not just admin) --------------


def test_unified_login_404s_outside_local(unauthenticated_client):
    _as_staging()
    try:
        response = unauthenticated_client.post(
            "/api/auth/local-login", json={"username": "demo_user", "password": "x"}
        )
        assert response.status_code == 404
    finally:
        _clear_settings_override()


def test_unified_login_with_an_unknown_username_is_a_generic_401(unauthenticated_client):
    response = unauthenticated_client.post(
        "/api/auth/local-login", json={"username": "nobody", "password": "whatever123"}
    )
    assert response.status_code == 401
    assert response.json()["error"] == "unauthorized"


async def test_unified_login_works_for_a_non_admin_local_account(
    unauthenticated_client, db_sessionmaker
):
    """The whole point of this endpoint over /local-admin/login: any role
    signs in here, not just admin - set up a plain 'user' account through
    the same bootstrap primitives the demo seed uses and confirm login
    succeeds and returns a session for it."""
    import uuid

    from backend.core.password_hash import hash_password
    from backend.repositories.rbac import RbacRepository

    user_id = uuid.uuid4()
    async with db_sessionmaker() as session:
        repo = RbacRepository(session)
        session.add(UserRole(user_id=user_id, role="user", is_active=True))
        await session.flush()
        await repo.create_local_admin_credential(
            user_id=user_id, username="demo_user", password_hash=hash_password("user-pass-123")
        )
        await session.commit()

    response = unauthenticated_client.post(
        "/api/auth/local-login", json={"username": "demo_user", "password": "user-pass-123"}
    )
    assert response.status_code == 200
    assert response.json()["user"]["id"] == str(user_id)
