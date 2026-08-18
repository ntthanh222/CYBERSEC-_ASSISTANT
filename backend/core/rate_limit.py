"""Redis-backed fixed-window rate limiting.

Applied to the three endpoints that either cost money upstream or perform
outbound network requests: assistant chat, URL scan and CVE lookup.

Design notes
------------
* **Bucket, not path, is the metrics label.** Buckets are a small fixed set of
  strings; actors and IP addresses are never used as label values because
  their cardinality is unbounded.
* **Fail open.** If Redis is unreachable the request is allowed and a warning
  is logged. A cache outage degrading into a full API outage would be a worse
  failure than briefly unmetered traffic, and Phase 1.5 already treats Redis as
  a non-fatal dependency.
* The window counter is created with ``INCR`` and given a TTL on first use, so
  keys expire on their own and no cleanup job is needed.
"""
import logging
import time
from typing import Awaitable, Callable

from fastapi import Depends, Request

from backend.core.actor import get_current_actor
from backend.core.exceptions import RateLimitedError
from backend.core.metrics import observe_rate_limit
from backend.core.redis_client import get_redis

logger = logging.getLogger("backend.rate_limit")


class RateLimiter:
    """Dependency factory enforcing ``limit`` requests per ``window_seconds``."""

    def __init__(self, bucket: str, limit: int, window_seconds: int) -> None:
        self.bucket = bucket
        self.limit = limit
        self.window_seconds = window_seconds

    async def __call__(
        self,
        request: Request,
        actor: str = Depends(get_current_actor),
    ) -> None:
        client = get_redis()
        if client is None:
            return

        window_start = int(time.time()) // self.window_seconds
        key = f"ratelimit:{self.bucket}:{actor}:{window_start}"

        try:
            count = await client.incr(key)
            if count == 1:
                await client.expire(key, self.window_seconds)
        except Exception as exc:  # noqa: BLE001 - availability over enforcement
            logger.warning(
                "rate_limit_backend_unavailable",
                extra={"fields": {"bucket": self.bucket, "exception_type": type(exc).__name__}},
            )
            return

        if count > self.limit:
            observe_rate_limit(self.bucket)
            raise RateLimitedError(
                f"Rate limit exceeded: at most {self.limit} requests per "
                f"{self.window_seconds} seconds for this operation."
            )


def rate_limit(bucket: str, limit: int, window_seconds: int) -> Callable[..., Awaitable[None]]:
    """Convenience wrapper so routes read ``Depends(rate_limit(...))``."""
    return RateLimiter(bucket=bucket, limit=limit, window_seconds=window_seconds)
