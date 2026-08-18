"""URL scanner: fetch/scoring logic against a mocked transport (no live network)."""
import httpx
import pytest

from backend.core.exceptions import (
    BlockedTargetError,
    InvalidRequestError,
    ProviderAuthenticationError,
    ProviderRateLimitedError,
)
from backend.providers.reputation.virustotal import VirusTotalProvider
from backend.services import ssrf_guard
from backend.services.url_scanner import get_url_reputation, scan_url


def _stub_resolve(monkeypatch, mapping: dict[str, tuple[str, ...]]) -> None:
    async def fake_resolve(hostname: str, port: int) -> tuple[str, ...]:
        return mapping[hostname]

    monkeypatch.setattr(ssrf_guard, "resolve_hostname", fake_resolve)


def _transport(handler) -> httpx.MockTransport:
    return httpx.MockTransport(handler)


async def test_scan_reports_safe_for_a_clean_https_site(monkeypatch):
    _stub_resolve(monkeypatch, {"example.com": ("93.184.216.34",)})

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "text/html"}, content=b"<html></html>")

    result = await scan_url("https://example.com/", transport=_transport(handler))
    assert result["status"] == "safe"
    assert result["reachable"] is True
    assert result["risk_score"] < 20
    assert result["findings"] == []


async def test_scan_flags_plain_http(monkeypatch):
    _stub_resolve(monkeypatch, {"example.com": ("93.184.216.34",)})

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"ok")

    result = await scan_url("http://example.com/", transport=_transport(handler))
    codes = {finding["code"] for finding in result["findings"]}
    assert "no_https" in codes
    assert result["risk_score"] >= 20


async def test_scan_flags_an_ip_literal_host(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"ok")

    result = await scan_url("http://93.184.216.34/", transport=_transport(handler))
    codes = {finding["code"] for finding in result["findings"]}
    assert "ip_literal_host" in codes


async def test_scan_flags_a_suspicious_tld(monkeypatch):
    _stub_resolve(monkeypatch, {"free-prize.top": ("93.184.216.34",)})

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"ok")

    result = await scan_url("https://free-prize.top/", transport=_transport(handler))
    codes = {finding["code"] for finding in result["findings"]}
    assert "suspicious_tld" in codes


async def test_scan_flags_an_executable_download_path(monkeypatch):
    _stub_resolve(monkeypatch, {"example.com": ("93.184.216.34",)})

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"MZ")

    result = await scan_url(
        "https://example.com/download/update.exe", transport=_transport(handler)
    )
    codes = {finding["code"] for finding in result["findings"]}
    assert "executable_download_path" in codes
    assert result["status"] in ("suspicious", "critical")


async def test_scan_rejects_a_malformed_url():
    with pytest.raises(InvalidRequestError):
        await scan_url("not a url at all")


async def test_scan_blocks_localhost():
    with pytest.raises(BlockedTargetError):
        await scan_url("http://127.0.0.1/")


async def test_scan_blocks_a_private_ipv4():
    with pytest.raises(BlockedTargetError):
        await scan_url("http://10.0.0.1/")


async def test_scan_blocks_a_private_ipv6():
    with pytest.raises(BlockedTargetError):
        await scan_url("http://[fd00::1]/")


async def test_scan_follows_and_revalidates_a_safe_redirect(monkeypatch):
    _stub_resolve(
        monkeypatch,
        {"short.example": ("93.184.216.34",), "landing.example": ("93.184.216.34",)},
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "short.example":
            return httpx.Response(302, headers={"location": "https://landing.example/"})
        return httpx.Response(200, content=b"ok")

    result = await scan_url("https://short.example/", transport=_transport(handler))
    assert result["reachable"] is True
    assert result["redirect_count"] == 1
    assert result["final_url"] == "https://landing.example/"
    codes = {finding["code"] for finding in result["findings"]}
    assert "cross_domain_redirect" in codes


async def test_scan_blocks_a_redirect_into_a_private_network(monkeypatch):
    _stub_resolve(monkeypatch, {"evil.example": ("93.184.216.34",)})

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "http://127.0.0.1/admin"})

    with pytest.raises(BlockedTargetError):
        await scan_url("https://evil.example/", transport=_transport(handler))


