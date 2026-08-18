# Deployment (local Docker Compose — Phase 1/1.5 scope)

There is no hosted/cloud deployment target yet; this covers running the
full stack locally via Docker Compose, which is what the acceptance gate
actually exercises.

## Prerequisites

- Docker Desktop (Windows) with Docker Compose v2.
- PowerShell 5.1+ (built into Windows) for the `scripts\*.ps1` wrappers.

## Configuration

Copy `.env.example` to `.env` and fill in real values before any
non-local use. `Settings` (`backend/config/settings.py`) refuses to start
with `ENVIRONMENT=production` while `JWT_SECRET`, `SECRET_KEY`, or
`DB_PASSWORD` still hold default/empty values — this is enforced at
startup, not just documented.

## Start / stop / check

```powershell
scripts\Start-Project.ps1     # docker compose up -d --build
scripts\Check-Project.ps1     # curl-equivalent checks against all 4 services
scripts\Stop-Project.ps1      # docker compose down (keeps volumes)
```

## Full quality gate

```powershell
scripts\Run-Acceptance-Tests.ps1
```

Runs lint, tests+coverage (both stacks), security scanners (bandit,
pip-audit, npm audit, semgrep, Trivy fs + 2 images), Docker build/health/
persistence, seed idempotency, a real backup→restore cycle, and a k6
smoke test — 37 gates total. Add `-SkipSlowScans` to skip the Docker-based
scanners/k6 for a faster local iteration loop (not for the definitive
acceptance run).

## Images

| Service | Base image | Non-root | Notes |
|---|---|---|---|
| backend | `python:3.12-slim-bookworm` (multi-stage) | uid 10001 (`appuser`) | Phase 2.6: switched from Alpine to Debian slim because `onnxruntime` (a `fastembed` dependency) publishes zero musllinux wheels on PyPI for any release — Alpine cannot install it at all, not just at a CVE cost. Residual OS-CVE count (no-fix-available) re-measured after the switch — see `.ai/SECURITY_REPORT.md` and `.ai/DECISIONS.md`. |
| frontend | `nginxinc/nginx-unprivileged:1.27-alpine` | uid 101 (`nginx`) | `apk upgrade` at build time keeps OS packages current |
| postgres | `postgres:16.6-alpine` (pinned) | image default | internal-only, named volume |
| redis | `redis:7.4-alpine` (pinned), AOF enabled | image default | internal-only, named volume |

## Hardening applied (docker-compose.yml)

- `security_opt: no-new-privileges:true` on all 4 services.
- `read_only: true` + `tmpfs` for `/tmp` (backend, frontend) — stateless
  services never write to their own image filesystem at runtime.
- `mem_limit` / `cpus` resource caps on every service (see
  `docs/PERFORMANCE.md` for how this shapes load-test results at scale).
- PostgreSQL/Redis have no host port mapping — reachable only from
  `backend` over the internal Docker network.
- `.dockerignore` (both images) excludes `.venv`, `node_modules`,
  `__pycache__`, test/coverage artifacts, and `.env`.

## Persistence

Named volumes (`postgres_data`, `redis_data`) survive
`docker compose restart` and `docker compose down` (without `-v`) —
verified for real in every acceptance run (insert → restart → confirm
still present).

### Local embedding model cache (Phase 2.6)

The backend container is `read_only: true` with only `/tmp` as `tmpfs`, but
`fastembed`'s ONNX model (and `huggingface_hub`'s own cache/lockfiles,
written under `HF_HOME` regardless of `EMBEDDING_CACHE_DIR`) are downloaded
lazily on first embed, not baked into the image. `docker-compose.yml` maps
a dedicated named volume, `embedding_cache`, onto `/app/.cache` (owned by
`appuser`, uid 10001, at image build time) to give both caches a writable,
restart-persistent home without weakening the read-only root filesystem.
Verified live: first embed downloads the model (~240 MB) from Hugging Face;
a subsequent container restart reuses the cached model with no re-download.

Network/download failures during the first embed surface as
`ProviderUnavailableError` ("The local embedding model could not be
loaded.") rather than hanging — `fastembed`'s own retry/backoff applies, and
the error propagates through the normal RAG error path.

## Backup / restore

See [`docs/BACKUP_RESTORE.md`](BACKUP_RESTORE.md).

## Rollback

No rolling/blue-green deployment exists yet at this phase (single
`docker compose up -d --build` target). To roll back: `git checkout` the
previous commit and re-run `docker compose up -d --build`; `docker compose down`
does not touch the named volumes, so data survives a rollback.
