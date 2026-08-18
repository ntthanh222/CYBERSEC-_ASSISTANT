"""Structured JSON logging with redaction of sensitive fields.

Never pass raw exception text or connection strings into log fields: driver
exceptions can embed DSNs (including passwords). Callers must log
``type(exc).__name__`` rather than ``str(exc)`` for anything touching
credentials, and must never log Authorization/Cookie headers or bodies.
"""
import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

from backend.core.context import get_request_id
from backend.core.correlation import get_correlation_id

REDACT_KEYS = {
    "authorization",
    "password",
    "jwt",
    "jwt_secret",
    "secret",
    "secret_key",
    "client_secret",
    "cookie",
    "token",
    "access_token",
    "refresh_token",
    "api_key",
    "connection_string",
    "database_url",
    "database_migration_url",
    "dsn",
    "supabase_secret_key",
    "supabase_service_role_key",
}

REDACTED_VALUE = "***redacted***"


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: (REDACTED_VALUE if key.lower() in REDACT_KEYS else _redact(val))
            for key, val in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_redact(item) for item in value]
    return value


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        # Local import: avoids a config->logging->config import cycle at
        # module load time, and settings are read fresh (cheap, lru_cache'd).
        from backend.config.settings import get_settings

        settings = get_settings()
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "service": "backend",
            "environment": settings.environment,
            "message": record.getMessage(),
        }

        request_id = getattr(record, "request_id", None) or get_request_id()
        if request_id:
            payload["request_id"] = request_id

        correlation_id = getattr(record, "correlation_id", None) or get_correlation_id()
        if correlation_id:
            payload["correlation_id"] = correlation_id

        fields = getattr(record, "fields", None)
        if fields:
            payload.update(_redact(fields))

        if record.exc_info and record.exc_info[0] is not None:
            payload["exception_type"] = record.exc_info[0].__name__

        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: int = logging.INFO) -> None:
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    root.addHandler(handler)

    # Quiet noisy third-party loggers; access/audit logging is owned by our
    # own request-context middleware, not uvicorn's default access log.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
