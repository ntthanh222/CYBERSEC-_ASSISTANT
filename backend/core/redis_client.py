"""Shared Redis client.

Phase 1.5 opened a throwaway connection inside the health probe. Phase 2 adds
two more consumers (the CVE cache and the rate limiter), so the client is
created once and reused.

The client is created lazily and never at import time: an unreachable Redis
must degrade the features that use it, not prevent the process from starting.
"""
from functools import lru_cache
from typing import Optional

import redis.asyncio as aioredis

from backend.config.settings import get_settings

CONNECT_TIMEOUT_SECONDS = 2.0
OPERATION_TIMEOUT_SECONDS = 2.0


@lru_cache
def get_redis() -> Optional[aioredis.Redis]:
    """Return the shared Redis client, or ``None`` when no URL is configured."""
    settings = get_settings()
    if not settings.redis_url:
        return None
    return aioredis.from_url(
        settings.redis_url,
        socket_connect_timeout=CONNECT_TIMEOUT_SECONDS,
        socket_timeout=OPERATION_TIMEOUT_SECONDS,
        decode_responses=True,
    )


async def close_redis() -> None:
    """Close the shared client, if one was ever created (used on shutdown)."""
    client = get_redis()
    if client is not None:
        await client.aclose()
    get_redis.cache_clear()
