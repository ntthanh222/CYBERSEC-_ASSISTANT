import logging

from sqlalchemy import create_engine

from backend.database.base import Base
from backend.database import models  # noqa: F401 - registers tables on Base.metadata
from backend.scripts.db_preflight import _check_downgrade_renders, _check_tls, _host_and_db, run


def _sqlite_url(tmp_path, name: str) -> str:
    path = tmp_path / name
    engine = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(engine)
    engine.dispose()
    return f"sqlite:///{path}"


def test_host_and_db_parses_a_normal_dsn():
    host, db = _host_and_db("postgresql+psycopg://u:p@pooler.supabase.com:5432/postgres")
    assert host == "pooler.supabase.com"
    assert db == "postgres"


def test_host_and_db_handles_missing_parts():
    host, db = _host_and_db("sqlite:///x.db")
    assert host == "?"


def test_run_reports_expected_tables_present(tmp_path, capsys):
    url = _sqlite_url(tmp_path, "clean.db")

    exit_code = run(url, allow_production=True)

    assert exit_code == 0


def test_run_never_prints_a_credential(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://secret-user:secret-pass@host:5432/db")
    url = _sqlite_url(tmp_path, "clean.db")

    run(url, allow_production=True)

    captured = capsys.readouterr()
    assert "secret-pass" not in captured.out
    assert "secret-pass" not in captured.err


def test_run_rejects_a_malformed_dsn_before_connecting(tmp_path, capsys):
    bad = 'postgresql+psycopg://user:pa"ss@db.example.com:5432/postgres'

    exit_code = run(bad, allow_production=True)

    assert exit_code == 3
    captured = capsys.readouterr()
    assert 'pa"ss' not in captured.out
    assert 'pa"ss' not in captured.err


def test_check_downgrade_renders_true_for_a_real_target(tmp_path):
    # Regression: command.downgrade(cfg, "-1", sql=True) raises CommandError
    # ("downgrade with --sql requires <fromrev>:<torev>") because offline
    # mode never queries the target for "current", making "-1" ambiguous.
    # This silently reported downgrade_ok=False in every environment,
    # local Docker Postgres included - not something the DSN itself could
    # ever fix, so an SQLite target proves the rendering path itself works.
    url = _sqlite_url(tmp_path, "clean.db")
    assert _check_downgrade_renders(url) is True


def test_check_downgrade_renders_does_not_choke_on_a_percent_encoded_password():
    # A password percent-encoded per docs/SUPABASE_SETUP.md (e.g. '"' -> %22)
    # puts a literal "%" in the DSN. Config.set_main_option() stores it via
    # configparser, whose BasicInterpolation treats a bare "%" as the start
    # of an interpolation directive and previously raised ValueError. Offline
    # (--sql) rendering never opens a connection - host reachability is
    # irrelevant here - so the regression is specifically that this must not
    # raise, and now correctly renders.
    url = "postgresql+psycopg://user:pa%22ss@db.unreachable-host.example:5432/postgres"
    assert _check_downgrade_renders(url) is True


def _staging_env(monkeypatch, app_env: str):
    from backend.config.settings import get_settings

    monkeypatch.setenv("APP_ENV", app_env)
    if app_env in {"staging", "production"}:
        monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@db.example.com:5432/postgres")
        # A secure default so tests targeting the app_env/host guards below
        # are not incidentally tripped by the (separate) TLS guard - tests
        # that specifically exercise TLS enforcement override this.
        monkeypatch.setenv("DATABASE_SSL_MODE", "require")
    get_settings.cache_clear()


def test_expect_staging_refuses_when_app_env_is_not_staging(tmp_path, monkeypatch):
    _staging_env(monkeypatch, "local")
    from backend.config.settings import get_settings

    try:
        url = _sqlite_url(tmp_path, "clean.db")
        assert run(url, allow_production=True, expect_staging=True) == 4
    finally:
        get_settings.cache_clear()


def test_expect_staging_refuses_a_local_host(monkeypatch):
    _staging_env(monkeypatch, "staging")
    from backend.config.settings import get_settings

    try:
        local = "postgresql+psycopg://u:p@localhost:5432/postgres"
        assert run(local, allow_production=True, expect_staging=True) == 4
    finally:
        get_settings.cache_clear()


def test_expect_staging_refuses_the_docker_service_hostname(monkeypatch):
    _staging_env(monkeypatch, "staging")
    from backend.config.settings import get_settings

    try:
        docker_default = "postgresql+psycopg://u:p@postgres:5432/cybersec_assistant"
        assert run(docker_default, allow_production=True, expect_staging=True) == 4
    finally:
        get_settings.cache_clear()


def test_expect_staging_passes_the_guard_for_a_remote_host(tmp_path, monkeypatch):
    """The guard itself allows a remote host through; the connection attempt
    that follows is a separate concern (here it fails, which is exit 2, not 4)."""
    _staging_env(monkeypatch, "staging")
    from backend.config.settings import get_settings

    try:
        remote = "postgresql+psycopg://u:p@db.unreachable-host.example:5432/postgres"
        assert run(remote, allow_production=True, expect_staging=True) == 2
    finally:
        get_settings.cache_clear()


def test_expect_staging_hard_fails_on_a_target_dsn_with_no_sslmode(monkeypatch, caplog):
    # Requirement 8: --expect-staging with an insecure DSN must exit non-zero,
    # not just warn and continue exit 0 (the bug Codex flagged). Overrides
    # _staging_env's default DATABASE_SSL_MODE=require so this genuinely
    # tests "nothing anywhere sets a secure sslmode", not the fallback path
    # (that path is covered by test_run_reports_tls_pass_before_attempting_a_secure_target).
    _staging_env(monkeypatch, "staging")
    monkeypatch.setenv("DATABASE_SSL_MODE", "")
    from backend.config.settings import get_settings

    try:
        insecure = "postgresql+psycopg://u:p@db.remote-host.example:5432/postgres"
        with caplog.at_level(logging.INFO):
            exit_code = run(
                insecure, allow_production=True, expect_staging=True, target_label="Migration"
            )
        assert exit_code == 5
        assert "Migration TLS: FAIL" in caplog.text
    finally:
        get_settings.cache_clear()


def test_expect_staging_hard_fails_on_explicit_sslmode_disable(monkeypatch):
    _staging_env(monkeypatch, "staging")
    from backend.config.settings import get_settings

    try:
        insecure = "postgresql+psycopg://u:p@db.remote-host.example:5432/postgres?sslmode=disable"
        assert run(insecure, allow_production=True, expect_staging=True) == 5
    finally:
        get_settings.cache_clear()


def test_run_reports_tls_pass_before_attempting_a_secure_target(monkeypatch, caplog):
    # A secure but unreachable host: TLS must pass first (proven by the log
    # line), and the *subsequent* failure is a connection failure (exit 2),
    # not a TLS failure (exit 5) - this is what distinguishes "TLS enforced
    # correctly" from "TLS check never actually ran".
    _staging_env(monkeypatch, "staging")
    from backend.config.settings import get_settings

    try:
        secure = "postgresql+psycopg://u:p@db.unreachable-host.example:5432/postgres?sslmode=require"
        with caplog.at_level(logging.INFO):
            exit_code = run(
                secure, allow_production=True, expect_staging=True, target_label="Migration"
            )
        assert exit_code == 2
        assert "Migration TLS: PASS (sslmode=require)" in caplog.text
    finally:
        get_settings.cache_clear()


def test_check_tls_is_a_noop_outside_staging_and_production():
    # Requirement 9: local/dev Docker Postgres (no TLS configured) must not
    # be affected by this guard at all.
    ok = _check_tls(
        "postgresql+psycopg://cybersec:change-me@postgres:5432/cybersec_assistant",
        database_ssl_mode="",
        app_env="local",
        label="Runtime",
    )
    assert ok is True


def test_check_tls_never_logs_the_password_on_failure(caplog):
    with caplog.at_level(logging.INFO):
        ok = _check_tls(
            "postgresql+psycopg://u:s3cr3t-pass@db.example.com:5432/postgres?sslmode=disable",
            database_ssl_mode="",
            app_env="staging",
            label="Runtime",
        )
    assert ok is False
    assert "s3cr3t-pass" not in caplog.text


def test_run_refuses_without_allow_production_flag(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("JWT_SECRET", "a-real-secret-value")
    monkeypatch.setenv("SECRET_KEY", "another-real-secret")
    monkeypatch.setenv("DB_PASSWORD", "a-real-db-password")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@host:5432/db?sslmode=require")
    from backend.config.settings import get_settings

    get_settings.cache_clear()
    try:
        url = _sqlite_url(tmp_path, "clean.db")
        exit_code = run(url, allow_production=False)
        assert exit_code == 1
    finally:
        get_settings.cache_clear()
