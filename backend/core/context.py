"""Request-scoped context propagated through async tasks."""
import contextvars
from typing import Optional

_request_id_ctx: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "request_id", default=None
)


def set_request_id(value: str) -> contextvars.Token:
    return _request_id_ctx.set(value)


def reset_request_id(token: contextvars.Token) -> None:
    _request_id_ctx.reset(token)


def get_request_id() -> Optional[str]:
    return _request_id_ctx.get()
