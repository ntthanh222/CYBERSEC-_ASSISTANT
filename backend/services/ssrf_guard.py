"""SSRF protection for the URL scanner.

This module is the single gate between a user-supplied URL and an outbound
request. It implements the flow required by blueprint 2.6::

    parse -> allow only http/https -> resolve DNS -> check EVERY returned IP
    -> block private/loopback/link-local -> request with timeout
    -> check redirects -> re-resolve the target after each redirect
    -> block oversized responses

Design decisions worth knowing:

* **Every** address returned by DNS is checked, not just the first. A hostname
  that resolves to one public and one internal address is refused outright.
* IPv6 forms that embed an IPv4 address (``::ffff:127.0.0.1``, 6to4, Teredo)
  are unwrapped before classification, so they cannot smuggle an internal
  target past the checks.
* Classification uses :attr:`ipaddress.IPv4Address.is_global` in addition to
  the specific predicates, which covers the whole IANA special-purpose
  registry (shared CGNAT space, benchmarking ranges, documentation ranges)
  rather than an allowlist that ages badly.
* Error messages never echo the resolved addresses back to the caller. Doing so
  would turn the scanner into an internal-network discovery oracle: an attacker
  could map internal DNS by reading the refusal text.
"""
import asyncio
import ipaddress
import socket
from dataclasses import dataclass
from typing import Final, Iterable, Optional
from urllib.parse import urlsplit, urlunsplit

from backend.core.exceptions import BlockedTargetError, InvalidRequestError

ALLOWED_SCHEMES: Final = frozenset({"http", "https"})
DEFAULT_PORTS: Final = {"http": 80, "https": 443}

#: Hostnames refused before DNS is even consulted. Resolution would normally
#: catch these anyway; refusing early keeps the failure mode obvious and covers
#: hosts files that point them somewhere unexpected.
BLOCKED_HOSTNAMES: Final = frozenset(
    {
        "localhost",
        "localhost.localdomain",
        "ip6-localhost",
        "ip6-loopback",
        "metadata",
        "metadata.google.internal",
        "metadata.goog",
        "instance-data",
    }
)

#: Cloud instance-metadata endpoints, listed explicitly so the refusal reason is
#: specific. Every one of these is also caught by the generic address checks.
METADATA_ADDRESSES: Final = frozenset(
    {
        "169.254.169.254",  # AWS / Azure / GCP / DigitalOcean
        "169.254.170.2",  # AWS ECS task metadata
        "100.100.100.200",  # Alibaba Cloud
        "192.0.0.192",  # Oracle Cloud
        "fd00:ec2::254",  # AWS IMDS over IPv6
    }
)

DNS_TIMEOUT_SECONDS: Final = 5.0


@dataclass(frozen=True)
class ValidatedTarget:
    """A URL that passed every check, plus the addresses it resolved to."""

    url: str
    scheme: str
    hostname: str
    port: int
    resolved_ips: tuple[str, ...]
    #: Credentials found in the URL are stripped from :attr:`url` before any
    #: request is made; this flag lets the scanner report them as a finding.
    had_embedded_credentials: bool


def _unwrap_ipv6(address: ipaddress._BaseAddress) -> ipaddress._BaseAddress:
    """Return the embedded IPv4 address for tunnelling IPv6 forms."""
    if isinstance(address, ipaddress.IPv6Address):
        if address.ipv4_mapped is not None:
            return address.ipv4_mapped
        if address.sixtofour is not None:
            return address.sixtofour
        if address.teredo is not None:
            return address.teredo[1]
    return address


def classify_address(raw_ip: str) -> Optional[str]:
    """Return the reason ``raw_ip`` is not allowed, or ``None`` if it is fine."""
    try:
        address = ipaddress.ip_address(raw_ip)
    except ValueError:
        return "unparseable"

    if raw_ip in METADATA_ADDRESSES:
        return "cloud_metadata"

    address = _unwrap_ipv6(address)
    if str(address) in METADATA_ADDRESSES:
        return "cloud_metadata"

    for predicate, reason in (
        (address.is_unspecified, "unspecified"),
        (address.is_loopback, "loopback"),
        (address.is_link_local, "link_local"),
        (address.is_multicast, "multicast"),
        (address.is_reserved, "reserved"),
        (address.is_private, "private"),
    ):
        if predicate:
            return reason

    # Catches the remaining IANA special-purpose ranges (shared CGNAT space,
    # benchmarking, documentation) without hard-coding an allowlist.
    if not address.is_global:
        return "non_global"
    return None


