"""Bounded retry for *connection establishment* only.

Scope is deliberately narrow: this wraps "can we open a connection and run
SELECT 1" for tooling that talks to a possibly-cold or network-flaky target
(Supabase over the internet, vs. Docker's same-host Postgres). It must never
wrap an actual migration run or a query with side effects - a retried
`alembic upgrade head` on a partially-applied migration is exactly the kind
of silent-corruption bug this module exists to avoid, not cause.

Classification never logs the exception text (it may embed a DSN, including
a password) - only `type(exc).__name__` is safe to log, per the same rule
documented in core.logging.
"""
import time
from typing import Callable, TypeVar

T = TypeVar("T")

# Substrings that mean "the server answered and said no" - retrying would
# just fail the same way N more times, slower. Matched case-insensitively
# against the exception text in-memory only; never logged as-is.
_NON_RETRYABLE_MARKERS = (
    "password authentication failed",
    "no pg_hba.conf entry",
    "role ",  # e.g. role "x" does not exist
    "database ",  # e.g. database "x" does not exist
    "invalid_password",
    "invalid_authorization_specification",
    "permission denied",
)


def pg_connect_args(url: str, timeout_seconds: int = 10) -> dict:
    """`connect_timeout` only makes sense for a real Postgres driver.

    SQLite (used in tests as a Postgres stand-in for schema/logic checks -
    see conftest.py) does not accept it, so scripts that want to run
    unmodified against either target need this rather than a bare literal.
    """
    if url.startswith("postgresql"):
        return {"connect_timeout": timeout_seconds}
    return {}


def is_transient_db_error(exc: BaseException) -> bool:
    """True for network/availability failures worth retrying.

    False for anything that looks like a credential, permission, or
    not-found problem - those will not resolve themselves on a retry.
    """
    text = str(exc).lower()
    if any(marker in text for marker in _NON_RETRYABLE_MARKERS):
        return False
    return True


def retry_transient(
    fn: Callable[[], T],
    *,
    attempts: int = 3,
    base_delay_seconds: float = 1.0,
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """Call `fn()`, retrying only on transient connection errors.

    Backs off linearly (base_delay * attempt number). Re-raises immediately
    - no retry - on the first non-transient error, and re-raises the last
    error if every attempt was transient and still failed.
    """
    if attempts < 1:
        raise ValueError("attempts must be >= 1")
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 - reclassified below, not swallowed
            if not is_transient_db_error(exc) or attempt == attempts:
                raise
            sleep(base_delay_seconds * attempt)
