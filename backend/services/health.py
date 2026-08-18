"""Real dependency probes for the system health endpoint.

Every probe swallows its own exceptions and returns a structured status
instead of raising, so that a database or Redis outage degrades the health
report rather than crashing the backend. Only the exception *type* is
logged, never ``str(exc)``: driver errors can embed the connection string
(including the password) in their message text.
"""
import asyncio
import functools
import logging
import time
from pathlib import Path
from typing import Literal, Optional, TypedDict

from alembic.config import Config as AlembicConfig
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine
import redis.asyncio as aioredis

logger = logging.getLogger("backend.health")

Status = Literal["healthy", "degraded", "unavailable", "unknown"]

DB_TIMEOUT_SECONDS = 2.0
REDIS_TIMEOUT_SECONDS = 2.0

_ALEMBIC_INI_PATH = Path(__file__).resolve().parent.parent / "alembic.ini"


@functools.lru_cache(maxsize=1)
def _expected_migration_revision() -> Optional[str]:
    """The Alembic head revision this backend expects the database to be at.

    Read from the migration scripts themselves (via Alembic's own
    ``ScriptDirectory``) instead of a hand-maintained constant, so this can
    never silently drift behind the real head the way a copy-pasted string
    would every time a new migration is added.
    """
    try:
        config = AlembicConfig(str(_ALEMBIC_INI_PATH))
        migrations_dir = _ALEMBIC_INI_PATH.parent / "database" / "migrations"
        config.set_main_option("script_location", str(migrations_dir))
        return ScriptDirectory.from_config(config).get_current_head()
    except Exception:  # noqa: BLE001 - never let a misread scripts dir crash health checks
        logger.warning("expected_migration_revision_lookup_failed")
        return None


class CheckResult(TypedDict):
    status: Status
    latency_ms: Optional[float]


def _elapsed_ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 2)


async def check_database(engine: Optional[AsyncEngine]) -> CheckResult:
    if engine is None:
        return {"status": "unknown", "latency_ms": None}

    start = time.perf_counter()
    try:
        async with asyncio.timeout(DB_TIMEOUT_SECONDS):
            async with engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
        return {"status": "healthy", "latency_ms": _elapsed_ms(start)}
    except Exception as exc:  # noqa: BLE001 - defense in depth, never crash the caller
        logger.warning(
            "database_probe_failed",
            extra={"fields": {"exception_type": type(exc).__name__}},
        )
        return {"status": "unavailable", "latency_ms": _elapsed_ms(start)}


async def check_redis(redis_url: Optional[str]) -> CheckResult:
    if not redis_url:
        return {"status": "unknown", "latency_ms": None}

    start = time.perf_counter()
    client = aioredis.from_url(
        redis_url,
        socket_connect_timeout=REDIS_TIMEOUT_SECONDS,
        socket_timeout=REDIS_TIMEOUT_SECONDS,
    )
    try:
        pong = await client.ping()
        status: Status = "healthy" if pong else "unavailable"
        return {"status": status, "latency_ms": _elapsed_ms(start)}
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "redis_probe_failed",
            extra={"fields": {"exception_type": type(exc).__name__}},
        )
        return {"status": "unavailable", "latency_ms": _elapsed_ms(start)}
    finally:
        await client.aclose()


async def check_migration(engine: Optional[AsyncEngine]) -> CheckResult:
    """Never report healthy if the schema isn't actually at the expected head.

    A backend that answers requests against a stale or half-applied schema
    is worse than one that is honestly unavailable - it silently corrupts or
    rejects data instead of failing loudly.
    """
    if engine is None:
        return {"status": "unknown", "latency_ms": None}

    start = time.perf_counter()
    try:
        async with asyncio.timeout(DB_TIMEOUT_SECONDS):
            async with engine.connect() as connection:
                result = await connection.execute(text("SELECT version_num FROM alembic_version"))
                row = result.first()
        current = row[0] if row else None
        expected = _expected_migration_revision()
        is_healthy = expected is not None and current == expected
        status: Status = "healthy" if is_healthy else "unavailable"
        return {"status": status, "latency_ms": _elapsed_ms(start)}
    except Exception as exc:  # noqa: BLE001 - defense in depth, never crash the caller
        logger.warning(
            "migration_probe_failed",
            extra={"fields": {"exception_type": type(exc).__name__}},
        )
        return {"status": "unavailable", "latency_ms": _elapsed_ms(start)}


async def check_pgvector(engine: Optional[AsyncEngine]) -> CheckResult:
    if engine is None:
        return {"status": "unknown", "latency_ms": None}

    start = time.perf_counter()
    try:
        async with asyncio.timeout(DB_TIMEOUT_SECONDS):
            async with engine.connect() as connection:
                result = await connection.execute(
                    text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
                )
                row = result.first()
        status: Status = "healthy" if row is not None else "unavailable"
        return {"status": status, "latency_ms": _elapsed_ms(start)}
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "pgvector_probe_failed",
            extra={"fields": {"exception_type": type(exc).__name__}},
        )
        return {"status": "unavailable", "latency_ms": _elapsed_ms(start)}


def check_local_auth_secret(
    app_env: str,
    secret_path: str,
    *,
    externally_supplied: bool,
) -> CheckResult:
    """Confirms Local Mode actually has a durable JWT-signing secret.

    Only meaningful in `local`/`test` - in staging/production Local Mode is
    hard-disabled regardless of this check (see backend/api/local_auth.py),
    so the check is a no-op there rather than a false negative.

    Two genuinely different valid states, both `healthy`:
    - `externally_supplied=True`: a real `SUPABASE_JWT_SECRET` was
      configured, so the generated-secret file is deliberately never
      written (see backend/config/settings.py) - the file's absence here
      is correct, not a problem, and checking for it would be a false
      negative (this was a real bug, caught in Codex review round 1).
    - `externally_supplied=False` AND the secret file exists on disk right
      now: the runtime-generated secret genuinely persisted.

    The one case that must NOT report `healthy`: `externally_supplied=False`
    and the file does not exist. `backend/core/local_auth_secret.py` always
    returns *some* usable secret even when persistence to disk failed (an
    in-memory-only fallback, so the process can still start and serve
    requests) - checking only "is there a secret in memory" would silently
    mask that failure (a real bug, caught in Codex review round 2, since
    that in-memory fallback means every Local Mode session minted before
    the next restart stops validating - existing users get logged out
    with no warning). Reported `degraded`, not `unavailable`: Local Mode
    is actually working right now, it just won't survive a restart.
    """
    if app_env.lower() not in {"local", "test"}:
        return {"status": "unknown", "latency_ms": None}

    start = time.perf_counter()
    if externally_supplied:
        status: Status = "healthy"
    else:
        status = "healthy" if Path(secret_path).is_file() else "degraded"
    return {"status": status, "latency_ms": _elapsed_ms(start)}


def aggregate_status(checks: dict) -> Status:
    statuses = {check["status"] for check in checks.values()}
    if statuses == {"healthy"}:
        return "healthy"
    if "healthy" not in statuses and statuses <= {"unavailable", "unknown"}:
        return "unavailable"
    return "degraded"
