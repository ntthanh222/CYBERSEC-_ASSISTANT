"""Minimal audit-event abstraction.

Phase 1.5 scope: a structured log-based audit trail only (no admin module,
no persistence store) — enough for later phases to build on. Every event
carries the current request_id automatically so audit lines can be
correlated with access logs.
"""
import logging
from datetime import datetime, timezone
from typing import Any, Literal, Optional

from backend.core.context import get_request_id

logger = logging.getLogger("backend.audit")

AuditResult = Literal["success", "failure"]


def log_audit_event(
    event_type: str,
    action: str,
    resource: str,
    result: AuditResult,
    actor: Optional[str] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> None:
    """Emit one structured audit log line.

    ``metadata`` must never contain secrets — it passes through the same
    redaction as every other structured log field, but callers should still
    avoid putting raw credentials or tokens in it.
    """
    logger.info(
        "audit_event",
        extra={
            "request_id": get_request_id(),
            "fields": {
                "audit": True,
                "event_type": event_type,
                "action": action,
                "resource": resource,
                "result": result,
                "actor": actor,
                "occurred_at": datetime.now(timezone.utc).isoformat(),
                "metadata": metadata or {},
            },
        },
    )
