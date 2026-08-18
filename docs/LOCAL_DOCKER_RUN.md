# Running CyberSec Assistant locally with Docker Compose

## The one canonical command

```powershell
cd "D:\đồ án1"
docker compose up -d --build
```

Then open <http://localhost:3000> and click **ENTER LOCAL MODE** on the
login screen.

That is the entire setup. No `.env` file, no `npm install`/`npm run dev`,
no `uvicorn`, no `alembic upgrade head`, no token-minting script, no
hosted Supabase project, and no internet access beyond the one-time model
download described below.

## What happens automatically

`docker compose up -d --build` builds and starts four services:

1. **postgres** (`pgvector/pgvector:pg16`) - Postgres with the `vector`
   extension pre-installed. Data persists in the named volume
   `postgres_data`.
2. **redis** - used for CVE-lookup caching and rate limiting.
3. **backend** (FastAPI) - on startup, its entrypoint
   (`backend/entrypoint.sh`) runs `alembic upgrade head` first and only
   starts the API if every migration succeeds (revisions `0001` through
   `0005`, including enabling `pgvector` and creating the RAG tables). The
   local embedding model (FastEmbed/ONNX Runtime) is downloaded and
   initialized the first time it's actually used (first chat message or
   first document upload), not at container startup, so `docker compose
   up` itself finishes quickly.
4. **frontend** (nginx serving a production Vite build) - reverse-proxies
   `/api/*` to the backend so the browser only ever talks to
   `localhost:3000`, same-origin.

Every service has a real health check (not just "is the process alive");
`frontend` waits for `backend` to report healthy before it's considered
ready, and `backend` waits for `postgres`/`redis`.

## Local Mode: signing in with no hosted auth

This project's real login form talks to a hosted Supabase Auth project.
Nothing in a local `docker compose` checkout has that configured - by
design, so nobody has to create one just to try the app locally.

The **ENTER LOCAL MODE** button on the login screen instead calls
`POST /api/auth/local-session`, a small backend endpoint that:

- creates (or reuses) one fixed local demo user,
- mints a backend-verifiable session token,
- and is **hard-disabled outside `APP_ENV=local`** - it returns HTTP 404
  in any staging/production deployment, regardless of other settings. See
  `backend/api/local_auth.py` and its regression tests in
  `backend/tests/test_local_auth.py`.

If you *do* have a real hosted Supabase project and want to use it
instead, create `.env` (backend) / `frontend/.env` (frontend) with your
real values - this is entirely optional and the app works identically
without it.

## First-run timing

- **First `docker compose up -d --build` ever**: several minutes, mostly
  spent downloading base images and building the frontend/backend images.
  Every later run reuses Docker's build cache and is much faster.
- **First document you upload / first chat message**: the backend starts
  warming the AI embedding model in the background as soon as it starts up
  (not blocking anything else), so this is usually already done by the
  time you click anything. If it isn't, the Knowledge Base page shows a
  clear "Đang khởi tạo mô hình AI lần đầu" banner instead of a silent
  hang - upload still works, just slower on that one request (observed up
  to ~90s on a genuinely fresh `embedding_cache` volume; every later
  request is fast). See `docs/LOCAL_HEALTHCHECK.md` for exactly how this
  readiness state works and how to check it directly
  (`/api/system/health`'s `embedding` field).

## Data persistence

Documents, conversations, scan history, and the embedding model cache all
live in named Docker volumes (`postgres_data`, `embedding_cache`) that
survive `docker compose down`, `docker compose restart`, and normal
container restarts. Only `docker compose down -v` removes them.

## Ports

- `http://localhost:3000` - the website (bound to `127.0.0.1` and `[::1]`
  only, not reachable from other machines on your network).
- `http://localhost:8000` - the backend API directly (also
  loopback-only), useful for debugging with `curl` or the interactive
  API docs at `http://localhost:8000/docs`. The frontend never needs this
  directly - it talks to the backend through nginx's `/api/` proxy.
- Postgres and Redis are **not** published to the host at all - only
  reachable from other containers on the stack's own internal Docker
  network.

## If the app can't reach the backend

The frontend detects a real backend/database outage or a browser going
offline and shows a live "Connection Recovery" page (`/offline`) instead of
hanging or showing fake data - it auto-recovers you back to where you were
once things come back up. See `docs/LOCAL_TROUBLESHOOTING.md`.

## Diagnostics, backups, and log rotation

- `scripts\Check-Project.ps1` - read-only local diagnostics; see
  `docs/LOCAL_HEALTHCHECK.md`.
- `scripts\Backup-Database.ps1` / `scripts\Restore-Database.ps1` - see
  `docs/LOCAL_BACKUP_RESTORE.md`.
- Every container's logs are capped (`json-file`, 10MB per file, 3 files
  kept) so a long-running local stack never grows its logs unbounded.
