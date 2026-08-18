# Supabase Rollback (Phase 2.5A)

## Before you migrate: back up

Supabase projects on a paid plan have point-in-time recovery; free-tier
projects do not. Do not rely on that alone. Before running a schema
migration against a Supabase database that already has data:

```bash
pg_dump "<DATABASE_MIGRATION_URL>" --format=custom --file=backup-$(date +%Y%m%dT%H%M%S).dump
```

Store the dump outside the repository. **The dump file's name and contents
may contain data but the command above does not embed the password in the
filename** - the connection string itself is still a secret; do not commit
it, log it, or paste it into an issue tracker. Treat the dump file itself as
sensitive (it contains real row data) and store it somewhere access-controlled.

## Rolling back a schema migration

Alembic's downgrade path is exercised by the preflight script
(`db_preflight.py`'s `downgrade_ok` check renders the SQL without running
it) before you ever need to run it for real. To actually roll back:

```bash
python -m alembic -c backend/alembic.ini downgrade -1
```

This reverses exactly one revision (e.g. `0003` -> `0002`). Migration 0003's
`downgrade()` drops `security_scan_history`, `messages`, and `conversations`
in FK-safe order (children before parents) - this is destructive to any data
in those tables. If you need the data back, restore from the `pg_dump` taken
above; there is no soft-undo.

To go further back:

```bash
python -m alembic -c backend/alembic.ini downgrade 0001
```

Never downgrade past `0001` (`base`) on a database still in use - it drops
`schema_bootstrap`, the bootstrap table every later migration's `env.py`
setup assumes exists.

## Rolling back a data migration (`migrate_to_supabase.py`)

There is no automatic rollback for the data-copy tool, by design - it only
ever performs `INSERT ... ON CONFLICT DO NOTHING`, never `DELETE` or
`UPDATE`, so:

- If the tool copied rows you did not want on the target, delete them
  manually by id (the tool logs which ids it read from the source - keep
  that log). This is a manual, deliberate step; the tool will not do it for
  you, matching its "never overwrite/never touch existing target data"
  invariant.
- If a partial copy occurred (the tool stopped after a table failed), the
  already-copied earlier tables are left in place (they are valid rows, not
  corrupt state) - you can safely re-run the tool once the underlying issue
  (e.g. connectivity) is fixed; the `ON CONFLICT DO NOTHING` insert makes
  the re-run pick up only what is still missing.

## Rolling back the application's target (not the database)

If a deploy pointed `DATABASE_URL`/`DATABASE_MIGRATION_URL` at Supabase and
you need to revert to the Docker Postgres target: unset both variables (or
point them back at the previous Docker connection string) and restart the
backend. No code change is required - `backend/config/settings.py` falls
back to the `db_*` fields whenever `DATABASE_URL` is empty. `APP_ENV` should
also be set back to `local`/`test` if this is a genuine revert to local
development, since `staging`/`production` refuse to start without an
explicit `DATABASE_URL`.

## Never do this on a target with real data

- `docker compose down -v` (drops the Docker volume - only relevant to the
  local target, but listed here as a reminder it is never appropriate
  against anything with data you care about)
- `alembic downgrade base` against a database with real conversations, scan
  history, or anything you have not already backed up
- Re-running `migrate_to_supabase.py --execute` with source/target swapped
  by mistake - always read the logged "source:" / "target:" lines before
  confirming a live run
