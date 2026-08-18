# Logging, Correlation, and Audit

## Structured JSON logging

Every log line (`backend/core/logging.py`, `JSONFormatter`) is one JSON
object:

```json
{
  "timestamp": "2026-07-29T12:00:00.123456+00:00",
  "level": "INFO",
  "logger": "backend.access",
  "service": "backend",
  "environment": "production",
  "message": "request_completed",
  "request_id": "a1b2c3d4-...",
  "correlation_id": "e5f6a7b8-...",
  "method": "GET",
  "path": "/api/system/health",
  "status_code": 200,
  "duration_ms": 12.4
}
```

`uvicorn.access` is silenced (`WARNING` level) — the app owns access
logging via `RequestContextMiddleware`, so every access log line is
structured JSON with `request_id`/`correlation_id`, not uvicorn's default
plaintext format.

## Request ID / Correlation ID

Handled by `RequestContextMiddleware` (`backend/middleware/request_context.py`):

- Accepts `X-Request-ID` / `X-Correlation-ID` from the client.
- Validated against `^[A-Za-z0-9_-]{1,128}$` — anything else (too long,
  containing CR/LF or other unsafe characters) is discarded and a fresh
  UUID generated instead. This blocks header/log injection via a crafted
  client-supplied ID.
- Both are echoed back in response headers and propagated through
  `contextvars` (`backend/core/context.py`, `backend/core/correlation.py`)
  so any log line emitted during that request — including from nested
  function calls — carries both IDs automatically, without threading them
  through every function signature.
- A request that raises an unhandled exception still gets a `request_id`
  in its error response (`test_errors.py`).

## Redaction

`REDACT_KEYS` in `backend/core/logging.py`:

```
authorization, password, jwt, jwt_secret, secret, secret_key,
client_secret, cookie, token, access_token, refresh_token, api_key,
connection_string, database_url, dsn
```

Any dict key matching one of these (case-insensitive) anywhere in a log
record's `extra={"fields": {...}}` payload is replaced with
`***redacted***` before serialization — recursively, including nested
dicts and lists. Verified by test: `test_logging_security.py::test_authorization_header_never_appears_in_logs`
sends a real `Authorization: Bearer ...` header and asserts the secret
value never appears in any captured log record.

**Convention, not just redaction**: dependency-probe code
(`backend/services/health.py`) logs `type(exc).__name__`, never `str(exc)`
— a driver exception's message can itself contain the connection string
(including the password), so redaction alone isn't relied on there.

## Audit events

`backend/core/audit.py`'s `log_audit_event()` — a minimal structured
audit-log abstraction (not a database table; Phase 1.5 scope is the
abstraction, not a full audit subsystem). Every call logs:

```json
{
  "audit": true,
  "event_type": "health_check",
  "action": "probe_dependencies",
  "resource": "system_health",
  "result": "success",
  "actor": null,
  "occurred_at": "2026-07-29T12:00:00+00:00",
  "metadata": {"status": "healthy"}
}
```

Currently wired into `GET /api/system/health` (one audit event per call,
`result` reflecting whether the aggregate status was healthy). Later
phases call the same function for real actions (login, config change,
etc.) instead of building a new mechanism.

## Tests proving this

- `test_request_id.py`, `test_correlation_id.py` — ID propagation,
  validation, injection resistance.
- `test_logging_security.py` — redaction, secret never logged.
- `test_audit.py` — audit events emit valid structured JSON, redaction
  applies to audit fields too.
- `test_errors.py` — error responses always carry `request_id`.
