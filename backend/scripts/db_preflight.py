"""Read-only preflight check before running Alembic against a target database.

Reports, without ever printing a credential:
  - which target is configured (redacted DSN, host, database name)
  - whether SSL is configured on that DSN
  - the database's current Alembic revision (or "unstamped")
  - which of the expected Phase 0-2 tables exist
  - whether the current head migration can produce a downgrade script
    (a dry check via `alembic downgrade -1 --sql`, no connection required
    beyond what Alembic itself needs to render SQL - never actually runs it)

Exit codes: 0 = checks completed (see report for pass/fail per item),
1 = refused to run (production guard), 2 = could not connect,
3 = the target connection string itself is malformed, 4 = refused to run
(--expect-staging guard: wrong APP_ENV or a local host), 5 = refused to run
(staging/production target does not have verified TLS - see
backend/core/tls.py; this is a hard failure, never a warning).

This script never modifies the database. It exists so a human (or CI) can
see exactly what `alembic upgrade head` is about to do before running it,
especially against Supabase where a wrong target is a real incident, not a
`docker compose down -v` away from a fresh start.
"""
import argparse
import logging
import sys
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import ValidationError
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import SQLAlchemyError

from backend.config.settings import get_settings
from backend.core.db_retry import pg_connect_args, retry_transient
from backend.core.dsn import describe_dsn_problem, redact_dsn
from backend.core.tls import (
    InsecureTlsConfigurationError,
    apply_ssl_mode,
    dsn_sslmode,
    require_secure_tls,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("db_preflight")

# Tables introduced by 0001-0003. Kept as a literal list (not read from
# Base.metadata) so this script still reports something meaningful even if
# imports fail. Deliberately excludes any Auth/Phase-3 table name.
EXPECTED_TABLES = {
    "schema_bootstrap",  # 0001
    "demo_seed_marker",  # 0002
    "conversations",  # 0003
    "messages",  # 0003
    "security_scan_history",  # 0003
}
FORBIDDEN_TABLES = {"users"}  # would indicate the quarantined 0004 leaked back in

# Hosts that are definitively *not* a remote staging target. Used by
# --expect-staging to catch "I meant to point at Supabase but I'm still on
# the Docker default" before a migration runs against the wrong database.
LOCAL_HOSTNAMES = {"localhost", "127.0.0.1", "::1", "postgres", "db", "host.docker.internal"}


def _host_and_db(url: str) -> tuple[str, str]:
    try:
        parts = urlsplit(url)
        return parts.hostname or "?", parts.path.lstrip("/") or "?"
    except ValueError:
        return "?", "?"


def _check_tls(url: str, *, database_ssl_mode: str, app_env: str, label: str) -> bool:
    """Log a "<Label> TLS: PASS/FAIL" line and return whether it passed.

    Delegates the actual decision to backend.core.tls.require_secure_tls -
    the same function Settings' own validator uses - so this script and the
    application agree on what "TLS enforced" means. Never logs the DSN.
    """
    try:
        require_secure_tls(
            url=url, database_ssl_mode=database_ssl_mode, app_env=app_env, label=f"{label} target"
        )
    except InsecureTlsConfigurationError as exc:
        logger.error(str(exc))
        logger.info("%s TLS: FAIL (insecure sslmode)", label)
        return False
    mode = dsn_sslmode(url) or database_ssl_mode or "n/a"
    logger.info("%s TLS: PASS (sslmode=%s)", label, mode)
    return True


def run(
    target_url: str,
    allow_production: bool,
    expect_staging: bool = False,
    target_label: str = "Runtime",
) -> int:
    try:
        settings = get_settings()
    except ValidationError as exc:
        messages = [error["msg"] for error in exc.errors()]
        tls_messages = [m for m in messages if "sslmode" in m.lower() or "tls" in m.lower()]
        if not tls_messages:
            raise  # a genuinely different config problem - do not mislabel it
        for message in tls_messages:
            logger.error(message)
        logger.info("%s TLS: FAIL (insecure sslmode)", target_label)
        return 5

    if settings.is_production and not allow_production:
        logger.error(
            "Refusing to run: is_production is true and --allow-production was not "
            "passed. Re-run with --allow-production if this is genuinely intended."
        )
        return 1

    # Check DSN shape before anything tries to connect: an unencoded special
    # character in the password otherwise surfaces as a misleading host/port
    # error from the driver.
    problem = describe_dsn_problem(target_url)
    if problem is not None:
        logger.error("Target connection string is unusable: %s", problem)
        return 3

    # Normalize *before* checking or connecting - the same transform
    # Settings.database_url/database_migration_url apply - so what
    # _check_tls validates below is exactly what create_engine() receives
    # a few lines down, never a URL that only looks safe on paper because
    # DATABASE_SSL_MODE would have covered it had it actually been applied.
    # A no-op when database_ssl_mode is empty (local/dev).
    target_url = apply_ssl_mode(target_url, settings.database_ssl_mode)

    host, dbname = _host_and_db(target_url)

    if expect_staging:
        if settings.app_env.lower() != "staging":
            logger.error(
                "Refusing to run: --expect-staging was passed but APP_ENV=%s. "
                "Set APP_ENV=staging when targeting the staging database.",
                settings.app_env,
            )
            return 4
        if host.lower() in LOCAL_HOSTNAMES:
            logger.error(
                "Refusing to run: --expect-staging was passed but the target host "
                "(%s) is a local host, not a remote staging database.",
                host,
            )
            return 4
        logger.info("staging target confirmed: APP_ENV=staging, host is remote")

    logger.info("target host=%s database=%s dsn=%s", host, dbname, redact_dsn(target_url))

    if settings.requires_supabase_target:
        if not _check_tls(
            target_url,
            database_ssl_mode=settings.database_ssl_mode,
            app_env=settings.app_env,
            label=target_label,
        ):
            return 5

    try:
        engine = create_engine(
            target_url, pool_pre_ping=True, connect_args=pg_connect_args(target_url)
        )
        try:
            def _connect_and_inspect():
                with engine.connect() as conn:
                    tables = set(inspect(conn).get_table_names())
                    revision_row = (
                        conn.execute(text("SELECT version_num FROM alembic_version")).first()
                        if "alembic_version" in tables
                        else None
                    )
                    return revision_row, tables

            revision_row, tables = retry_transient(_connect_and_inspect, attempts=3)
        finally:
            engine.dispose()
    except SQLAlchemyError as exc:
        logger.error("could not connect to target: %s", type(exc).__name__)
        return 2

    revision = revision_row[0] if revision_row else "unstamped"
    logger.info("current alembic revision: %s", revision)

    missing = sorted(EXPECTED_TABLES - tables)
    unexpected_forbidden = sorted(FORBIDDEN_TABLES & tables)
    if missing:
        logger.info("expected tables missing (ok if pre-migration): %s", missing)
    else:
        logger.info("all expected Phase 0-2 tables present")
    if unexpected_forbidden:
        logger.error(
            "FORBIDDEN tables present (quarantined work leaked in?): %s", unexpected_forbidden
        )

    downgrade_ok = _check_downgrade_renders(target_url)
    logger.info("downgrade script renders cleanly: %s", downgrade_ok)

    logger.info(
        "preflight summary: revision=%s missing_tables=%s forbidden_tables_present=%s "
        "downgrade_ok=%s",
        revision,
        bool(missing),
        bool(unexpected_forbidden),
        downgrade_ok,
    )
    return 0


def _check_downgrade_renders(target_url: str) -> bool:
    """Verify Alembic can render a downgrade script without executing it.

    Uses `--sql` (offline mode): Alembic emits the SQL it *would* run and
    touches no connection, so this is safe to call even against a target
    the caller has not confirmed yet.
    """
    import io
    import contextlib

    from alembic.config import Config
    from alembic import command

    cfg = Config()
    migrations_path = Path(__file__).resolve().parents[1] / "database" / "migrations"
    cfg.set_main_option("script_location", str(migrations_path))
    # See the matching comment in migrations/env.py: configparser's
    # interpolation treats a bare "%" (as produced by percent-encoding a
    # password) as a directive start and raises ValueError unless escaped.
    cfg.set_main_option("sqlalchemy.url", target_url.replace("%", "%%"))
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            # Offline (--sql) mode never queries the target for "current",
            # so a relative revision like "-1" is ambiguous and Alembic
            # raises CommandError. "head:-1" gives it an explicit range
            # instead, matching `alembic downgrade head:-1 --sql`.
            command.downgrade(cfg, "head:-1", sql=True)
        return True
    except Exception:  # noqa: BLE001 - this is a boolean health check, not a propagating failure
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--target",
        choices=["migration", "runtime"],
        default="migration",
        help="Which configured URL to check: DATABASE_MIGRATION_URL (default) or DATABASE_URL.",
    )
    parser.add_argument(
        "--allow-production",
        action="store_true",
        help="Required to run this against a target where is_production is true.",
    )
    parser.add_argument(
        "--expect-staging",
        action="store_true",
        help=(
            "Refuse to proceed unless APP_ENV=staging and the target host is remote. "
            "Use before migrating a staging database so a stale local DSN fails loudly."
        ),
    )
    args = parser.parse_args()

    try:
        settings = get_settings()
    except ValidationError as exc:
        messages = [error["msg"] for error in exc.errors()]
        tls_messages = [m for m in messages if "sslmode" in m.lower() or "tls" in m.lower()]
        if not tls_messages:
            raise
        for message in tls_messages:
            logger.error(message)
        logger.info("Runtime TLS: FAIL (insecure sslmode)")
        logger.info("Migration TLS: FAIL (insecure sslmode)")
        return 5

    # Both configured targets are reported up front - which one gets an
    # actual connection attempt below depends on --target, but both must be
    # safe regardless of which is selected (requirement: TLS applies to
    # DATABASE_URL and DATABASE_MIGRATION_URL alike).
    if settings.requires_supabase_target:
        runtime_ok = _check_tls(
            settings.database_url,
            database_ssl_mode=settings.database_ssl_mode,
            app_env=settings.app_env,
            label="Runtime",
        )
        migration_ok = _check_tls(
            settings.database_migration_url,
            database_ssl_mode=settings.database_ssl_mode,
            app_env=settings.app_env,
            label="Migration",
        )
        if not (runtime_ok and migration_ok):
            return 5

    target_label = "Migration" if args.target == "migration" else "Runtime"
    target_url = (
        settings.database_migration_url if args.target == "migration" else settings.database_url
    )
    return run(
        target_url,
        allow_production=args.allow_production,
        expect_staging=args.expect_staging,
        target_label=target_label,
    )


if __name__ == "__main__":
    sys.exit(main())
