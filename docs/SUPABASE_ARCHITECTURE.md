# Supabase Database Architecture (Phase 2.5A)

## Scope

This phase adds Supabase Postgres as the staging/production database target,
while local development and the test suite keep using Docker Postgres. It
does **not** add Supabase Auth, Row Level Security, RAG, or Rasa - those
remain out of scope for later phases.

## Target matrix

| Environment | Database | Cache | Backend |
|---|---|---|---|
| local development | PostgreSQL (Docker Compose) | Redis (Docker Compose) | FastAPI, uvicorn |
| test (pytest) | SQLite (in-memory/file, per test) | none (Redis calls mocked or skipped) | FastAPI TestClient |
| staging | Supabase Postgres | Redis (wherever staging Redis is hosted - out of scope here) | FastAPI |
| production | Supabase Postgres | Redis | FastAPI |

The frontend is unaffected: it continues to call the FastAPI backend only.
It does not call Supabase directly and does not use the Supabase client SDK.
No Supabase credential of any kind is present in the frontend bundle.

## Why one schema, two databases

The same SQLAlchemy models, the same Alembic migrations (0001-0003), and the
same repository layer run against both targets. This works because:

- All three Phase 2 tables (`conversations`, `messages`,
  `security_scan_history`) use portable types: `sa.Uuid`, `sa.DateTime(timezone=True)`,
  and a `JSONVariant` helper that resolves to `JSONB` on Postgres (both Docker
  and Supabase are Postgres) - there is no Supabase-specific SQL anywhere in
  the schema.
- Nothing in the application queries Supabase-specific catalogs, RPC
  functions, or storage. It is plain SQLAlchemy against plain Postgres.
- The only thing that differs between targets is the **connection string**
  and whether **TLS** is required - both are environment configuration, never
  application code.

## Connection topology

```
                        APP_ENV=local|test              APP_ENV=staging|production
                        ------------------              ---------------------------
FastAPI (async engine)  ->  Docker Postgres         ->   Supabase Session Pooler
Alembic / seed / reset  ->  Docker Postgres         ->   Supabase direct connection
                             (same as above)              (DATABASE_MIGRATION_URL)
```

- **`DATABASE_URL`** is what the running application uses for every request.
  Against Supabase this should be the **Session Pooler** connection string
  (Supabase Dashboard -> Project Settings -> Database -> Connection string ->
  "Session pooler") - it is designed for a persistent backend holding a small
  pool of long-lived connections, which is exactly what `backend/database/session.py`
  does (`pool_size=5, max_overflow=5, pool_recycle=300`).
- **`DATABASE_MIGRATION_URL`** is what Alembic and the administrative
  scripts (`seed_demo.py`, `reset_demo.py`, `db_preflight.py`,
  `migrate_to_supabase.py`) use. Against Supabase this can be the **direct**
  connection (not pooled) since migrations run once per deploy, not per
  request, and don't benefit from pooling. If left unset, it falls back to
  `DATABASE_URL`.
- Both fall back to the existing `db_host`/`db_port`/`db_user`/`db_password`/`db_name`
  fields (the Docker Compose defaults) when unset - local development needs
  zero new configuration.

## Redis is unchanged

CVE lookup caching and rate limiting continue to use Redis exactly as before
(`backend/core/redis_client.py`, `backend/core/rate_limit.py`). Supabase does
not host Redis; this phase does not introduce a managed Redis dependency.
Where staging/production Redis is hosted is an infrastructure decision
outside this phase's scope - the application only needs `REDIS_URL`.

## What is explicitly NOT part of this phase

- **Supabase Auth**: the application keeps its existing minimal
  `get_current_actor()` seam (an unauthenticated, forgeable `X-Actor` header
  default) - see `docs/SECURITY.md`. No Supabase JWT verification, no user
  table.
- **Row Level Security (RLS)**: not enabled. Since the backend is the only
  writer/reader (the frontend never queries Postgres directly), RLS is not a
  meaningful boundary here - the FastAPI layer *is* the access-control layer.
  This is documented so it stays a deliberate decision, not an oversight.
- **RAG**: `backend/providers/rag/` still returns `NullRagRetriever` - unused
  in this phase, unaffected by the database change.
- **Rasa**: not introduced.

See `docs/SUPABASE_SETUP.md` for how to configure a real Supabase project,
`docs/SUPABASE_MIGRATION.md` for schema and data migration, `docs/SUPABASE_ROLLBACK.md`
for reverting, and `docs/SUPABASE_SECURITY.md` for the security posture.
