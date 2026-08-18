"""SSRF guard: pure unit coverage of address classification and validation,
with DNS resolution stubbed so these tests never touch the network."""

import pytest

from backend.core.exceptions import BlockedTargetError, InvalidRequestError
from backend.services import ssrf_guard


def _stub_resolve(monkeypatch, mapping: dict[str, tuple[str, ...]]) -> None:
    async def fake_resolve(hostname: str, port: int) -> tuple[str, ...]:
        try:
            return mapping[hostname]
        except KeyError:
            raise BlockedTargetError("That hostname could not be resolved.") from None

    monkeypatch.setattr(ssrf_guard, "resolve_hostname", fake_resolve)


@pytest.mark.parametrize(
    ("address", "expected_reason"),
    [
        ("127.0.0.1", "loopback"),
        ("127.53.0.1", "loopback"),
        ("10.0.0.1", "private"),
        ("172.16.5.5", "private"),
        ("192.168.1.1", "private"),
        ("169.254.169.254", "cloud_metadata"),
        ("169.254.1.1", "link_local"),
        ("0.0.0.0", "unspecified"),
        ("224.0.0.1", "multicast"),
        ("100.64.0.1", "non_global"),  # shared CGNAT space
        ("::1", "loopback"),
        ("fc00::1", "private"),
        ("fe80::1", "link_local"),
        ("::ffff:127.0.0.1", "loopback"),  # IPv4-mapped IPv6
    ],
)
def test_classify_address_blocks_internal_ranges(address, expected_reason):
    assert ssrf_guard.classify_address(address) == expected_reason


def test_classify_address_allows_public_ip():
    assert ssrf_guard.classify_address("93.184.216.34") is None


def test_classify_address_rejects_unparseable_input():
    assert ssrf_guard.classify_address("not-an-ip") == "unparseable"


async def test_validate_url_allows_a_public_https_url(monkeypatch):
    _stub_resolve(monkeypatch, {"example.com": ("93.184.216.34",)})
    target = await ssrf_guard.validate_url("https://example.com/path?x=1")
    assert target.hostname == "example.com"
    assert target.resolved_ips == ("93.184.216.34",)
    assert target.had_embedded_credentials is False


async def test_validate_url_blocks_localhost_by_name(monkeypatch):
    with pytest.raises(BlockedTargetError):
        await ssrf_guard.validate_url("http://localhost/")


async def test_validate_url_blocks_a_private_ipv4_literal():
    with pytest.raises(BlockedTargetError):
        await ssrf_guard.validate_url("http://10.0.0.5/")


async def test_validate_url_blocks_a_private_ipv6_literal():
    with pytest.raises(BlockedTargetError):
        await ssrf_guard.validate_url("http://[fc00::1]/")


async def test_validate_url_blocks_when_any_resolved_address_is_internal(monkeypatch):
    # A hostname that resolves to one public and one internal address must be
    # refused outright - the client cannot control which address a redirect or
    # a subsequent request would actually use.
    _stub_resolve(
        monkeypatch, {"mixed.example": ("93.184.216.34", "127.0.0.1")}
    )
    with pytest.raises(BlockedTargetError):
        await ssrf_guard.validate_url("http://mixed.example/")


async def test_validate_url_blocks_the_metadata_endpoint():
    with pytest.raises(BlockedTargetError):
        await ssrf_guard.validate_url("http://169.254.169.254/latest/meta-data/")


async def test_validate_url_blocks_a_disallowed_scheme():
    with pytest.raises(BlockedTargetError):
        await ssrf_guard.validate_url("ftp://example.com/")


async def test_validate_url_rejects_a_url_with_no_scheme():
    with pytest.raises(InvalidRequestError):
        await ssrf_guard.validate_url("example.com/path")


async def test_validate_url_rejects_an_empty_url():
    with pytest.raises(InvalidRequestError):
        await ssrf_guard.validate_url("   ")


async def test_validate_url_rejects_whitespace_in_the_url():
    with pytest.raises(InvalidRequestError):
        await ssrf_guard.validate_url("http://example.com/ path")


async def test_validate_url_strips_embedded_credentials(monkeypatch):
    _stub_resolve(monkeypatch, {"example.com": ("93.184.216.34",)})
    target = await ssrf_guard.validate_url("https://user:secret@example.com/")
    assert target.had_embedded_credentials is True
    assert "user" not in target.url
    assert "secret" not in target.url


async def test_validate_url_resolution_failure_is_blocked(monkeypatch):
    _stub_resolve(monkeypatch, {})
    with pytest.raises(BlockedTargetError):
        await ssrf_guard.validate_url("http://does-not-exist.invalid/")


def test_assert_peer_allowed_rejects_a_rebound_address():
    with pytest.raises(BlockedTargetError):
        ssrf_guard.assert_peer_allowed("127.0.0.1")


def test_assert_peer_allowed_accepts_a_public_address():
    ssrf_guard.assert_peer_allowed("93.184.216.34")


def test_assert_peer_allowed_ignores_a_missing_address():
    ssrf_guard.assert_peer_allowed(None)
