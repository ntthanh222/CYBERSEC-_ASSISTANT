import pytest

from backend.core.tls import (
    InsecureTlsConfigurationError,
    apply_ssl_mode,
    dsn_sslmode,
    effective_sslmode,
    require_secure_tls,
)


def test_apply_ssl_mode_injects_when_absent():
    url = "postgresql+psycopg://u:p@host:5432/db"
    assert apply_ssl_mode(url, "require") == url + "?sslmode=require"


def test_apply_ssl_mode_does_not_override_an_existing_sslmode():
    url = "postgresql+psycopg://u:p@host:5432/db?sslmode=disable"
    assert apply_ssl_mode(url, "require") == url


def test_apply_ssl_mode_is_a_noop_without_a_database_ssl_mode():
    url = "postgresql+psycopg://u:p@host:5432/db"
    assert apply_ssl_mode(url, "") == url


def test_apply_ssl_mode_is_a_noop_for_non_postgres_urls():
    # Regression: unconditionally injecting sslmode into any URL corrupted
    # sqlite:// URLs (the test suite's Postgres stand-in) with an
    # ArgumentError - sslmode is a libpq concept, not a driver-agnostic one.
    url = "sqlite:///C:/tmp/test.db"
    assert apply_ssl_mode(url, "require") == url


def test_dsn_sslmode_reads_the_query_string():
    assert dsn_sslmode("postgresql+psycopg://u:p@host:5432/db?sslmode=require") == "require"


def test_dsn_sslmode_is_none_when_absent():
    assert dsn_sslmode("postgresql+psycopg://u:p@host:5432/db") is None


def test_dsn_sslmode_is_none_for_an_empty_url():
    assert dsn_sslmode("") is None


def test_effective_sslmode_prefers_the_dsns_own_value():
    url = "postgresql+psycopg://u:p@host:5432/db?sslmode=disable"
    assert effective_sslmode(url, "require") == "disable"


def test_effective_sslmode_falls_back_to_database_ssl_mode():
    url = "postgresql+psycopg://u:p@host:5432/db"
    assert effective_sslmode(url, "require") == "require"


def test_effective_sslmode_is_none_when_neither_is_set():
    assert effective_sslmode("postgresql+psycopg://u:p@host:5432/db", "") is None


@pytest.mark.parametrize("app_env", ["local", "test", "development"])
def test_require_secure_tls_is_a_noop_outside_staging_and_production(app_env):
    # Must not raise, regardless of how insecure the DSN is.
    require_secure_tls(
        url="postgresql+psycopg://u:p@postgres:5432/db?sslmode=disable",
        database_ssl_mode="",
        app_env=app_env,
        label="DATABASE_URL",
    )


@pytest.mark.parametrize("app_env", ["staging", "production", "STAGING", "Production"])
@pytest.mark.parametrize("sslmode", ["require", "verify-ca", "verify-full"])
def test_require_secure_tls_accepts_secure_modes(app_env, sslmode):
    require_secure_tls(
        url=f"postgresql+psycopg://u:p@host:5432/db?sslmode={sslmode}",
        database_ssl_mode="",
        app_env=app_env,
        label="DATABASE_URL",
    )


@pytest.mark.parametrize("app_env", ["staging", "production"])
@pytest.mark.parametrize("sslmode", ["disable", "allow", "prefer", "garbage-value"])
def test_require_secure_tls_rejects_insecure_or_invalid_modes(app_env, sslmode):
    with pytest.raises(InsecureTlsConfigurationError):
        require_secure_tls(
            url=f"postgresql+psycopg://u:p@host:5432/db?sslmode={sslmode}",
            database_ssl_mode="",
            app_env=app_env,
            label="DATABASE_URL",
        )


def test_require_secure_tls_rejects_a_missing_sslmode_in_staging():
    with pytest.raises(InsecureTlsConfigurationError):
        require_secure_tls(
            url="postgresql+psycopg://u:p@host:5432/db",
            database_ssl_mode="",
            app_env="staging",
            label="DATABASE_URL",
        )


def test_require_secure_tls_accepts_a_missing_dsn_sslmode_when_database_ssl_mode_is_secure():
    require_secure_tls(
        url="postgresql+psycopg://u:p@host:5432/db",
        database_ssl_mode="require",
        app_env="staging",
        label="DATABASE_URL",
    )


def test_require_secure_tls_rejects_an_insecure_database_ssl_mode_value():
    with pytest.raises(InsecureTlsConfigurationError):
        require_secure_tls(
            url="postgresql+psycopg://u:p@host:5432/db",
            database_ssl_mode="disable",
            app_env="staging",
            label="DATABASE_URL",
        )


def test_require_secure_tls_rejects_when_dsn_declares_weak_mode_despite_secure_database_ssl_mode():
    # The DSN's own sslmode=disable wins over DATABASE_SSL_MODE=require for
    # the actual connection (setdefault semantics) - this must hard-fail,
    # not silently trust DATABASE_SSL_MODE instead.
    with pytest.raises(InsecureTlsConfigurationError):
        require_secure_tls(
            url="postgresql+psycopg://u:p@host:5432/db?sslmode=disable",
            database_ssl_mode="require",
            app_env="staging",
            label="DATABASE_URL",
        )


def test_require_secure_tls_error_message_never_contains_the_password():
    secret = "s3cr3t-password"
    url = f"postgresql+psycopg://u:{secret}@host:5432/db?sslmode=disable"
    with pytest.raises(InsecureTlsConfigurationError) as exc_info:
        require_secure_tls(url=url, database_ssl_mode="", app_env="staging", label="DATABASE_URL")
    assert secret not in str(exc_info.value)


def test_require_secure_tls_error_message_identifies_the_label():
    with pytest.raises(InsecureTlsConfigurationError, match="DATABASE_MIGRATION_URL"):
        require_secure_tls(
            url="postgresql+psycopg://u:p@host:5432/db?sslmode=disable",
            database_ssl_mode="",
            app_env="production",
            label="DATABASE_MIGRATION_URL",
        )
