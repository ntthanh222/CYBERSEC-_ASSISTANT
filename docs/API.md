# API

Scope: Phase 1/1.5 (this document) covers platform health and
observability. **Phase 2** adds the first business endpoints — AI Security
Assistant + Security Toolkit (URL Scanner, Password Checker, CVE Lookup,
Scan History) — documented separately and in full in
[`PHASE_2_API_CONTRACT.md`](PHASE_2_API_CONTRACT.md); see also
[`PHASE_2_FRONTEND_INTEGRATION.md`](PHASE_2_FRONTEND_INTEGRATION.md) for
the fixture-to-endpoint field mapping. Auth/RBAC and the remaining SOC
features are still out of scope.

Interactive docs (live, generated from the code, not hand-maintained):

- Swagger UI: `GET /docs`
- ReDoc: `GET /redoc`
- Raw OpenAPI JSON: `GET /openapi.json`

## Endpoints

### `GET /health` — Liveness

Dependency-free. Never touches PostgreSQL/Redis — used by the Docker
healthcheck and orchestrators, so a dependency outage never restarts an
otherwise-healthy backend.

```json
{"status": "healthy", "service": "backend"}
```

### `GET /api/system/health` — Aggregated system health

Probes PostgreSQL and Redis in real time. **Always returns HTTP 200** — the
real status is in the JSON body (`healthy` / `degraded` / `unavailable`),
so a dependency outage is never confused with a network failure at the
HTTP layer.

```json
{
  "status": "healthy",
  "timestamp": "2026-07-29T12:00:00+00:00",
  "request_id": "a1b2c3d4-...",
  "checks": {
    "backend": {"status": "healthy", "latency_ms": 0.0},
    "database": {"status": "healthy", "latency_ms": 2.76},
    "redis": {"status": "healthy", "latency_ms": 1.87}
  }
}
```

### `GET /metrics` — Prometheus scrape endpoint

Plaintext Prometheus exposition format. Not in the OpenAPI schema
(`include_in_schema=False`) since it's an infra endpoint, not part of the
public API surface. See [`docs/MONITORING.md`](MONITORING.md).

## Cross-cutting behavior (every endpoint)

- **Request ID**: accepts `X-Request-ID` from the client (validated against
  `^[A-Za-z0-9_-]{1,128}$`; regenerated as a UUID if missing/invalid),
  always echoed back in the response header.
- **Correlation ID**: same rule, header `X-Correlation-ID` — identifies a
  logical operation across multiple requests, independent of request ID.
- **Security headers**: `X-Content-Type-Options`, `Referrer-Policy`,
  `X-Frame-Options`, `Permissions-Policy`, `Content-Security-Policy` on
  every response.
- **CORS**: explicit origin allowlist (`CORS_ORIGINS` env var), never `*`
  with credentials.
- **Error responses**: every error (validation, HTTP error, unhandled
  exception) returns `{"error": ..., "message": ..., "request_id": ...}`,
  never a stack trace or internal detail. Example 500 body:

```json
{
  "error": "internal_server_error",
  "message": "An unexpected error occurred. Please try again later.",
  "request_id": "a1b2c3d4-..."
}
```

## Phase 2 endpoints (summary — full contract in PHASE_2_API_CONTRACT.md)

```
POST   /api/chatbot/chat
GET    /api/chatbot/conversations
POST   /api/chatbot/conversations
GET    /api/chatbot/conversations/{conversation_id}
DELETE /api/chatbot/conversations/{conversation_id}
GET    /api/chatbot/conversations/{conversation_id}/messages
GET    /api/system/ai-health

POST   /api/tools/url-scan
POST   /api/tools/password-check
GET    /api/tools/password-guidance
GET    /api/tools/scan-history
GET    /api/tools/scan-history/{record_id}
DELETE /api/tools/scan-history/{record_id}

GET    /api/cves/{cve_id}
GET    /api/cves/search
```

None of these require authentication yet (see `docs/SECURITY.md`). All of
them follow the same error envelope and `X-Request-ID`/`X-Correlation-ID`
conventions documented above.

## Adding an endpoint in a later phase

Every route must set `summary`, `description`, `response_model`, and a
`responses` entry for its realistic error cases — see `backend/api/health.py`
and `backend/api/system.py` for the pattern. `backend/schemas/health.py`
shows the response-model convention (Pydantic models with `examples=`).
