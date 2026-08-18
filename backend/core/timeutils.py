"""Timezone helpers.

Every timestamp the API stores or emits is UTC. PostgreSQL round-trips
``TIMESTAMPTZ`` as an aware datetime, but SQLite (used by the test suite)
returns naive values for the same column, so anything read back from the
database goes through :func:`ensure_utc` before it is serialized.
"""
from datetime import datetime, timezone


def utcnow() -> datetime:
    """Current time as a timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


def ensure_utc(value: datetime) -> datetime:
    """Return ``value`` as an aware UTC datetime.

    A naive datetime is assumed to already be UTC (that is the only thing this
    application ever writes) rather than silently reinterpreted as local time.
    """
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def to_iso_utc(value: datetime) -> str:
    """Serialize to ISO-8601 UTC, e.g. ``2026-07-29T02:15:00+00:00``."""
    return ensure_utc(value).isoformat()
