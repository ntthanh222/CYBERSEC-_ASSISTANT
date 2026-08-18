"""Optional one-shot data mover: local Docker Postgres -> Supabase Postgres.

Dry-run by default. Both source and target URLs must be passed explicitly
(never read from a "current" settings object) so this can never accidentally
run against whatever DATABASE_URL happens to be configured - the caller has
to name both ends on the command line every time.

Copies, in FK-safe order, conversations -> messages -> security_scan_history.
Each table is copied inside its own transaction: a mid-table failure rolls
back that table's inserts and stops (later tables are not attempted), so the
target is never left with orphaned messages referencing a half-copied
conversation batch.

Duplicate-safe: every insert is `ON CONFLICT (id) DO NOTHING`, so re-running
this tool against a target that already has some or all of the rows is a
no-op for those rows, not an overwrite and not an error. This also means it
is safe to interrupt and re-run.

Never deletes anything from the source. Never touches rows in the target
that are not part of this copy (no UPDATE, ever - only INSERT ... DO NOTHING).
"""
import argparse
import logging
import sys

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from backend.core.db_retry import pg_connect_args
from backend.core.dsn import redact_dsn

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("migrate_to_supabase")

# Order matters: messages.conversation_id -> conversations.id (FK), so
# conversations must land first. security_scan_history has no FK to the
# other two and no ordering constraint relative to them.
TABLES_IN_ORDER = ["conversations", "messages", "security_scan_history"]


def _count(engine, table: str) -> int:
    # table is always one of TABLES_IN_ORDER, never caller/user input.
    with engine.connect() as conn:
        query = text(  # noqa: S608  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text -- table names are fixed server-side constants
            f"SELECT COUNT(*) FROM {table}"  # nosec B608
        )
        return conn.execute(query).scalar_one()


def _copy_table(source_engine, target_engine, table: str, dry_run: bool) -> tuple[int, int]:
    """Return (rows_read, rows_inserted). rows_inserted is 0 in dry-run mode."""
    with source_engine.connect() as source_conn:
        query = text(  # noqa: S608  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text -- table names are fixed server-side constants
            f"SELECT * FROM {table}"  # nosec B608
        )
        rows = source_conn.execute(query).mappings().all()

    if not rows:
        logger.info("%s: 0 rows in source, nothing to copy", table)
        return 0, 0

    if dry_run:
        logger.info("%s: [dry-run] would copy %d row(s)", table, len(rows))
        return len(rows), 0

    columns = list(rows[0].keys())
    col_list = ", ".join(columns)
    param_list = ", ".join(f":{c}" for c in columns)
    # table is always one of TABLES_IN_ORDER (module constant), never
    # caller/user input; column names come from the source row's own keys,
    # and values are bound as params (:col), never interpolated.
    insert_sql = text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text -- fixed tables and schema keys
        f"INSERT INTO {table} ({col_list}) VALUES ({param_list}) "  # noqa: S608 # nosec B608
        "ON CONFLICT (id) DO NOTHING"
    )

    inserted = 0
    with target_engine.begin() as target_conn:
        for row in rows:
            result = target_conn.execute(insert_sql, dict(row))
            inserted += result.rowcount or 0

    logger.info(
        "%s: read %d row(s), inserted %d new row(s) (rest already present)",
        table,
        len(rows),
        inserted,
    )
    return len(rows), inserted


def run(source_url: str, target_url: str, dry_run: bool) -> int:
    logger.info("source: %s", redact_dsn(source_url))
    logger.info("target: %s", redact_dsn(target_url))
    logger.info("mode: %s", "DRY RUN (no writes)" if dry_run else "LIVE (will write to target)")

    source_engine = create_engine(
        source_url, pool_pre_ping=True, connect_args=pg_connect_args(source_url)
    )
    target_engine = create_engine(
        target_url, pool_pre_ping=True, connect_args=pg_connect_args(target_url)
    )

    try:
        before_counts = {t: _count(target_engine, t) for t in TABLES_IN_ORDER}
        logger.info("target row counts before: %s", before_counts)

        for table in TABLES_IN_ORDER:
            try:
                _copy_table(source_engine, target_engine, table, dry_run)
            except SQLAlchemyError as exc:
                logger.error(
                    "%s: copy failed and was rolled back (%s) - stopping, "
                    "later tables not attempted",
                    table,
                    type(exc).__name__,
                )
                return 1

        after_counts = {t: _count(target_engine, t) for t in TABLES_IN_ORDER}
        logger.info("target row counts after: %s", after_counts)
    finally:
        source_engine.dispose()
        target_engine.dispose()

    logger.info("done.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-url", required=True, help="Source Postgres DSN (e.g. local Docker)."
    )
    parser.add_argument(
        "--target-url", required=True, help="Target Postgres DSN (e.g. Supabase)."
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually write to the target. Without this flag, runs a dry-run (default).",
    )
    args = parser.parse_args()
    return run(args.source_url, args.target_url, dry_run=not args.execute)


if __name__ == "__main__":
    sys.exit(main())
