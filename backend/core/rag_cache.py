"""Redis caching for RAG retrieval: cache-aside, version-invalidated.

Cache-aside pattern (mirrors ``backend/services/cve.py``): check Redis, on
miss compute and populate, on any Redis error skip the cache entirely - a
cache outage must degrade performance, not correctness.

Invalidation is a version counter, not a TTL guess: every knowledge-base
mutation (ingest, delete, reprocess) bumps ``knowledge_version:{scope}`` in
Redis (see :func:`bump_knowledge_version`), and every cache key embeds the
current version for the scopes the query can see (the caller's own
documents, plus the shared global-document scope). A stale cache entry is
never served after a document changes - the version bump changes the key
itself, so the old entry is simply never looked up again (and expires on
its own TTL, needing no explicit delete).
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from typing import Any, Final, Optional

from backend.config.settings import get_settings
from backend.core.redis_client import get_redis

logger = logging.getLogger("backend.core.rag_cache")

_GLOBAL_VERSION_KEY: Final = "kb:version:global"
_USER_VERSION_KEY_PREFIX: Final = "kb:version:user:"
_RETRIEVAL_CACHE_PREFIX: Final = "rag:retrieval:v1:"
_ANSWER_CACHE_PREFIX: Final = "rag:answer:v1:"
_COOLDOWN_CACHE_PREFIX: Final = "rag:cooldown:"
_EMBEDDING_CACHE_PREFIX: Final = "rag:embedding:v1:"


async def bump_knowledge_version(*, user_id: Optional[uuid.UUID]) -> None:
    """Called on document ingest/delete/reprocess. ``user_id=None`` bumps the
    global (system-document) scope - every cached retrieval becomes
    unreachable for the next lookup regardless of TTL. Best-effort: a Redis
    outage here must not block the mutation that triggered it."""
    client = get_redis()
    if client is None:
        return
    key = _USER_VERSION_KEY_PREFIX + str(user_id) if user_id else _GLOBAL_VERSION_KEY
    try:
        await client.incr(key)
    except Exception as exc:  # noqa: BLE001 - cache is best-effort
        logger.warning(
            "rag_cache_version_bump_failed",
            extra={"fields": {"exception_type": type(exc).__name__}},
        )


async def _current_versions(user_id: uuid.UUID) -> tuple[str, str]:
    client = get_redis()
    if client is None:
        return "0", "0"
    try:
        user_version = await client.get(_USER_VERSION_KEY_PREFIX + str(user_id))
        global_version = await client.get(_GLOBAL_VERSION_KEY)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "rag_cache_version_read_failed",
            extra={"fields": {"exception_type": type(exc).__name__}},
        )
        return "0", "0"
    return (user_version or "0", global_version or "0")


def _cache_key(*, user_id: uuid.UUID, user_version: str, global_version: str, query: str) -> str:
    normalized = " ".join(query.strip().lower().split())
    digest = hashlib.sha256(normalized.encode()).hexdigest()[:32]
    return f"{_RETRIEVAL_CACHE_PREFIX}{user_id}:{user_version}:{global_version}:{digest}"


def _answer_cache_key(
    *, user_id: uuid.UUID, user_version: str, global_version: str, query: str, mode: str
) -> str:
    normalized = " ".join(query.strip().lower().split())
    digest = hashlib.sha256(f"{mode}:{normalized}".encode()).hexdigest()[:32]
    return f"{_ANSWER_CACHE_PREFIX}{user_id}:{user_version}:{global_version}:{digest}"


async def get_cached_retrieval(*, user_id: uuid.UUID, query: str) -> Optional[list[dict[str, Any]]]:
    client = get_redis()
    if client is None:
        return None
    user_version, global_version = await _current_versions(user_id)
    key = _cache_key(
        user_id=user_id, user_version=user_version, global_version=global_version, query=query
    )
    try:
        raw = await client.get(key)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "rag_cache_read_failed", extra={"fields": {"exception_type": type(exc).__name__}}
        )
        return None
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return None


async def set_cached_retrieval(
    *, user_id: uuid.UUID, query: str, results: list[dict[str, Any]]
) -> None:
    client = get_redis()
    if client is None:
        return
    settings = get_settings()
    user_version, global_version = await _current_versions(user_id)
    key = _cache_key(
        user_id=user_id, user_version=user_version, global_version=global_version, query=query
    )
    try:
        await client.set(
            key,
            json.dumps(results),
            ex=settings.rag_retrieval_cache_ttl_seconds,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "rag_cache_write_failed", extra={"fields": {"exception_type": type(exc).__name__}}
        )


async def get_cached_answer(
    *, user_id: uuid.UUID, query: str, mode: str
) -> Optional[dict[str, Any]]:
    """Retrieve full cached answer response if available."""
    client = get_redis()
    if client is None:
        return None
    user_version, global_version = await _current_versions(user_id)
    key = _answer_cache_key(
        user_id=user_id,
        user_version=user_version,
        global_version=global_version,
        query=query,
        mode=mode,
    )
    try:
        raw = await client.get(key)
        if raw is not None:
            data = json.loads(raw)
            data["cache_hit"] = True
            return data
    except Exception as exc:  # noqa: BLE001
        logger.warning("rag_answer_cache_read_failed", extra={"fields": {"exception": str(exc)}})
    return None


async def set_cached_answer(
    *, user_id: uuid.UUID, query: str, mode: str, answer_data: dict[str, Any], ttl: int = 3600
) -> None:
    """Cache full answer response."""
    client = get_redis()
    if client is None:
        return
    user_version, global_version = await _current_versions(user_id)
    key = _answer_cache_key(
        user_id=user_id,
        user_version=user_version,
        global_version=global_version,
        query=query,
        mode=mode,
    )
    try:
        await client.set(key, json.dumps(answer_data), ex=ttl)
    except Exception as exc:  # noqa: BLE001
        logger.warning("rag_answer_cache_write_failed", extra={"fields": {"exception": str(exc)}})


async def set_provider_cooldown(provider_name: str, duration_seconds: int = 60) -> None:
    """Set provider cooldown (e.g. on 429 rate limit)."""
    client = get_redis()
    if client is None:
        return
    key = f"{_COOLDOWN_CACHE_PREFIX}{provider_name}"
    try:
        await client.set(key, "1", ex=duration_seconds)
    except Exception:  # nosec B110
        pass


async def is_provider_in_cooldown(provider_name: str) -> bool:
    """Check if provider is in active cooldown."""
    client = get_redis()
    if client is None:
        return False
    key = f"{_COOLDOWN_CACHE_PREFIX}{provider_name}"
    try:
        return bool(await client.exists(key))
    except Exception:  # noqa: BLE001
        return False
