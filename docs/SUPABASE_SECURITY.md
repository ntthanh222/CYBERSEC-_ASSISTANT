# Supabase Security (Phase 2.5A)

This extends `docs/SECURITY.md`'s existing posture (SSRF protection,
password statelessness, redaction, minimal actor abstraction) to cover what
changes with a Supabase database target. Everything already documented
there still holds unchanged - this file only covers the delta.

## Secrets

| Variable | Where it may live | Where it must never live |
|---|---|---|
| `DATABASE_URL`, `DATABASE_MIGRATION_URL` | backend process environment (staging/production secret store) | Git, frontend bundle, logs, error responses |
| `SUPABASE_SECRET_KEY` | backend process environment, only if a future phase needs it | Git, frontend bundle (**no** `VITE_` prefix - ever), logs |
| `SUPABASE_PUBLISHABLE_KEY` | reserved; unused in this phase | still not committed as a matter of hygiene, even though Supabase itself designs this key to be public-safe |

Verified in this phase:

- `git grep` across the repo for the literal strings used in local testing
  (e.g. `secret-pass`, real-looking Supabase host fragments) finds nothing
  committed - `.env` is gitignored and was never staged.
- `REDACT_KEYS` in `backend/core/logging.py` now includes
  `database_migration_url`, `supabase_secret_key`, and
  `supabase_service_role_key` (defense in depth - Supabase's own docs use
  both `secret key` and, in older projects, `service_role key` naming), in
  addition to the pre-existing `database_url`.
- A dedicated redaction path (`backend/core/dsn.py::redact_dsn`) strips
  `user:password@` from any raw DSN string before it can reach a log line -
  this matters because a DSN is not a dict value keyed `"password"`, so the
  dict-based `REDACT_KEYS` mechanism alone would not catch it. Both
  `db_preflight.py` and `migrate_to_supabase.py` use this before logging a
  target.
- `frontend/` has zero `VITE_`-prefixed environment variable usage anywhere
  in `src/` (confirmed via `grep -rn "VITE_\|import.meta.env" frontend/src`)
  - there is no code path by which a Supabase key could reach the frontend
    bundle, and the production build's output was checked for the literal
    string `supabase` and found none.

## Transport security

- `DATABASE_SSL_MODE=require` is documented as required for Supabase in
  `.env.example` and `docs/SUPABASE_SETUP.md`.
- `backend/config/settings.py` logs (via `db_preflight.py`) a warning - not
  a hard failure, since local Docker Postgres legitimately has no TLS
  configured - when `APP_ENV` is `staging`/`production` and no `sslmode` is
  present on the DSN.
- Supabase's pooler and direct connections both terminate TLS by default;
  `sslmode=require` on the client side ensures the driver refuses to fall
  back to plaintext if that ever changed.

## SQL injection

- All query parameters (row values, ids) go through SQLAlchemy's bound
  parameters (`text(...).execute(dict(...))`) everywhere, including the new
  `migrate_to_supabase.py` tool - never Python string interpolation of a
  value into SQL.
- Table names in `migrate_to_supabase.py` and `db_preflight.py` are
  interpolated into SQL text, but only ever from `TABLES_IN_ORDER` /
  `EXPECTED_TABLES` - fixed literal lists in the script's own source, never
  from a CLI argument or any other external input. Bandit's B608 warning on
  these lines is a false positive for that reason and is suppressed inline
  with a comment explaining why (`# nosec B608`), not silently.

## Access control (what did *not* change)

- No Supabase Auth, no Row Level Security. The backend remains the sole
  reader/writer of Postgres; the frontend never queries it directly. RLS
  would be security theater here - there is no second, less-trusted client
  querying the same tables to defend against - and enabling it without a
  real multi-tenant/multi-role model would just add operational risk
  without a corresponding security benefit. This is a deliberate decision,
  revisit if/when a future phase adds a client that talks to Supabase
  directly.
- The existing minimal `get_current_actor()` seam (`backend/core/actor.py`)
  is unchanged: still an optional, forgeable `X-Actor` header, still
  documented as **not a security control**, still defaulting to
  `"anonymous"`. Every Phase 2 endpoint remains unauthenticated in
  development, staging, and production alike, exactly as before this
  phase - Phase 2.5A does not narrow or widen that.

## Docker/network exposure (unaffected, re-verified)

- Local Docker Postgres and Redis are still not published to the host
  (`docker port <container>` returns nothing for either) - re-confirmed
  live during this phase's Database Matrix A verification.
- Supabase Postgres is reached over the internet by design (it is a managed
  service) - the mitigation is TLS (`sslmode=require`) plus Supabase's own
  network-level controls (IP allow-listing, if configured on the project),
  not host firewalling this backend does not control.

## Backups

- `docs/SUPABASE_ROLLBACK.md`'s `pg_dump` step produces a file containing
  real row data - treat it as sensitive. The command itself does not put a
  password in the dump's filename or in `pg_dump`'s own log output (the
  connection string is passed as a single argument, not echoed).
