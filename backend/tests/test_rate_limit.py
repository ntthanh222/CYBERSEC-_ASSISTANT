"""Rate limiter: enforcement, fail-open behaviour, and per-actor isolation."""
import pytest

from backend.core.exceptions import RateLimitedError
from backend.core.rate_limit import RateLimiter


class FakeRedis:
    def __init__(self, *, fail: bool = False) -> None:
        self._counts: dict[str, int] = {}
        self._fail = fail

    async def incr(self, key: str) -> int:
        if self._fail:
            raise ConnectionError("redis unreachable")
        self._counts[key] = self._counts.get(key, 0) + 1
        return self._counts[key]

    async def expire(self, key: str, seconds: int) -> None:
        if self._fail:
            raise ConnectionError("redis unreachable")


class DummyRequest:
    headers: dict[str, str] = {}


async def test_rate_limiter_allows_requests_under_the_limit(monkeypatch):
    redis = FakeRedis()
    monkeypatch.setattr("backend.core.rate_limit.get_redis", lambda: redis)
    limiter = RateLimiter(bucket="test", limit=3, window_seconds=60)

    for _ in range(3):
        await limiter(DummyRequest(), actor="tester")


async def test_rate_limiter_rejects_once_the_limit_is_exceeded(monkeypatch):
    redis = FakeRedis()
    monkeypatch.setattr("backend.core.rate_limit.get_redis", lambda: redis)
    limiter = RateLimiter(bucket="test", limit=2, window_seconds=60)

    await limiter(DummyRequest(), actor="tester")
    await limiter(DummyRequest(), actor="tester")
    with pytest.raises(RateLimitedError):
        await limiter(DummyRequest(), actor="tester")


async def test_rate_limiter_tracks_actors_independently(monkeypatch):
    redis = FakeRedis()
    monkeypatch.setattr("backend.core.rate_limit.get_redis", lambda: redis)
    limiter = RateLimiter(bucket="test", limit=1, window_seconds=60)

    await limiter(DummyRequest(), actor="alice")
    await limiter(DummyRequest(), actor="bob")  # different actor, own bucket
    with pytest.raises(RateLimitedError):
        await limiter(DummyRequest(), actor="alice")


async def test_rate_limiter_fails_open_when_redis_is_unreachable(monkeypatch):
    redis = FakeRedis(fail=True)
    monkeypatch.setattr("backend.core.rate_limit.get_redis", lambda: redis)
    limiter = RateLimiter(bucket="test", limit=1, window_seconds=60)

    # Would be rejected on a healthy backend after the first call; with Redis
    # down, availability wins and every call is allowed.
    await limiter(DummyRequest(), actor="tester")
    await limiter(DummyRequest(), actor="tester")


async def test_rate_limiter_is_a_no_op_when_no_redis_is_configured(monkeypatch):
    monkeypatch.setattr("backend.core.rate_limit.get_redis", lambda: None)
    limiter = RateLimiter(bucket="test", limit=1, window_seconds=60)
    await limiter(DummyRequest(), actor="tester")
    await limiter(DummyRequest(), actor="tester")
