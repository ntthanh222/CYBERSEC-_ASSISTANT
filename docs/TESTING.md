# Testing

## Backend

```powershell
.\.venv\Scripts\python.exe -m pytest -q --cov=backend --cov-report=term-missing
```

- Framework: pytest + pytest-asyncio + pytest-cov.
- Coverage gate: `.coveragerc` enforces `fail_under = 90`.
- Lint: `.\.venv\Scripts\python.exe -m ruff check backend`.
- `backend/scripts/*` remains excluded from host-side coverage because DB-touching branches require the Docker `postgres` service name. Production guards still have unit coverage.

Phase 1.5 baseline coverage included health endpoints, real dependency probes, request/correlation ID propagation, security headers, structured logging redaction, Prometheus metrics, OpenAPI/Swagger/ReDoc, CORS, safe error responses, production-secret validation, seed scripts, and audit events.

## Frontend

```bash
cd frontend && npm run test:coverage
```

The backend branch does not modify frontend code. Frontend validation remains the Phase 1.5 suite until Antigravity wires the React UI to real APIs.

## Phase 2 Backend: AI Assistant + Security Toolkit

```powershell
.\.venv\Scripts\python.exe -m pytest -q --cov=backend --cov-report=term-missing
```

Phase 2 backend tests cover:

- AI assistant chat, conversations, messages, provider success/timeout/unavailable/rate-limit behavior, missing provider configuration, local fallback honesty, redaction, and password-question routing.
- URL scanner validation, SSRF guard, redirect-to-private blocking, timeout, response-size limit, risk calculation, and scan-history recording.
- Password checker derived-only response, common/repeated/sequential password analysis, and privacy invariants: no echo, no scan-history row, no log/metric secret value.
- CVE lookup valid/invalid IDs, provider errors, not found, malformed upstream response, and cache miss/hit behavior.
- Scan history pagination, filters, detail retrieval, deletion, and 404 after delete.
- Request ID, correlation ID, CORS, OpenAPI, metrics, rate limiting, actor attribution, and safe error envelope.

No unit test should depend on live internet access. External HTTP should be stubbed or explicitly isolated to Docker/manual smoke evidence.

## Full Acceptance Gate

```powershell
scripts\Run-Acceptance-Tests.ps1
```

Phase 1.5 baseline: 37 gates covering repo/config validation, backend and frontend tests/coverage, security scanners, Docker build/health/persistence, seed idempotency, backup/restore, and k6 smoke. See `PHASE_1_5_REPORT.md`.

Phase 2 backend extensions cover migration `0003`, AI health honesty, assistant local answer, SSRF blocks on loopback/cloud metadata, completed URL scan, password privacy invariants, scan-history CRUD, CVE cache behavior where enabled, and OpenAPI path documentation. See `PHASE_2_BACKEND_REPORT.md`.

## Phase 2.5A: Supabase Database Foundation

New unit-tested modules (SQLite-backed, no live network - see `.coveragerc`
for why `backend/scripts/*` itself is exercised by dedicated tests but
excluded from the coverage percentage, same precedent as `seed_demo.py`):

- `backend/tests/test_supabase_settings.py` - `APP_ENV` validation,
  `DATABASE_URL`/`DATABASE_MIGRATION_URL` precedence and fallback,
  `DATABASE_SSL_MODE` injection, the staging/production explicit-URL guard.
- `backend/tests/test_dsn_redaction.py` - `redact_dsn()` never leaks
  credentials, preserves host/query.
- `backend/tests/test_db_retry.py` - transient-vs-non-transient
  classification, retry/backoff/give-up behavior.
- `backend/tests/test_db_preflight.py` - the preflight script never prints a
  credential, refuses to run against `is_production` without
  `--allow-production`.
- `backend/tests/test_migrate_to_supabase.py` - dry-run writes nothing,
  live run copies in FK-safe order, idempotent on re-run, never touches the
  source, never overwrites an existing target row.

### Database matrix

**A. Local Docker Postgres** - run for real in this phase, against a fresh
isolated stack (own Compose project, remapped host ports, never touching
another checkout's running containers):

- clean-database migration: `0001` → `0002` → `0003 (head)`
- existing-database migration: re-running `alembic upgrade head` is a no-op
- chatbot CRUD: create, chat (user+assistant messages persisted), list
  (paginated), detail, delete, 404-after-delete, survives a backend restart
- scan history CRUD: create (via a real URL scan), list, detail, delete,
  404-after-delete
- CVE Redis cache unaffected: miss then hit
- password never persisted, never logged

**B. Supabase staging** - `Supabase cloud validation: BLOCKED` in this
phase - no credentials were provided. The checklist to run once they are
available is `docs/CHATBOT_SUPABASE_VALIDATION.md`; the tooling
(`db_preflight.py`, `migrate_to_supabase.py`) and every doc it references
are complete and ready.

## What Is Not Fully Automated Yet

- Real Auth/RBAC is not proven complete in this branch until GAP-P1-004 is closed.
- Phase 3 IOC/Asset/Vulnerability/Patch backend APIs are not proven complete until GAP-P2-007 is closed.
- Browser E2E belongs to Antigravity after backend/UI integration.
- A live GitHub Actions run is still pending remote configuration.
