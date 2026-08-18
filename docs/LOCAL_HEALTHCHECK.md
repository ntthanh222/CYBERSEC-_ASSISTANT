# Health, readiness, and diagnostics (local Docker stack)

## Three separate signals, on purpose

The backend exposes two endpoints that answer different questions. Mixing
them together (as many apps do) means a slow dependency ends up restarting
a perfectly healthy process, or a genuinely broken process keeps answering
"OK". This project keeps them apart:

| Endpoint | Question it answers | Touches Postgres/Redis? |
|---|---|---|
| `GET /health` | Is the backend process alive at all? | No - dependency-free, always fast. This is what Docker's own `healthcheck:` on the `backend` service calls. |
| `GET /api/system/health` | Is the backend actually able to do its job right now? | Yes - real round trips. |

`/api/system/health` returns a real per-dependency breakdown under
`checks`, never a hardcoded "healthy":

- **`database`** - `SELECT 1` against Postgres.
- **`redis`** - a real `PING`.
- **`migration`** - reads `alembic_version` and compares it against the
  Alembic head this backend build expects (`0005`). If the schema is
  stale or the migration table is missing, this reports `unavailable` -
  the backend will never claim to be healthy while serving requests
  against the wrong schema.
- **`pgvector`** - confirms the `vector` Postgres extension is actually
  installed (`pg_extension`), not just that migration `0005` claims to
  have run.
- **`local_auth_secret`** - confirms Local Mode actually has a usable
  JWT-signing secret: either the runtime-generated one persisted to disk
  (see `docs/LOCAL_DOCKER_RUN.md`), **or** a real `SUPABASE_JWT_SECRET`
  was supplied instead (in which case the file is deliberately never
  written - checking for the file alone would wrongly flag that
  perfectly valid configuration as broken). Reports `unknown` (not
  `unavailable`) outside `APP_ENV=local`/`test`, since staging/production
  never create this file at all - that's
  correct, not a failure.

The overall `status` field aggregates these (`healthy` / `degraded` /
`unavailable`), ignoring any `unknown` entries so a not-applicable check
never drags a genuinely healthy stack down.

## Embedding readiness: a third, separate axis

A brand-new container's first document upload or chat message also has to
load the local AI embedding model into memory - the first time this
happens on a fresh `embedding_cache` volume it can also download the model
from Hugging Face Hub, observed taking up to ~90 seconds. This is
deliberately **not** folded into `overall_status`: the rest of the
site (dashboard, security tools, auth) works completely normally while
this warms up, so treating it as a "degraded" dependency would be
misleading.

Instead, `/api/system/health`'s `embedding` field reports its own
independent state:

```json
"embedding": { "status": "warming", "elapsed_seconds": 12.4, "error": null }
```

`status` is one of `not_started` / `warming` / `ready` / `failed`. The
backend starts warming this in the background at process startup
(`backend/main.py`'s `_warmup_embedding_model`) so it's usually already
`ready` by the time a real user clicks anything - but if it isn't, the
Knowledge Base page shows a clear "Đang khởi tạo mô hình AI lần đầu"
banner (see `frontend/src/hooks/useEmbeddingReadiness.ts`) instead of a
silent hang or a confusing upload failure. Uploads still work while
warming; they're just slower on that first request.

## `scripts/Check-Project.ps1` - read-only local diagnostics

```powershell
cd "D:\đồ án1"
powershell -File scripts\Check-Project.ps1
```

Never starts, stops, restarts, or otherwise mutates anything - every
command it runs is a read (`docker ps`/`inspect`/`stats`, `docker system
df`, HTTP `GET`). It reports:

- Docker Desktop reachability.
- Each container's `state`/`health`/`RestartCount`/`StartedAt` and current
  CPU/memory.
- The liveness and readiness endpoints above, including every individual
  dependency check and the embedding-readiness state.
- Frontend reachability.
- This project's own volume disk usage (scoped to the running Compose
  project's own volumes - it never lists other, unrelated projects on the
  same machine).
- The last 20 `ERROR`/`CRITICAL`/`FATAL` log lines per container, if any.
- A final `OVERALL: HEALTHY` / `DEGRADED` / `FAILED` verdict, with a
  non-zero exit code on `FAILED` so it's usable in a script.

It never prints a secret, token, password, or connection string - only
aggregated status fields and container metadata.

## Nginx timeout

`frontend/nginx.conf`'s proxy timeout for `/api/` is 120 seconds - enough
margin over the real measured cold-start (~90s) without being effectively
infinite. A request that's still cold-starting the embedding model gets a
real answer within that window, not a silent hang.