async def test_scan_reports_unreachable_target_on_timeout(monkeypatch):
    _stub_resolve(monkeypatch, {"slow.example": ("93.184.216.34",)})

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timed out", request=request)

    result = await scan_url("https://slow.example/", transport=_transport(handler))
    assert result["reachable"] is False
    assert result["status"] == "failed"
    assert result["failure_reason"] == "timeout"


async def test_scan_reports_unreachable_target_on_connection_error(monkeypatch):
    _stub_resolve(monkeypatch, {"down.example": ("93.184.216.34",)})

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    result = await scan_url("https://down.example/", transport=_transport(handler))
    assert result["reachable"] is False
    assert result["failure_reason"] == "connection_failed"


async def test_scan_truncates_an_oversized_response(monkeypatch):
    _stub_resolve(monkeypatch, {"big.example": ("93.184.216.34",)})

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-length": "999999999"},
            content=b"x" * 10,
        )

    result = await scan_url("https://big.example/", transport=_transport(handler))
    assert result["body_truncated"] is True
    codes = {finding["code"] for finding in result["findings"]}
    assert "response_truncated" in codes


async def test_scan_stops_after_the_configured_redirect_limit(monkeypatch):
    _stub_resolve(monkeypatch, {f"hop{i}.example": ("93.184.216.34",) for i in range(10)})

    def handler(request: httpx.Request) -> httpx.Response:
        host = request.url.host
        index = int(host[3:].split(".")[0])
        return httpx.Response(
            302, headers={"location": f"https://hop{index + 1}.example/"}
        )

    result = await scan_url("https://hop0.example/", transport=_transport(handler))
    assert result["reachable"] is False
    assert result["failure_reason"] == "too_many_redirects"


# --- VirusTotal reputation integration ---------------------------------


async def test_scan_reports_not_configured_when_no_virustotal_key_is_set(monkeypatch):
    _stub_resolve(monkeypatch, {"clean.example": ("93.184.216.34",)})

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"<html></html>")

    result = await scan_url("https://clean.example/", transport=_transport(handler))
    assert result["reputation"]["configured"] is False
    assert result["reputation"]["status"] == "not_configured"
    assert result["reputation"]["error_category"] == "NOT_CONFIGURED"


async def test_scan_includes_a_real_virustotal_verdict_kept_separate_from_risk_score(
    monkeypatch,
):
    """The core requirement from the master prompt: local heuristic score
    and VirusTotal's verdict never blend into one number - a locally-clean
    scan (risk_score stays whatever the local findings alone produce) can
    still carry a VirusTotal malicious count, and the caller must be able
    to see both independently."""
    _stub_resolve(monkeypatch, {"clean.example": ("93.184.216.34",)})

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"<html></html>")

    def vt_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": {
                    "attributes": {
                        "last_analysis_stats": {
                            "malicious": 5,
                            "suspicious": 2,
                            "harmless": 50,
                            "undetected": 10,
                        }
                    }
                }
            },
        )

    vt_provider = VirusTotalProvider(api_key="x", transport=_transport(vt_handler))
    result = await scan_url(
        "https://clean.example/", transport=_transport(handler), reputation_provider=vt_provider
    )

    assert result["reputation"]["configured"] is True
    assert result["reputation"]["status"] == "completed"
    assert result["reputation"]["malicious"] == 5
    # Local risk_score is derived only from local findings (static_findings +
    # fetch findings) - it must not silently jump because VirusTotal found
    # something local heuristics never could have detected on their own.
    assert result["risk_score"] < 50


async def test_get_url_reputation_maps_authentication_error_to_invalid_key():
    class _FailingProvider:
        is_configured = True

        async def get_url_reputation(self, url):
            raise ProviderAuthenticationError()

    result = await get_url_reputation("https://example.com", provider=_FailingProvider())
    assert result["error_category"] == "INVALID_KEY"
    assert result["status"] == "unavailable"


async def test_get_url_reputation_maps_rate_limited():
    class _FailingProvider:
        is_configured = True

        async def get_url_reputation(self, url):
            raise ProviderRateLimitedError()

    result = await get_url_reputation("https://example.com", provider=_FailingProvider())
    assert result["error_category"] == "RATE_LIMITED"
