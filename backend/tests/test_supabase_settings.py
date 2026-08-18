import pytest
from pydantic import ValidationError

from backend.config.settings import Settings
from backend.core.tls import dsn_sslmode


def _clear_supabase_env(monkeypatch):
    for key in (
        "APP_ENV",
        "DATABASE_URL",
        "DATABASE_MIGRATION_URL",
        "DATABASE_SSL_MODE",
        "SUPABASE_URL",
        "SUPABASE_PUBLISHABLE_KEY",
        "SUPABASE_SECRET_KEY",
    ):
        monkeypatch.delenv(key, raising=False)


def test_app_env_defaults_to_local(monkeypatch):
    _clear_supabase_env(monkeypatch)
    settings = Settings(_env_file=None)
    assert settings.app_env == "local"
    assert not settings.requires_supabase_target


def test_app_env_rejects_unknown_value(monkeypatch):
    _clear_supabase_env(monkeypatch)
    monkeypatch.setenv("APP_ENV", "nonsense")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_database_url_falls_back_to_docker_default(monkeypatch):
    _clear_supabase_env(monkeypatch)
    monkeypatch.setenv("DB_HOST", "postgres")
    monkeypatch.setenv("DB_USER", "cybersec")
    monkeypatch.setenv("DB_PASSWORD", "change-me")
    monkeypatch.setenv("DB_NAME", "cybersec_assistant")
    settings = Settings(_env_file=None)
    assert settings.database_url.startswith("postgresql+psycopg://cybersec:change-me@postgres")


def test_database_url_prefers_explicit_override(monkeypatch):
    _clear_supabase_env(monkeypatch)
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@pooler.supabase.com:5432/postgres")
    settings = Settings(_env_file=None)
    assert settings.database_url == "postgresql+psycopg://u:p@pooler.supabase.com:5432/postgres"


def test_database_ssl_mode_is_injected_once(monkeypatch):
    _clear_supabase_env(monkeypatch)
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@pooler.supabase.com:5432/postgres")
    monkeypatch.setenv("DATABASE_SSL_MODE", "require")
    settings = Settings(_env_file=None)
    assert "sslmode=require" in settings.database_url
    assert settings.database_url.count("sslmode=") == 1


def test_database_ssl_mode_does_not_override_existing_query_param(monkeypatch):
    _clear_supabase_env(monkeypatch)
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@host:5432/db?sslmode=disable")
    monkeypatch.setenv("DATABASE_SSL_MODE", "require")
    settings = Settings(_env_file=None)
    assert "sslmode=disable" in settings.database_url


def test_migration_url_falls_back_to_database_url_when_unset(monkeypatch):
    _clear_supabase_env(monkeypatch)
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@pooler.supabase.com:5432/postgres")
    settings = Settings(_env_file=None)
    assert settings.database_migration_url == settings.database_url


def test_migration_url_overrides_independently(monkeypatch):
    _clear_supabase_env(monkeypatch)
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@pooler.supabase.com:5432/postgres")
    monkeypatch.setenv("DATABASE_MIGRATION_URL", "postgresql+psycopg://u:p@direct.supabase.com:5432/postgres")
    settings = Settings(_env_file=None)
    assert "direct.supabase.com" in settings.database_migration_url
    assert "pooler.supabase.com" in settings.database_url


def test_sync_database_url_alias_matches_migration_url(monkeypatch):
    _clear_supabase_env(monkeypatch)
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@pooler.supabase.com:5432/postgres")
    settings = Settings(_env_file=None)
    assert settings.sync_database_url == settings.database_migration_url


def test_staging_requires_explicit_database_url(monkeypatch):
    _clear_supabase_env(monkeypatch)
    monkeypatch.setenv("APP_ENV", "staging")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_production_requires_explicit_database_url(monkeypatch):
    _clear_supabase_env(monkeypatch)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("JWT_SECRET", "a-real-secret-value")
    monkeypatch.setenv("SECRET_KEY", "another-real-secret")
    monkeypatch.setenv("DB_PASSWORD", "a-real-db-password")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_staging_accepts_explicit_database_url(monkeypatch):
    _clear_supabase_env(monkeypatch)
    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@pooler.supabase.com:5432/postgres")
    monkeypatch.setenv("DATABASE_SSL_MODE", "require")
    settings = Settings(_env_file=None)
    assert settings.requires_supabase_target


def test_local_does_not_require_database_url(monkeypatch):
    _clear_supabase_env(monkeypatch)
    monkeypatch.setenv("APP_ENV", "local")
    settings = Settings(_env_file=None)
    assert settings.database_url  # falls back to Docker default without raising


def test_supabase_secret_key_never_defaults_to_a_real_looking_value(monkeypatch):
    _clear_supabase_env(monkeypatch)
    settings = Settings(_env_file=None)
    assert settings.supabase_secret_key == ""


# --- TLS enforcement (Codex merge-block finding) -----------------------
#
# backend/core/tls.py is the single source of truth for "is this DSN
# actually going to use TLS"; every test below reads the *effective*
# settings.database_url / settings.database_migration_url - the exact
# strings handed to create_async_engine() (session.py) and Alembic
# (migrations/env.py) - via dsn_sslmode(), not a superficial substring
# check on the raw input.


def _production_env(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "a-real-secret-value")
    monkeypatch.setenv("SECRET_KEY", "another-real-secret")
    monkeypatch.setenv("DB_PASSWORD", "a-real-db-password")


