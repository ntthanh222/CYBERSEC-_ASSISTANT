"""Security-critical regression: local demo-session mode must never be
reachable outside APP_ENV=local, regardless of how a deployment got
misconfigured. The positive path (real session creation against a real
Postgres) is exercised end-to-end by the Docker one-command Playwright
acceptance test, not here - this file only proves the gate holds.
"""
from backend.config.settings import Settings, get_settings
from backend.main import app


def _settings_with_app_env(app_env: str) -> Settings:
    # Fields with a `validation_alias` (DATABASE_URL, SUPABASE_JWT_SECRET,
    # ...) must be passed by that alias when constructing Settings directly
    # in Python - the model has no `populate_by_name=True`, so the plain
    # attribute name (`database_url_raw`) is silently ignored otherwise.
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


def test_local_session_404s_in_staging(unauthenticated_client):
    app.dependency_overrides[get_settings] = lambda: _settings_with_app_env("staging")
    try:
        response = unauthenticated_client.post("/api/auth/local-session")
    finally:
        app.dependency_overrides.pop(get_settings, None)

    assert response.status_code == 404


def test_local_session_404s_in_production(unauthenticated_client):
    app.dependency_overrides[get_settings] = lambda: _settings_with_app_env("production")
    try:
        response = unauthenticated_client.post("/api/auth/local-session")
    finally:
        app.dependency_overrides.pop(get_settings, None)

    assert response.status_code == 404


def test_local_session_404s_in_test_env(unauthenticated_client):
    app.dependency_overrides[get_settings] = lambda: _settings_with_app_env("test")
    try:
        response = unauthenticated_client.post("/api/auth/local-session")
    finally:
        app.dependency_overrides.pop(get_settings, None)

    assert response.status_code == 404


def test_default_local_auth_secret_only_applied_when_local():
    staging = _settings_with_app_env("staging")
    assert staging.supabase_jwt_secret == ""

    local = Settings(_env_file=None, app_env="local")
    assert local.supabase_jwt_secret != ""


def test_real_secret_overrides_local_default():
    local = Settings(_env_file=None, app_env="local", SUPABASE_JWT_SECRET="a-real-secret")
    assert local.supabase_jwt_secret == "a-real-secret"


def test_local_session_404s_when_demo_seed_enabled(unauthenticated_client):
    """The anonymous zero-credential session must not sit alongside seeded
    demo accounts - it defaults to disallowed the moment Demo Mode is on,
    without an explicit ALLOW_LOCAL_MODE override."""
    settings = Settings(_env_file=None, app_env="local", DEMO_SEED_ENABLED="true")
    assert settings.allow_local_mode is False
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        response = unauthenticated_client.post("/api/auth/local-session")
    finally:
        app.dependency_overrides.pop(get_settings, None)

    assert response.status_code == 404


def test_local_session_404s_when_demo_require_gemini_enabled(unauthenticated_client):
    settings = Settings(_env_file=None, app_env="local", DEMO_REQUIRE_GEMINI="true")
    assert settings.allow_local_mode is False
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        response = unauthenticated_client.post("/api/auth/local-session")
    finally:
        app.dependency_overrides.pop(get_settings, None)

    assert response.status_code == 404


def test_explicit_allow_local_mode_true_overrides_demo_mode_default(unauthenticated_client):
    """An operator's explicit ALLOW_LOCAL_MODE=true always wins, even under
    Demo Mode - the default only flips automatically, it never hard-blocks."""
    settings = Settings(
        _env_file=None, app_env="local", DEMO_SEED_ENABLED="true", ALLOW_LOCAL_MODE="true"
    )
    assert settings.allow_local_mode is True


def test_explicit_allow_local_mode_false_disables_outside_demo_mode():
    settings = Settings(_env_file=None, app_env="local", ALLOW_LOCAL_MODE="false")
    assert settings.allow_local_mode is False


def test_allow_local_mode_defaults_true_in_plain_local_dev():
    settings = Settings(_env_file=None, app_env="local")
    assert settings.allow_local_mode is True
