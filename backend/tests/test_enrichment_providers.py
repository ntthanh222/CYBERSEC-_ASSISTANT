"""EPSS/KEV enrichment provider tests (Task 6). Network is always mocked via
httpx.MockTransport (mirroring backend/tests/test_cve_api.py's NVD provider
tests) or a fake Redis client (mirroring backend/tests/test_cve_lookup.py) -
no real network calls."""
import httpx
import pytest

from backend.providers.enrichment.epss import EpssProvider
from backend.providers.enrichment.fixture import FixtureEpssProvider, FixtureKevProvider
from backend.providers.enrichment.kev import KevProvider


class FakeRedis:
    """Minimal in-memory stand-in for the subset of redis.asyncio used here."""

    def __init__(self, *, fail: bool = False) -> None:
        self._store: dict[str, str] = {}
        self._fail = fail
        self.set_calls = 0
        self.get_calls = 0

    async def get(self, key: str):
        self.get_calls += 1
        if self._fail:
            raise ConnectionError("redis unreachable")
        return self._store.get(key)

    async def set(self, key: str, value: str, ex: int | None = None):
        self.set_calls += 1
        if self._fail:
            raise ConnectionError("redis unreachable")
        self._store[key] = value


def _transport(handler) -> httpx.MockTransport:
    return httpx.MockTransport(handler)


# ─── Fixture providers (used by API-level tests elsewhere) ─────────────────


async def test_fixture_epss_provider_returns_known_score():
    provider = FixtureEpssProvider()
    result = await provider.get("CVE-2021-44228")
    assert result is not None
    assert result.score == pytest.approx(0.94427)
    assert result.percentile == pytest.approx(0.99930)


async def test_fixture_epss_provider_returns_none_for_unknown_cve():
    provider = FixtureEpssProvider()
    result = await provider.get("CVE-2099-99999")
    assert result is None


async def test_fixture_kev_provider_membership():
    provider = FixtureKevProvider()
    assert await provider.is_kev("CVE-2021-44228") is True
    assert await provider.is_kev("CVE-2099-99999") is False
    assert await provider.get("CVE-2021-44228") is True


# ─── EpssProvider: real-shaped response parsing ─────────────────────────────


_SAMPLE_EPSS_RESPONSE = {
    "status": "OK",
    "data": [
        {"cve": "CVE-2021-44228", "epss": "0.94427", "percentile": "0.99930", "date": "2024-01-01"}
    ],
}


async def test_epss_provider_parses_a_real_shaped_response(monkeypatch):
    monkeypatch.setattr("backend.providers.enrichment.epss.get_redis", lambda: None)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["cve"] == "CVE-2021-44228"
        return httpx.Response(200, json=_SAMPLE_EPSS_RESPONSE)

    provider = EpssProvider(transport=_transport(handler))
    result = await provider.get("CVE-2021-44228")
    assert result is not None
    assert result.score == pytest.approx(0.94427)
    assert result.percentile == pytest.approx(0.99930)
    assert result.cve_id == "CVE-2021-44228"


async def test_epss_provider_returns_none_for_a_cve_not_in_the_dataset(monkeypatch):
    monkeypatch.setattr("backend.providers.enrichment.epss.get_redis", lambda: None)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "OK", "data": []})

    provider = EpssProvider(transport=_transport(handler))
    result = await provider.get("CVE-2099-99999")
    assert result is None


async def test_epss_provider_fails_open_on_network_error(monkeypatch):
    monkeypatch.setattr("backend.providers.enrichment.epss.get_redis", lambda: None)

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    provider = EpssProvider(transport=_transport(handler))
    result = await provider.get("CVE-2021-44228")
    assert result is None


async def test_epss_provider_fails_open_on_timeout(monkeypatch):
    monkeypatch.setattr("backend.providers.enrichment.epss.get_redis", lambda: None)

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timed out", request=request)

    provider = EpssProvider(transport=_transport(handler))
    result = await provider.get("CVE-2021-44228")
    assert result is None


async def test_epss_provider_fails_open_on_non_200(monkeypatch):
    monkeypatch.setattr("backend.providers.enrichment.epss.get_redis", lambda: None)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    provider = EpssProvider(transport=_transport(handler))
    result = await provider.get("CVE-2021-44228")
    assert result is None


async def test_epss_provider_fails_open_on_malformed_json(monkeypatch):
    monkeypatch.setattr("backend.providers.enrichment.epss.get_redis", lambda: None)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not json")

    provider = EpssProvider(transport=_transport(handler))
    result = await provider.get("CVE-2021-44228")
    assert result is None


async def test_epss_provider_fails_open_on_non_numeric_score(monkeypatch):
    monkeypatch.setattr("backend.providers.enrichment.epss.get_redis", lambda: None)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"status": "OK", "data": [{"cve": "CVE-2021-44228", "epss": "n/a", "percentile": "n/a"}]},
        )

    provider = EpssProvider(transport=_transport(handler))
    result = await provider.get("CVE-2021-44228")
    assert result is None


