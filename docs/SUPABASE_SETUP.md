# Supabase Setup (Phase 2.5A)

## When you need this

Only when standing up staging or production. Local development does not
need a Supabase project - the Docker Compose Postgres default keeps working
with zero configuration, exactly as in Phase 1.5/2.

## 1. Create the Supabase project

Create a project in the Supabase dashboard. Note the project's database
password at creation time - it is only shown once.

## 2. Get the connection strings

From **Project Settings -> Database -> Connection string**:

- **Session pooler** URI -> use for `DATABASE_URL`. This is what the running
  backend uses for every request; it is designed for many short-lived
  connections from a persistent app, which matches this backend's connection
  pool (`pool_size=5, max_overflow=5`).
- **Direct connection** URI -> use for `DATABASE_MIGRATION_URL`. Migrations
  run once per deploy and don't need pooling; a direct connection also
  avoids any pooler-specific limitation on `CREATE TABLE`/`ALTER TABLE`
  during a migration.

Both URIs come in the form:

```
postgresql://postgres.<project-ref>:<password>@<host>:<port>/postgres
```

Rewrite the scheme to `postgresql+psycopg://` (this backend uses psycopg3
via SQLAlchemy, not the plain `postgresql://` driver) - everything else
about the URI is unchanged:

```
postgresql+psycopg://postgres.<project-ref>:<password>@<host>:<port>/postgres
```

### Percent-encode special characters in the password

A connection string is a URI, so any RFC-3986-reserved character in the
password must be percent-encoded — otherwise the URI parse shifts and the
driver reports a *misleading* error ("could not translate host name",
"invalid integer value for port") that points at the wrong thing entirely.

Characters that must be encoded: `@` → `%40`, `/` → `%2F`, `?` → `%3F`,
`#` → `%23`, `[` → `%5B`, `]` → `%5D`, `%` → `%25`, `"` → `%22`, and a
literal space → `%20`.

`db_preflight.py` checks this before attempting any connection and reports
the offending *character class* (never the password itself), so a bad
encoding fails immediately and legibly rather than as a confusing network
error. The simplest way to avoid the issue entirely is to choose a
generated password with no URI-special characters.

## 3. Configure environment variables

In your staging/production environment (never in a committed file):

```
APP_ENV=staging               # or production
DATABASE_URL=postgresql+psycopg://postgres.<ref>:<password>@<pooler-host>:5432/postgres
DATABASE_MIGRATION_URL=postgresql+psycopg://postgres.<ref>:<password>@<direct-host>:5432/postgres
DATABASE_SSL_MODE=require
```

`APP_ENV=staging` or `production` makes the app **refuse to start** if
`DATABASE_URL` is not set - see `backend/config/settings.py`'s
`_require_explicit_target_for_staging_and_production` validator. This is
intentional: a staging process silently falling back to the Docker default
DSN is a worse failure mode than refusing to start.

`SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, and `SUPABASE_SECRET_KEY` are
reserved for future direct Supabase API/tooling use - the application itself
does not call the Supabase client SDK in this phase, so they are optional.
If you do set `SUPABASE_SECRET_KEY`, treat it exactly like `DB_PASSWORD`:
backend-only, never prefixed `VITE_`, never committed, never logged (it is
in `REDACT_KEYS` - see `docs/SUPABASE_SECURITY.md`).

## 4. Run the preflight check

Before running any migration against a new target, run:

```bash
DATABASE_MIGRATION_URL=<your-supabase-direct-url> \
  python -m backend.scripts.db_preflight --target migration --expect-staging
```

`--expect-staging` refuses to proceed unless `APP_ENV=staging` **and** the
target host is remote — so a stale local DSN (or a forgotten `APP_ENV`)
fails loudly instead of quietly reporting on the Docker database while you
believe you are looking at Supabase. Drop the flag only when deliberately
inspecting a local target.

This is read-only - it reports the target host, whether SSL is configured,
the current Alembic revision (or "unstamped" for a brand-new database),
which of the expected Phase 0-2 tables exist, and whether a downgrade script
renders cleanly. It never modifies the database. See
`docs/SUPABASE_MIGRATION.md` for what to do with its output.

## 5. Run the migration

```bash
DATABASE_MIGRATION_URL=<your-supabase-direct-url> \
  python -m alembic -c backend/alembic.ini upgrade head
```

Expected result: revision `0003` (head). See `docs/SUPABASE_MIGRATION.md`
for full detail, including what a clean run looks like and how to verify it.

## 6. Verify the application

Point a real backend instance at the new `DATABASE_URL` and run through
`docs/CHATBOT_SUPABASE_VALIDATION.md`'s checklist - conversation create,
message persistence, listing, deletion, and a restart-survives-data check.

## Local development is unaffected

None of the above is required to run `docker compose up` locally. Leaving
`DATABASE_URL`, `DATABASE_MIGRATION_URL`, and `DATABASE_SSL_MODE` unset
(the default in `.env.example`) keeps using the Docker Postgres service
exactly as before this phase.
