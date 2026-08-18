# Architecture (current — Phase 1 / 1.5)

This describes what is actually built today. For the full target product
architecture, see `docs/02_TARGET_ARCHITECTURE.md`.

## Services (docker-compose.yml — exactly 4)

```
┌──────────┐      ┌─────────┐      ┌──────────┐
│ frontend │ ───▶ │ backend │ ───▶ │ postgres │
│  nginx   │ /api │ FastAPI │      │          │
└──────────┘      └─────────┘      └──────────┘
    :3000            :8000              │
     host          (host+internal)   internal only
                        │
                        ▼
                    ┌───────┐
                    │ redis │
                    └───────┘
                    internal only
```

- **frontend**: static HTML/CSS/vanilla JS, served by
  `nginxinc/nginx-unprivileged:1.27-alpine` (non-root, uid 101, port 8080
  internally, `3000:8080` on the host). Proxies `/api/` to the backend so
  it never hardcodes an environment-specific backend URL.
- **backend**: FastAPI (`python:3.12-alpine`, multi-stage build, non-root
  uid 10001), `8000:8000` on the host (needed directly for Swagger/ReDoc/
  metrics access during development; a later phase may put this behind
  the frontend proxy too).
- **postgres** / **redis**: internal-only (no host port mapping) —
  reachable only from `backend` on the `cybersec-network` bridge.

All 4 have real Docker healthchecks (not just "container running") and
`restart: unless-stopped`.

## Backend module layout

```
backend/
  main.py                 FastAPI app wiring: middleware order, exception handlers
  api/                     health.py, system.py, metrics.py — route handlers only
  schemas/                 Pydantic response models (OpenAPI docs)
  core/
    context.py             request_id contextvar
    correlation.py         correlation_id contextvar
    logging.py             JSON formatter + redaction
    metrics.py             Prometheus registry
    audit.py                structured audit-event helper
  middleware/
    request_context.py     assigns/validates IDs, records metrics, emits access log
    security_headers.py    CSP/X-Frame-Options/etc.
  services/
    health.py               real DB/Redis probes
  database/
    session.py               lazy async SQLAlchemy engine
    migrations/               Alembic (versions/0001_baseline, 0002_demo_seed_marker)
  scripts/
    seed_demo.py, reset_demo.py   idempotent seed framework
  config/
    settings.py              pydantic-settings, production-secret validation
```

## Middleware order (`main.py`)

```
CORSMiddleware → SecurityHeadersMiddleware → RequestContextMiddleware → routes
                                                       │
                                          (also: metrics recording,
                                           structured access log,
                                           request_id/correlation_id
                                           contextvar propagation)
```

Exception handlers (`StarletteHTTPException`, `RequestValidationError`,
generic `Exception`) all return the same `{error, message, request_id}`
shape and record an `http_errors_total` metric — no stack traces or
internal details ever reach the client.

## Data flow: a request to `/api/system/health`

1. `RequestContextMiddleware` resolves/validates request ID + correlation
   ID, starts a timer.
2. Handler probes PostgreSQL (`SELECT 1`, 2s timeout) and Redis (`PING`,
   2s timeout) — each catches its own exceptions and returns a status
   string, never crashes the request.
3. `aggregate_status()` combines database+redis status (backend's own
   trivial self-check is excluded from the aggregate — see
   `.ai/DECISIONS.md`).
4. Response always HTTP 200; real status is in the JSON body.
5. Middleware records `dependency_probe_status`/`_latency_ms` metrics,
   logs one structured `request_completed` line, logs one audit event.

## Why these specific technology choices

See `.ai/DECISIONS.md` for the full decision log (psycopg3 over asyncpg,
HTTP-200-always for system health, backend excluded from the health
aggregate, Alpine over Debian-slim for the backend image, etc.) — each
entry states context, alternatives considered, and evidence.