# ─── EpssProvider: cache hit/miss behaviour ────────────────────────────────


async def test_epss_provider_hits_the_cache_on_the_second_call(monkeypatch):
    redis = FakeRedis()
    monkeypatch.setattr("backend.providers.enrichment.epss.get_redis", lambda: redis)
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json=_SAMPLE_EPSS_RESPONSE)

    provider = EpssProvider(transport=_transport(handler))
    first = await provider.get("CVE-2021-44228")
    second = await provider.get("CVE-2021-44228")

    assert first == second
    assert calls["n"] == 1  # provider was only ever asked once
    assert redis.set_calls == 1


async def test_epss_provider_does_not_cache_a_miss(monkeypatch):
    redis = FakeRedis()
    monkeypatch.setattr("backend.providers.enrichment.epss.get_redis", lambda: redis)
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json={"status": "OK", "data": []})

    provider = EpssProvider(transport=_transport(handler))
    await provider.get("CVE-2099-99999")
    await provider.get("CVE-2099-99999")

    assert calls["n"] == 2  # a miss is never cached, so it's re-fetched
    assert redis.set_calls == 0


async def test_epss_provider_a_broken_cache_does_not_fail_the_lookup(monkeypatch):
    redis = FakeRedis(fail=True)
    monkeypatch.setattr("backend.providers.enrichment.epss.get_redis", lambda: redis)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_SAMPLE_EPSS_RESPONSE)

    provider = EpssProvider(transport=_transport(handler))
    result = await provider.get("CVE-2021-44228")
    assert result is not None  # cache failure did not break the lookup


# ─── KevProvider: catalog parsing ───────────────────────────────────────────


_SAMPLE_KEV_RESPONSE = {
    "title": "CISA KEV",
    "count": 2,
    "vulnerabilities": [
        {"cveID": "CVE-2021-44228", "dateAdded": "2021-12-10"},
        {"cveID": "cve-2020-0001", "dateAdded": "2020-01-01"},
    ],
}


async def test_kev_provider_reports_membership_from_a_real_shaped_catalog(monkeypatch):
    monkeypatch.setattr("backend.providers.enrichment.kev.get_redis", lambda: None)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_SAMPLE_KEV_RESPONSE)

    provider = KevProvider(transport=_transport(handler))
    assert await provider.is_kev("CVE-2021-44228") is True
    assert await provider.is_kev("cve-2020-0001") is True  # case-insensitive
    assert await provider.is_kev("CVE-2099-99999") is False


async def test_kev_provider_catalog_fetch_failure_fails_open_to_false(monkeypatch):
    monkeypatch.setattr("backend.providers.enrichment.kev.get_redis", lambda: None)

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    provider = KevProvider(transport=_transport(handler))
    assert await provider.is_kev("CVE-2021-44228") is False


async def test_kev_provider_non_200_fails_open_to_false(monkeypatch):
    monkeypatch.setattr("backend.providers.enrichment.kev.get_redis", lambda: None)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    provider = KevProvider(transport=_transport(handler))
    assert await provider.is_kev("CVE-2021-44228") is False


async def test_kev_provider_malformed_json_fails_open_to_false(monkeypatch):
    monkeypatch.setattr("backend.providers.enrichment.kev.get_redis", lambda: None)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not json")

    provider = KevProvider(transport=_transport(handler))
    assert await provider.is_kev("CVE-2021-44228") is False


# ─── KevProvider: whole-catalog cache hit/miss behaviour ───────────────────


async def test_kev_provider_caches_the_whole_catalog_across_multiple_cve_checks(monkeypatch):
    redis = FakeRedis()
    monkeypatch.setattr("backend.providers.enrichment.kev.get_redis", lambda: redis)
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json=_SAMPLE_KEV_RESPONSE)

    provider = KevProvider(transport=_transport(handler))
    await provider.is_kev("CVE-2021-44228")
    await provider.is_kev("CVE-2020-0001")
    await provider.is_kev("CVE-9999-00001")

    assert calls["n"] == 1  # one catalog download served all three checks
    assert redis.set_calls == 1


async def test_kev_provider_a_broken_cache_does_not_fail_the_lookup(monkeypatch):
    redis = FakeRedis(fail=True)
    monkeypatch.setattr("backend.providers.enrichment.kev.get_redis", lambda: redis)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_SAMPLE_KEV_RESPONSE)

    provider = KevProvider(transport=_transport(handler))
    assert await provider.is_kev("CVE-2021-44228") is True


async def test_kev_provider_no_redis_configured_still_works(monkeypatch):
    monkeypatch.setattr("backend.providers.enrichment.kev.get_redis", lambda: None)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_SAMPLE_KEV_RESPONSE)

    provider = KevProvider(transport=_transport(handler))
    assert await provider.is_kev("CVE-2021-44228") is True
