# Troubleshooting the local Docker Compose stack

## Something seems wrong and I don't know where to start

```powershell
cd "D:\đồ án1"
powershell -File scripts\Check-Project.ps1
```

Read-only diagnostics: Docker Desktop reachability, every container's
health/restarts/memory, real backend readiness (database, Redis,
migration, pgvector, Local Mode secret), embedding warm-up state, volume
disk usage, and recent error log lines - ending in an overall
`HEALTHY`/`DEGRADED`/`FAILED` verdict. See `docs/LOCAL_HEALTHCHECK.md` for
what each check actually means. Never modifies anything.

## `docker compose up -d --build` fails with a port conflict

Something else is already using port `3000` or `8000` on your machine -
possibly an older run of this same stack under a different project name,
or an unrelated app. Check what's running:

```powershell
docker ps
```

Stop the conflicting stack (without deleting its data):

```powershell
docker compose down
```

Then retry `docker compose up -d --build`.

## The first upload/chat message seems to hang

This is expected the very first time - see `docs/LOCAL_DOCKER_RUN.md`'s
"First-run timing" section. The AI embedding model is being loaded into
memory for the first time, which can take 20-90 seconds depending on your
machine. The upload button shows "UPLOADING..." (disabled) the whole time,
and a hint appears below it. Every upload after that is fast.

If it still hasn't finished after several minutes, check the backend logs:

```powershell
docker compose logs backend --tail 100
```

## "ENTER LOCAL MODE" doesn't work / redirects back to login

Check that the backend is healthy:

```powershell
docker compose ps
```

If `backend` isn't `healthy`, check its logs (`docker compose logs backend`)
for a migration failure or startup error. Local Mode also only works when
`APP_ENV` is `local` (the default - nothing to configure). If you've set
`APP_ENV=staging` or `production` in a `.env` file for another reason,
Local Mode is intentionally disabled in those environments.

## I want to reset everything and start from scratch

```powershell
docker compose down -v
docker compose up -d --build
```

**`-v` deletes all local data** - every uploaded document, conversation,
and the downloaded embedding model cache. Only use this if you actually
want a clean slate; the next `docker compose up -d --build` will need to
re-download the embedding model and re-run every migration from scratch.

## Checking service health directly

```powershell
docker compose ps                                    # overall status
curl http://localhost:8000/health                     # backend liveness
curl http://localhost:8000/api/system/health           # backend + DB + Redis
curl http://localhost:3000/health                      # frontend/nginx
```

## The app redirected me to a "Connection Recovery" / `/offline` page

This means the frontend genuinely could not reach a working backend right
now - not a bug page, a real live check. It distinguishes:

- **No Network Connection** - your browser itself is offline.
- **Backend Server Unreachable** - the backend container is down/restarting.
- **System Degraded** - the backend answered, but PostgreSQL isn't healthy.

It polls automatically and returns you to the page you were on the moment
things recover - no action needed, but "RETRY CONNECTION" re-checks
immediately. If it's stuck, check `docker compose ps` and the relevant
container's logs. A dependency that's merely degraded but not required for
the current page (e.g. Redis, which only backs rate limiting) does **not**
trigger this page - most of the app keeps working.

## I need to back up or restore my local data

See `docs/LOCAL_BACKUP_RESTORE.md`. Short version:
`scripts\Backup-Database.ps1` writes a timestamped dump to
`backups\local\`; `scripts\Restore-Database.ps1 -BackupFile <path>`
safety-backs up the current state first and verifies the dump in a
disposable database before touching your real data.

## Using a real hosted Supabase project instead of Local Mode

Create `.env` (backend, repo root) and `frontend/.env` with your project's
real values (see `.env.example` / `frontend/.env.example` for the expected
variable names), then `docker compose up -d --build` again to pick them
up. This is entirely optional - the app works fully without it via Local
Mode.
