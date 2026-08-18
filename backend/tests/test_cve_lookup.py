"""CVE lookup: format validation, provider dispatch and Redis caching."""
import httpx
import pytest

from backend.core.exceptions import (
    InvalidRequestError,
    NotFoundError,
    ProviderAuthenticationError,
    ProviderTimeoutError,
    UpstreamMalformedError,
)
from backend.providers.cve.fixture import FixtureCVEProvider
from backend.providers.cve.nvd import NvdProvider
from backend.services.cve import CveLookupService, validate_cve_id


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


@pytest.mark.parametrize(
    "value",
    ["CVE-2021-44228", "cve-2021-44228", "CVE-1999-0001", "CVE-2024-123456"],
)
def test_validate_cve_id_accepts_well_formed_ids(value):
    assert validate_cve_id(value) == value.upper()


@pytest.mark.parametrize(
    "value", ["not-a-cve", "CVE-2021", "CVE-21-1234", "CVE-2021-1", "", "  ", "CVE_2021_1234"]
)
def test_validate_cve_id_rejects_malformed_ids(value):
    with pytest.raises(InvalidRequestError):
        validate_cve_id(value)


async def test_get_returns_the_fixture_record_and_marks_a_miss(monkeypatch):
    redis = FakeRedis()
    monkeypatch.setattr("backend.services.cve.get_redis", lambda: redis)
    service = CveLookupService(provider=FixtureCVEProvider())

    result = await service.get("CVE-2021-44228", actor="tester")
    assert result["cve_id"] == "CVE-2021-44228"
    assert result["cached"] is False
    assert result["source"] == "nvd"
    assert redis.set_calls == 1


async def test_get_hits_the_cache_on_the_second_call(monkeypatch):
    redis = FakeRedis()
    monkeypatch.setattr("backend.services.cve.get_redis", lambda: redis)
    calls = {"n": 0}

    class CountingProvider(FixtureCVEProvider):
        async def get(self, cve_id: str):
            calls["n"] += 1
            return await super().get(cve_id)

    service = CveLookupService(provider=CountingProvider())
    first = await service.get("CVE-2021-44228", actor="tester")
    second = await service.get("CVE-2021-44228", actor="tester")

    assert first["cached"] is False
    assert second["cached"] is True
    assert calls["n"] == 1  # provider was only ever asked once


async def test_get_raises_not_found_for_an_unknown_cve(monkeypatch):
    monkeypatch.setattr("backend.services.cve.get_redis", lambda: None)
    service = CveLookupService(provider=FixtureCVEProvider())
    with pytest.raises(NotFoundError):
        await service.get("CVE-2099-99999", actor=None)


async def test_a_broken_cache_does_not_fail_the_lookup(monkeypatch):
    redis = FakeRedis(fail=True)
    monkeypatch.setattr("backend.services.cve.get_redis", lambda: redis)
    service = CveLookupService(provider=FixtureCVEProvider())

    result = await service.get("CVE-2021-44228", actor=None)
    assert result["cached"] is False  # cache was skipped, not crashed


async def test_no_redis_configured_still_returns_a_result(monkeypatch):
    monkeypatch.setattr("backend.services.cve.get_redis", lambda: None)
    service = CveLookupService(provider=FixtureCVEProvider())
    result = await service.get("CVE-2021-44228", actor=None)
    assert result["cached"] is False


async def test_search_returns_matching_fixture_records(monkeypatch):
    monkeypatch.setattr("backend.services.cve.get_redis", lambda: None)
    service = CveLookupService(provider=FixtureCVEProvider())
    results = await service.search("log4j", limit=5)
    assert len(results) == 1
    assert results[0]["cve_id"] == "CVE-2021-44228"


async def test_search_rejects_an_empty_query(monkeypatch):
    monkeypatch.setattr("backend.services.cve.get_redis", lambda: None)
    service = CveLookupService(provider=FixtureCVEProvider())
    with pytest.raises(InvalidRequestError):
        await service.search("   ", limit=5)


# --- NVD provider: transport-mocked, never live network -------------------

_SAMPLE_NVD_RESPONSE = {
    "vulnerabilities": [
        {
            "cve": {
                "id": "CVE-2021-44228",
                "published": "2021-12-10T10:15:00.000",
                "lastModified": "2023-11-07T03:34:00.000",
                "descriptions": [{"lang": "en", "value": "Log4Shell RCE."}],
                "metrics": {
                    "cvssMetricV31": [
                        {
                            "cvssData": {
                                "baseScore": 10.0,
                                "baseSeverity": "CRITICAL",
                                "vectorString": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:C/C:H/I:H/A:H",
                            }
                        }
                    ]
                },
                "references": [{"url": "https://nvd.nist.gov/vuln/detail/CVE-2021-44228"}],
                "configurations": [],
            }
        }
    ]
}


def _nvd_transport(handler) -> httpx.MockTransport:
    return httpx.MockTransport(handler)


async def test_nvd_provider_parses_a_real_shaped_response():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_SAMPLE_NVD_RESPONSE)

    provider = NvdProvider(transport=_nvd_transport(handler))
    record = await provider.get("CVE-2021-44228")
    assert record.cvss_score == 10.0
    assert record.severity == "critical"
    assert record.source == "nvd"


async def test_nvd_provider_maps_an_empty_result_to_not_found():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"vulnerabilities": []})

    provider = NvdProvider(transport=_nvd_transport(handler))
    with pytest.raises(NotFoundError):
        await provider.get("CVE-2099-99999")


async def test_nvd_provider_maps_a_404_to_invalid_api_key_not_not_found():
    # Verified directly against the live NVD API: 404 is reserved exclusively
    # for a rejected apiKey (with a "message: Invalid apiKey." response
    # header) - a genuinely nonexistent CVE gets an ordinary 200 with an
    # empty vulnerabilities array instead (see the test above). Silently
    # mapping 404 to "not found" would hide a broken configured key behind a
    # misleading "this CVE does not exist" result.
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, headers={"message": "Invalid apiKey."})

    provider = NvdProvider(transport=_nvd_transport(handler), api_key="some-configured-key")
    with pytest.raises(ProviderAuthenticationError):
        await provider.get("CVE-2021-44228")


async def test_nvd_provider_maps_a_timeout():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timed out", request=request)

    provider = NvdProvider(transport=_nvd_transport(handler), max_attempts=1)
    with pytest.raises(ProviderTimeoutError):
        await provider.get("CVE-2021-44228")


async def test_nvd_provider_maps_a_malformed_response_body():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not json")

    provider = NvdProvider(transport=_nvd_transport(handler), max_attempts=1)
    with pytest.raises(UpstreamMalformedError):
        await provider.get("CVE-2021-44228")