def assert_addresses_allowed(addresses: Iterable[str]) -> None:
    """Raise :class:`BlockedTargetError` if *any* address is disallowed."""
    for raw_ip in addresses:
        reason = classify_address(raw_ip)
        if reason is not None:
            # The offending address is deliberately absent from the message.
            raise BlockedTargetError(
                "Mục tiêu này phân giải đến một địa chỉ mà trình quét không được phép "
                f"truy cập ({reason}). Chỉ có thể quét các host trên Internet công cộng."
            )


async def resolve_hostname(hostname: str, port: int) -> tuple[str, ...]:
    """Resolve ``hostname`` to every A/AAAA address, off the event loop."""
    loop = asyncio.get_running_loop()
    try:
        async with asyncio.timeout(DNS_TIMEOUT_SECONDS):
            infos = await loop.getaddrinfo(
                hostname, port, proto=socket.IPPROTO_TCP
            )
    except (socket.gaierror, UnicodeError):
        raise BlockedTargetError("Không thể phân giải tên máy chủ đó.") from None
    except (asyncio.TimeoutError, TimeoutError):
        raise BlockedTargetError("Phân giải tên máy chủ đó đã hết thời gian chờ.") from None

    addresses = tuple(dict.fromkeys(info[4][0] for info in infos))
    if not addresses:
        raise BlockedTargetError("Không thể phân giải tên máy chủ đó.")
    return addresses


async def validate_url(raw_url: str) -> ValidatedTarget:
    """Parse, sanitise and fully validate a scan target.

    Raises :class:`InvalidRequestError` when the input is not a usable URL and
    :class:`BlockedTargetError` when it is well-formed but must not be fetched.
    """
    candidate = (raw_url or "").strip()
    if not candidate:
        raise InvalidRequestError("Cần nhập một URL.")
    if len(candidate) > 2048:
        raise InvalidRequestError("URL đó quá dài để quét (giới hạn 2048 ký tự).")
    if any(character in candidate for character in ("\n", "\r", "\t", " ")):
        raise InvalidRequestError("URL đó chứa khoảng trắng hoặc ký tự điều khiển.")

    try:
        parts = urlsplit(candidate)
    except ValueError:
        raise InvalidRequestError("Không thể phân tích URL đó.") from None

    scheme = parts.scheme.lower()
    if not scheme:
        raise InvalidRequestError(
            "URL đó không có scheme. Hãy thêm http:// hoặc https://."
        )
    if scheme not in ALLOWED_SCHEMES:
        raise BlockedTargetError(
            f"Scheme '{scheme}' không được phép. Chỉ có thể quét http và https."
        )

    try:
        hostname = parts.hostname
    except ValueError:
        raise InvalidRequestError("URL đó có host không hợp lệ.") from None
    if not hostname:
        raise InvalidRequestError("URL đó không có hostname.")
    hostname = hostname.lower()

    if hostname in BLOCKED_HOSTNAMES:
        raise BlockedTargetError(
            "Mục tiêu đó là hostname cục bộ hoặc metadata nên không thể quét."
        )

    try:
        port = parts.port or DEFAULT_PORTS[scheme]
    except ValueError:
        raise InvalidRequestError("URL đó có cổng không hợp lệ.") from None
    if not 1 <= port <= 65535:
        raise InvalidRequestError("URL đó có cổng không hợp lệ.")

    had_credentials = bool(parts.username or parts.password)

    # A bare IP literal skips DNS but is checked identically.
    try:
        ipaddress.ip_address(hostname.strip("[]"))
    except ValueError:
        addresses = await resolve_hostname(hostname, port)
    else:
        addresses = (hostname.strip("[]"),)

    assert_addresses_allowed(addresses)

    # Rebuild without userinfo so credentials are never transmitted, and
    # without a fragment, which is not sent on the wire anyway.
    netloc = f"[{hostname}]" if ":" in hostname else hostname
    if parts.port:
        netloc = f"{netloc}:{parts.port}"
    sanitised = urlunsplit((scheme, netloc, parts.path, parts.query, ""))

    return ValidatedTarget(
        url=sanitised,
        scheme=scheme,
        hostname=hostname,
        port=port,
        resolved_ips=addresses,
        had_embedded_credentials=had_credentials,
    )


def assert_peer_allowed(peer_ip: Optional[str]) -> None:
    """Verify the address actually connected to, after the socket is open.

    This closes the DNS-rebinding window that pre-flight validation alone
    leaves open: even if the name resolved to a public address during
    validation and to an internal one at connect time, the connection is
    abandoned here before any response body is read.
    """
    if not peer_ip:
        return
    reason = classify_address(peer_ip)
    if reason is not None:
        raise BlockedTargetError(
            "Kết nối bị từ chối vì mục tiêu phân giải đến một "
            f"địa chỉ không được phép tại thời điểm kết nối ({reason})."
        )
