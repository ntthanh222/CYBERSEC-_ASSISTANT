# Supabase Migration (Phase 2.5A)

Two separate things are called "migration" here - keep them distinct:

1. **Schema migration**: running Alembic (`0001` -> `0002` -> `0003`)
   against a Supabase database so its schema matches the application.
2. **Data migration**: optionally copying existing rows from a local Docker
   Postgres into Supabase, using `backend/scripts/migrate_to_supabase.py`.

Do the schema migration first, always. The data migration tool assumes the
target's tables already exist.

## Schema migration

### Preconditions

- `DATABASE_MIGRATION_URL` set to the Supabase **direct** connection string
  (see `docs/SUPABASE_SETUP.md`).
- You have run `docs/SUPABASE_ROLLBACK.md`'s backup step if this is not a
  brand-new database.

### Step 1: preflight (read-only)

```bash
python -m backend.scripts.db_preflight --target migration
```

Reports (never printing a credential):

- the target host and database name, and a redacted DSN
- whether `sslmode` is configured (should be `require` for Supabase)
- the current Alembic revision - `unstamped` for a brand-new database
- which of the expected tables (`schema_bootstrap`, `demo_seed_marker`,
  `conversations`, `messages`, `security_scan_history`) already exist
- whether any **forbidden** table (`users` - the quarantined Auth work)
  exists. If this reports present, stop and investigate before migrating
  anything - it means unrelated/unapproved schema has already landed on
  this target.
- whether Alembic can render a downgrade script for the current head
  without connecting

Exit code `2` means it could not connect at all - check the DSN and network
path before doing anything else. Exit code `1` means it refused to run
because `APP_ENV=production` and `--allow-production` was not passed.

### Step 2: run the migration

```bash
python -m alembic -c backend/alembic.ini upgrade head
```

Alembic reads `DATABASE_MIGRATION_URL` via `settings.database_migration_url`
(`backend/database/migrations/env.py`) - it never touches the pooled
`DATABASE_URL`.

### Step 3: verify

```bash
python -m alembic -c backend/alembic.ini current
python -m alembic -c backend/alembic.ini history
```

Expected: `0003 (head)`. Then re-run the preflight script - it should now
report all five expected tables present, zero forbidden tables, and
`downgrade_ok: True`.

### What "clean" and "existing" both mean here

This exact sequence has been run for real, twice, against a fresh Docker
Postgres in this phase's own verification (see `PHASE_2_5A_SUPABASE_REPORT.md`):

- **Clean**: a brand-new database, `alembic upgrade head` from nothing,
  lands at `0003`.
- **Existing**: the same database, `alembic upgrade head` run a second time,
  is a no-op (Alembic sees it is already at head and does nothing) - safe to
  re-run, e.g. as part of a deploy script that always runs migrations.

The same behavior is expected against Supabase since it is the same
Postgres dialect and the same migration files - `docs/CHATBOT_SUPABASE_VALIDATION.md`
is where that gets confirmed for real once credentials are available.

## Data migration (optional)

Use `backend/scripts/migrate_to_supabase.py` only if you have existing rows
in a Docker Postgres you want carried over (e.g. moving a long-running local
demo environment to staging). A fresh staging/production database does not
need this step.

### Dry run first, always

```bash
python -m backend.scripts.migrate_to_supabase \
  --source-url postgresql+psycopg://cybersec:change-me@localhost:5432/cybersec_assistant \
  --target-url <supabase-direct-or-migration-url>
```

Without `--execute`, this only reports what it *would* copy - zero writes.
Read the row counts before adding `--execute`.

### Live run

```bash
python -m backend.scripts.migrate_to_supabase \
  --source-url <source-url> \
  --target-url <target-url> \
  --execute
```

Properties (see the script's own docstring for the full explanation):

- Copies `conversations` -> `messages` -> `security_scan_history`, in that
  order (FK-safe: messages reference conversations).
- Each table's insert runs inside its own transaction; a failure rolls back
  that table's writes and stops before touching the next table.
- Every insert is `INSERT ... ON CONFLICT (id) DO NOTHING` - re-running the
  tool against a target that already has some or all rows is a no-op for
  those rows, never an overwrite, never an error. Safe to interrupt and
  re-run.
- Never deletes or modifies the source.
- Prints row counts before and after, and never prints a password (DSNs are
  redacted via `backend.core.dsn.redact_dsn`).

### Passwords are never migrated

There is nothing to migrate here by design - `security.md`'s invariant that
passwords are never persisted anywhere applies identically before and after
this phase. The Password Checker remains fully stateless.