def test_staging_dsn_with_sslmode_require_passes(monkeypatch):
    _clear_supabase_env(monkeypatch)
    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql+psycopg://u:p@pooler.supabase.com:5432/postgres?sslmode=require"
    )
    settings = Settings(_env_file=None)
    assert dsn_sslmode(settings.database_url) == "require"


def test_production_dsn_with_sslmode_verify_full_passes(monkeypatch):
    _clear_supabase_env(monkeypatch)
    monkeypatch.setenv("APP_ENV", "production")
    _production_env(monkeypatch)
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql+psycopg://u:p@db.example.com:5432/postgres?sslmode=verify-full"
    )
    settings = Settings(_env_file=None)
    assert dsn_sslmode(settings.database_url) == "verify-full"


def test_staging_dsn_with_sslmode_disable_is_rejected(monkeypatch):
    _clear_supabase_env(monkeypatch)
    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql+psycopg://u:p@pooler.supabase.com:5432/postgres?sslmode=disable"
    )
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_production_dsn_with_sslmode_prefer_is_rejected(monkeypatch):
    _clear_supabase_env(monkeypatch)
    monkeypatch.setenv("APP_ENV", "production")
    _production_env(monkeypatch)
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql+psycopg://u:p@db.example.com:5432/postgres?sslmode=prefer"
    )
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_staging_dsn_with_an_unrecognised_sslmode_is_rejected(monkeypatch):
    # "giá trị không hợp lệ" - not just the three named-insecure values.
    _clear_supabase_env(monkeypatch)
    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql+psycopg://u:p@pooler.supabase.com:5432/postgres?sslmode=nope"
    )
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_staging_missing_sslmode_uses_database_ssl_mode_as_the_effective_connection(monkeypatch):
    # The DSN itself declares no sslmode; DATABASE_SSL_MODE must be the
    # thing that actually reaches the connection - not a silent weaker
    # default (libpq's own default is "prefer", which is insecure).
    _clear_supabase_env(monkeypatch)
    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@pooler.supabase.com:5432/postgres")
    monkeypatch.setenv("DATABASE_SSL_MODE", "require")
    settings = Settings(_env_file=None)
    assert dsn_sslmode(settings.database_url) == "require"


def test_staging_missing_sslmode_with_database_ssl_mode_disable_is_rejected(monkeypatch):
    _clear_supabase_env(monkeypatch)
    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@pooler.supabase.com:5432/postgres")
    monkeypatch.setenv("DATABASE_SSL_MODE", "disable")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_dsn_sslmode_disable_wins_over_database_ssl_mode_require_and_still_fails(monkeypatch):
    # Requirement E: a DSN that already declares a weak sslmode must hard
    # fail even when DATABASE_SSL_MODE says "require" - the DSN's own value
    # takes precedence for the *connection* (matching apply_ssl_mode's
    # setdefault), so this conflict must never resolve silently in the
    # DSN's favour.
    _clear_supabase_env(monkeypatch)
    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql+psycopg://u:p@pooler.supabase.com:5432/postgres?sslmode=disable"
    )
    monkeypatch.setenv("DATABASE_SSL_MODE", "require")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_database_migration_url_is_validated_independently_of_database_url(monkeypatch):
    _clear_supabase_env(monkeypatch)
    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql+psycopg://u:p@pooler.supabase.com:5432/postgres?sslmode=require"
    )
    monkeypatch.setenv(
        "DATABASE_MIGRATION_URL",
        "postgresql+psycopg://u:p@direct.supabase.com:5432/postgres?sslmode=disable",
    )
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_database_migration_url_secure_alongside_database_url_secure_passes(monkeypatch):
    _clear_supabase_env(monkeypatch)
    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql+psycopg://u:p@pooler.supabase.com:5432/postgres?sslmode=require"
    )
    monkeypatch.setenv(
        "DATABASE_MIGRATION_URL",
        "postgresql+psycopg://u:p@direct.supabase.com:5432/postgres?sslmode=verify-full",
    )
    settings = Settings(_env_file=None)
    assert dsn_sslmode(settings.database_migration_url) == "verify-full"
    assert dsn_sslmode(settings.database_url) == "require"


def test_local_docker_postgres_without_tls_is_unaffected(monkeypatch):
    _clear_supabase_env(monkeypatch)
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("DB_HOST", "postgres")
    monkeypatch.setenv("DB_USER", "cybersec")
    monkeypatch.setenv("DB_PASSWORD", "change-me")
    monkeypatch.setenv("DB_NAME", "cybersec_assistant")
    settings = Settings(_env_file=None)
    assert dsn_sslmode(settings.database_url) is None
    assert settings.database_url.startswith("postgresql+psycopg://cybersec:change-me@postgres")


def test_percent_encoded_password_characters_pass_through_tls_validation(monkeypatch):
    # '"' -> %22, '@' -> %40, ':' -> %3A, plus a literal '%' from those
    # encodings themselves - the TLS check must not choke on any of it.
    _clear_supabase_env(monkeypatch)
    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg://postgres.ref:p%22a%40ss%3Aword@pooler.supabase.com:5432/postgres"
        "?sslmode=require",
    )
    settings = Settings(_env_file=None)
    assert dsn_sslmode(settings.database_url) == "require"
    assert "p%22a%40ss%3Aword" in settings.database_url


def test_insecure_tls_validation_error_never_includes_the_password(monkeypatch):
    _clear_supabase_env(monkeypatch)
    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg://u:s3cr3t-password@pooler.supabase.com:5432/postgres?sslmode=disable",
    )
    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)
    assert "s3cr3t-password" not in str(exc_info.value)
