"""VirusTotal provider: request shaping, submit/poll flow, and error mapping.

The existing-report and submit/analysis response shapes below are not
guesses - the existing-report shape (data.attributes.last_analysis_stats)
was verified directly against the live API for a known-scanned URL; submit/
analysis follows VirusTotal's documented v3 API contract.
"""
import httpx
import pytest

from backend.core.exceptions import (
    ConfigurationMissingError,
    ProviderAuthenticationError,
    ProviderRateLimitedError,
    ProviderUnavailableError,
    UpstreamMalformedError,
)
from backend.providers.reputation.virustotal import VirusTotalProvider

EXISTING_REPORT_BODY = {
    "data": {
        "id": "aHR0cHM6Ly93d3cuZ29vZ2xlLmNvbS8",
        "attributes": {
            "last_analysis_stats": {
                "malicious": 0,
                "suspicious": 0,
                "undetected": 29,
                "harmless": 63,
                "timeout": 0,
            }
        },
    }
}

SUBMIT_BODY = {"data": {"type": "analysis", "id": "u-abc123-1700000000"}}
ANALYSIS_PENDING_BODY = {"data": {"attributes": {"status": "queued"}}}
ANALYSIS_COMPLETED_BODY = {
    "data": {
        "attributes": {
            "status": "completed",
            "stats": {"malicious": 2, "suspicious": 1, "harmless": 60, "undetected": 10},
        }
    }
}


def _provider(handler, **kwargs) -> VirusTotalProvider:
    return VirusTotalProvider(
        api_key="test-key",
        transport=httpx.MockTransport(handler),
        poll_interval_seconds=0.0,
        **kwargs,
    )


def test_is_configured_reflects_the_api_key():
    assert VirusTotalProvider(api_key="x").is_configured is True
    assert VirusTotalProvider(api_key="").is_configured is False


async def test_get_url_reputation_raises_configuration_missing_without_a_key():
    provider = VirusTotalProvider(api_key="")
    with pytest.raises(ConfigurationMissingError):
        await provider.get_url_reputation("https://example.com")


async def test_get_url_reputation_returns_an_existing_report_verbatim():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = dict(request.headers)
        captured["path"] = request.url.path
        return httpx.Response(200, json=EXISTING_REPORT_BODY)

    provider = _provider(handler)
    result = await provider.get_url_reputation("https://www.google.com/")

    assert result["status"] == "completed"
    assert result["malicious"] == 0
    assert result["harmless"] == 63
    assert result["undetected"] == 29
    assert result["permalink"] is not None
    assert captured["headers"]["x-apikey"] == "test-key"
    assert "test-key" not in str(result)


async def test_get_url_reputation_submits_and_polls_when_no_existing_report():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if request.method == "GET" and "/urls/" in request.url.path:
            return httpx.Response(404, json={"error": {"code": "NotFoundError"}})
        if request.method == "POST" and request.url.path.endswith("/urls"):
            return httpx.Response(200, json=SUBMIT_BODY)
        if "/analyses/" in request.url.path:
            return httpx.Response(200, json=ANALYSIS_COMPLETED_BODY)
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    provider = _provider(handler)
    result = await provider.get_url_reputation("https://a-brand-new-url.example/never-seen")

    assert result["status"] == "completed"
    assert result["malicious"] == 2
    assert result["suspicious"] == 1


async def test_get_url_reputation_reports_pending_if_analysis_never_completes_in_time():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and "/urls/" in request.url.path:
            return httpx.Response(404, json={"error": {"code": "NotFoundError"}})
        if request.method == "POST" and request.url.path.endswith("/urls"):
            return httpx.Response(200, json=SUBMIT_BODY)
        return httpx.Response(200, json=ANALYSIS_PENDING_BODY)

    provider = _provider(handler, poll_attempts=2)
    result = await provider.get_url_reputation("https://still-scanning.example")

    assert result["status"] == "pending"
    assert result["malicious"] == 0
    assert result["permalink"] is not None


async def test_get_url_reputation_raises_authentication_error_on_401():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"code": "WrongCredentialsError"}})

    provider = _provider(handler)
    with pytest.raises(ProviderAuthenticationError):
        await provider.get_url_reputation("https://example.com")


async def test_get_url_reputation_raises_rate_limited_on_429():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": {"code": "QuotaExceededError"}})

    provider = _provider(handler)
    with pytest.raises(ProviderRateLimitedError):
        await provider.get_url_reputation("https://example.com")


async def test_get_url_reputation_raises_unavailable_on_persistent_5xx():
    provider = _provider(lambda request: httpx.Response(503), max_attempts=2)
    with pytest.raises(ProviderUnavailableError):
        await provider.get_url_reputation("https://example.com")


async def test_get_url_reputation_raises_malformed_on_an_unexpected_report_shape():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": {"attributes": {}}})

    provider = _provider(handler)
    with pytest.raises(UpstreamMalformedError):
        await provider.get_url_reputation("https://example.com")
