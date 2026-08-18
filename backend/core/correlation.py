"""Request-scoped correlation ID, propagated alongside request_id.

request_id identifies one HTTP call; correlation_id identifies a logical
operation that may span multiple calls (e.g. a client-side retry chain).
Both are accepted from the client and echoed back, never trusted blindly.
"""
import contextvars
from typing import Optional

_correlation_id_ctx: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "correlation_id", default=None
)


def set_correlation_id(value: str) -> contextvars.Token:
    return _correlation_id_ctx.set(value)


def reset_correlation_id(token: contextvars.Token) -> None:
    _correlation_id_ctx.reset(token)


def get_correlation_id() -> Optional[str]:
    return _correlation_id_ctx.get()
