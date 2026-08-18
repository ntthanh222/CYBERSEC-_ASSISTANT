"""URL scanner.

Performs a bounded, read-only inspection of a user-supplied URL and turns it
into a risk score with the factors that produced it (``docs/05_DATA_MODEL.md``
requires storing the factors, not just the number).

What this deliberately does **not** do:

* It does not execute, render or parse the response body. The body is read only
  far enough to classify the content type and is never stored.
* It does not download files, follow non-HTTP schemes, or send credentials.
* It does not claim capabilities it lacks. There is no WHOIS/registrar lookup
  or geolocation, so those fields are absent from the response rather than
  filled with invented values (blueprint 2.6: "Không bịa ra 'proxy scan',
  'deep scan' hoặc 'AI scan' nếu không có"). A real third-party reputation
  feed (VirusTotal, see ``reputation`` in the result and
  ``backend/providers/reputation/virustotal.py``) is included when
  configured, kept strictly separate from the local heuristic score below -
  a clean local scan is never conflated with "VirusTotal confirmed safe".

Reachability failures return a scan whose ``status`` is ``failed`` with HTTP
200, following the same convention as ``/api/system/health``: a transport
problem must not look like an API error to the frontend. A target refused by
the SSRF guard is different - that is a client error and returns HTTP 400.
"""
import logging
import time
from dataclasses import asdict, dataclass
from typing import Any, Final, Optional
from urllib.parse import urljoin, urlsplit

import httpx

from backend.config.settings import get_settings
from backend.core.exceptions import (
    BlockedTargetError,
    ConfigurationMissingError,
    ProviderAuthenticationError,
    ProviderRateLimitedError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    UpstreamMalformedError,
)
from backend.providers.reputation.virustotal import VirusTotalProvider
from backend.services.ssrf_guard import ValidatedTarget, assert_peer_allowed, validate_url

logger = logging.getLogger("backend.url_scanner")

USER_AGENT: Final = "CyberSecAssistant-URLScanner/1.0 (+security-scan; read-only)"

#: Response headers worth reporting. An allowlist, so nothing unexpected (a
#: Set-Cookie carrying a session token, for example) is echoed back or stored.
REPORTED_HEADERS: Final = (
    "server",
    "content-type",
    "content-length",
    "strict-transport-security",
    "content-security-policy",
    "x-frame-options",
    "x-content-type-options",
    "location",
)

SUSPICIOUS_TLDS: Final = frozenset(
    {
        "zip", "mov", "xyz", "top", "work", "click", "link", "gq", "cf", "tk",
        "ml", "review", "country", "science", "party", "download", "stream",
        "loan", "date", "racing", "win", "bid", "quest",
    }
)

URL_SHORTENERS: Final = frozenset(
    {
        "bit.ly", "tinyurl.com", "t.co", "goo.gl", "ow.ly", "is.gd", "buff.ly",
        "cutt.ly", "rebrand.ly", "shorturl.at", "rb.gy", "s.id",
    }
)

CREDENTIAL_BAIT_WORDS: Final = (
    "login", "signin", "secure", "verify", "update", "account", "banking",
    "wallet", "confirm", "support", "recovery", "password", "unlock",
)

RISKY_DOWNLOAD_SUFFIXES: Final = (
    ".exe", ".scr", ".msi", ".bat", ".cmd", ".ps1", ".jar", ".apk", ".dmg",
    ".hta", ".vbs", ".js", ".zip", ".rar", ".7z", ".iso",
)


@dataclass(frozen=True)
class Finding:
    code: str
    severity: str
    message: str
    weight: int


def _severity_for(score: int) -> str:
    if score >= 75:
        return "critical"
    if score >= 50:
        return "high"
    if score >= 20:
        return "medium"
    return "low"


def _status_for(score: int) -> str:
    if score >= 75:
        return "critical"
    if score >= 20:
        return "suspicious"
    return "safe"


def _is_ip_literal(hostname: str) -> bool:
    import ipaddress

    try:
        ipaddress.ip_address(hostname.strip("[]"))
    except ValueError:
        return False
    return True


def _registrable_suffix(hostname: str) -> str:
    parts = hostname.rsplit(".", 1)
    return parts[-1].lower() if len(parts) == 2 else ""


def static_findings(target: ValidatedTarget, original_url: str) -> list[Finding]:
    """Findings derivable from the URL itself, before any request is made."""
    findings: list[Finding] = []
    hostname = target.hostname

    if target.had_embedded_credentials:
        findings.append(
            Finding(
                "credentials_in_url",
                "critical",
                "URL này chứa thông tin đăng nhập trước phần hostname. Đây là một "
                "thủ thuật ngụy trang cổ điển; thông tin đăng nhập đã bị loại bỏ "
                "trước khi quét và chưa từng được gửi đi.",
                35,
            )
        )
    if target.scheme != "https":
        findings.append(
            Finding(
                "no_https",
                "medium",
                "URL này dùng HTTP thuần, do đó lưu lượng truyền tải không được "
                "mã hóa cũng như không được xác thực.",
                20,
            )
        )
    if _is_ip_literal(hostname):
        findings.append(
            Finding(
                "ip_literal_host",
                "high",
                "Host là một địa chỉ IP thuần thay vì tên miền, điều mà các dịch vụ "
                "hợp pháp hiếm khi sử dụng cho các liên kết hướng tới người dùng.",
                25,
            )
        )
    if hostname.startswith("xn--") or ".xn--" in hostname:
        findings.append(
            Finding(
                "punycode_host",
                "high",
                "Hostname sử dụng mã hóa punycode/IDN, có thể hiển thị giống hệt "
                "một thương hiệu nổi tiếng (tấn công homograph).",
                25,
            )
        )
    if target.port not in (80, 443):
        findings.append(
            Finding(
                "non_standard_port",
                "medium",
                f"URL này trỏ đến cổng không chuẩn {target.port}.",
                10,
            )
        )
    if _registrable_suffix(hostname) in SUSPICIOUS_TLDS:
        findings.append(
            Finding(
                "suspicious_tld",
                "medium",
                "Tên miền cấp cao nhất này thường bị lạm dụng cho các trang "
                "phishing và lưu trữ mã độc dùng một lần.",
                15,
            )
        )
    if hostname in URL_SHORTENERS:
        findings.append(
            Finding(
                "url_shortener",
                "medium",
                "Liên kết này là một dịch vụ rút gọn URL, nên đích đến thực sự "
                "bị ẩn cho đến khi truy cập.",
                10,
            )
        )
    if hostname.count(".") >= 4:
        findings.append(
            Finding(
                "excessive_subdomains",
                "medium",
                "Hostname có số lượng nhãn tên miền phụ bất thường, thường được "
                "dùng để đẩy tên miền thật ra khỏi tầm nhìn trên di động.",
                10,
            )
        )
    matched_bait = [word for word in CREDENTIAL_BAIT_WORDS if word in hostname]
    if matched_bait and "-" in hostname:
        findings.append(
            Finding(
                "credential_bait_hostname",
                "high",
                "Hostname kết hợp các từ ngữ liên quan đến đăng nhập với dấu gạch "
                "ngang, một mẫu hình phổ biến ở các tên miền phishing giả mạo.",
                15,
            )
        )
    if len(original_url) > 120:
        findings.append(
            Finding(
                "long_url",
                "low",
                "URL này dài bất thường, một cách thường được dùng để che giấu "
                "đích đến thực sự.",
                5,
            )
        )
    path = urlsplit(target.url).path.lower()
    if path.endswith(RISKY_DOWNLOAD_SUFFIXES):
        findings.append(
            Finding(
                "executable_download_path",
                "high",
                "URL này trỏ trực tiếp đến một tệp thực thi hoặc tệp nén.",
                20,
            )
        )
    return findings


def _peer_ip(response: httpx.Response) -> Optional[str]:
    """Best-effort address of the peer actually connected to."""
    stream = response.extensions.get("network_stream")
    if stream is None:
        return None
    try:
        info = stream.get_extra_info("server_addr")
    except Exception:  # noqa: BLE001 - diagnostics only, never fatal
        return None
    if isinstance(info, (tuple, list)) and info:
        return str(info[0])
    return None


def _collect_headers(response: httpx.Response) -> dict[str, str]:
    return {
        name: response.headers[name]
        for name in REPORTED_HEADERS
        if name in response.headers
    }


@dataclass
class FetchResult:
    reachable: bool
    http_status: Optional[int] = None
    final_url: Optional[str] = None
    redirect_chain: list[str] = None  # type: ignore[assignment]
    headers: dict[str, str] = None  # type: ignore[assignment]
    body_truncated: bool = False
    failure_reason: Optional[str] = None
    findings: list[Finding] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self.redirect_chain = self.redirect_chain or []
        self.headers = self.headers or {}
        self.findings = self.findings or []


async def fetch_target(
    target: ValidatedTarget,
    *,
    timeout_seconds: float,
    max_redirects: int,
    max_response_bytes: int,
    transport: Optional[httpx.AsyncBaseTransport] = None,
) -> FetchResult:
    """Fetch ``target`` with redirects followed manually and re-validated."""
    findings: list[Finding] = []
    chain: list[str] = []
    current = target
    origin_host = target.hostname

    async with httpx.AsyncClient(
        follow_redirects=False,
        timeout=timeout_seconds,
        transport=transport,
        headers={"User-Agent": USER_AGENT, "Accept": "*/*"},
        max_redirects=0,
    ) as client:
        for _ in range(max_redirects + 1):
            try:
                async with client.stream("GET", current.url) as response:
                    # Anti-DNS-rebinding: verify what we are actually talking to
                    # before a single byte of the body is consumed.
                    assert_peer_allowed(_peer_ip(response))
                    headers = _collect_headers(response)

                    if response.is_redirect:
                        location = response.headers.get("location", "")
                        if not location:
                            return FetchResult(
                                reachable=True,
                                http_status=response.status_code,
                                final_url=current.url,
                                redirect_chain=chain,
                                headers=headers,
                                findings=findings,
                            )
                        next_url = urljoin(current.url, location)
                        chain.append(next_url)
                        # Each hop is fully re-parsed, re-resolved and
                        # re-checked, so a redirect into RFC1918 space is
                        # refused exactly like a direct attempt would be.
                        current = await validate_url(next_url)
                        if current.hostname != origin_host:
                            findings.append(
                                Finding(
                                    "cross_domain_redirect",
                                    "medium",
                                    "Liên kết này chuyển hướng đến một tên miền khác "
                                    "với tên miền được hiển thị ban đầu.",
                                    15,
                                )
                            )
                            origin_host = current.hostname
                        continue

                    declared = response.headers.get("content-length")
                    truncated = False
                    if declared and declared.isdigit() and int(declared) > max_response_bytes:
                        truncated = True
                    else:
                        read = 0
                        async for chunk in response.aiter_bytes():
                            read += len(chunk)
                            if read > max_response_bytes:
                                truncated = True
                                break

                    if truncated:
                        findings.append(
                            Finding(
                                "response_truncated",
                                "low",
                                "Phản hồi vượt quá giới hạn đọc của trình quét và đã "
                                "bị cắt bớt; chỉ có phần header được kiểm tra đầy đủ.",
                                0,
                            )
                        )

                    content_type = response.headers.get("content-type", "").lower()
                    if any(
                        marker in content_type
                        for marker in ("application/octet-stream", "application/x-msdownload")
                    ):
                        findings.append(
                            Finding(
                                "binary_download_response",
                                "high",
                                "Mục tiêu trả về một tệp nhị phân để tải xuống thay vì một trang web.",
                                20,
                            )
                        )
                    if response.status_code >= 400:
                        findings.append(
                            Finding(
                                "http_error_status",
                                "low",
                                f"Mục tiêu phản hồi với mã HTTP {response.status_code}.",
                                5,
                            )
                        )

                    return FetchResult(
                        reachable=True,
                        http_status=response.status_code,
                        final_url=current.url,
                        redirect_chain=chain,
                        headers=headers,
                        body_truncated=truncated,
                        findings=findings,
                    )
            except httpx.TimeoutException:
                findings.append(
                    Finding(
                        "request_timeout",
                        "medium",
                        "Mục tiêu không phản hồi trong thời gian chờ của trình quét.",
                        0,
                    )
                )
                return FetchResult(
                    reachable=False,
                    redirect_chain=chain,
                    failure_reason="timeout",
                    findings=findings,
                )
            except httpx.HTTPError:
                # Transport/protocol failure. The exception text is not kept:
                # it can contain the full request URL and internal detail.
                findings.append(
                    Finding(
                        "connection_failed",
                        "medium",
                        "Trình quét không thể thiết lập kết nối đến mục tiêu.",
                        0,
                    )
                )
                return FetchResult(
                    reachable=False,
                    redirect_chain=chain,
                    failure_reason="connection_failed",
                    findings=findings,
                )

    findings.append(
        Finding(
            "too_many_redirects",
            "high",
            f"Mục tiêu vượt quá giới hạn chuyển hướng của trình quét là {max_redirects}.",
            15,
        )
    )
    return FetchResult(
        reachable=False,
        redirect_chain=chain,
        failure_reason="too_many_redirects",
        findings=findings,
    )


def build_recommendations(findings: list[Finding], status: str) -> list[str]:
    codes = {finding.code for finding in findings}
    recommendations: list[str] = []
    if "credentials_in_url" in codes:
        recommendations.append(
            "Coi bất kỳ thông tin đăng nhập nào xuất hiện trong liên kết này là đã bị lộ và đổi ngay."
        )
    if "no_https" in codes:
        recommendations.append("Không gửi bất kỳ dữ liệu nào qua liên kết này; nó không được mã hóa.")
    if {"punycode_host", "credential_bait_hostname"} & codes:
        recommendations.append(
            "Kiểm tra từng ký tự của tên miền so với tên miền thật trước khi tin tưởng."
        )
    if {"url_shortener", "cross_domain_redirect"} & codes:
        recommendations.append(
            "Mở rộng liên kết và xác nhận đích đến cuối cùng trước khi truy cập."
        )
    if {"executable_download_path", "binary_download_response"} & codes:
        recommendations.append(
            "Không chạy tệp đã tải xuống; hãy gửi tệp đó đến một sandbox phân tích mã độc."
        )
    if status == "critical":
        recommendations.append(
            "Chặn URL này ở lớp proxy hoặc DNS và cảnh báo cho những người dùng bị ảnh hưởng."
        )
    if not recommendations:
        recommendations.append(
            "Không tìm thấy chỉ báo rủi ro cụ thể nào. Vẫn nên áp dụng sự thận trọng thông thường: "
            "trình quét chỉ kiểm tra cấu trúc và khả năng truy cập, không kiểm tra nội dung trang."
        )
    return recommendations


async def get_url_reputation(
    url: str, *, provider: Optional[VirusTotalProvider] = None
) -> dict[str, Any]:
    """VirusTotal's verdict for ``url``, with every failure mode mapped to
    one of the five honest categories - never silently swallowed into a
    "safe" or "unknown" result that looks the same as "not configured"."""
    resolved = provider or VirusTotalProvider()
    if not resolved.is_configured:
        return {"configured": False, "status": "not_configured", "error_category": "NOT_CONFIGURED"}

    try:
        result = await resolved.get_url_reputation(url)
    except ConfigurationMissingError:
        return {"configured": False, "status": "not_configured", "error_category": "NOT_CONFIGURED"}
    except ProviderAuthenticationError:
        return {"configured": True, "status": "unavailable", "error_category": "INVALID_KEY"}
    except ProviderRateLimitedError:
        return {"configured": True, "status": "unavailable", "error_category": "RATE_LIMITED"}
    except (ProviderTimeoutError, ProviderUnavailableError):
        return {"configured": True, "status": "unavailable", "error_category": "UNAVAILABLE"}
    except UpstreamMalformedError:
        return {"configured": True, "status": "unavailable", "error_category": "DEGRADED"}

    return {"configured": True, "error_category": None, **result}


async def scan_url(
    raw_url: str,
    *,
    transport: Optional[httpx.AsyncBaseTransport] = None,
    reputation_provider: Optional[VirusTotalProvider] = None,
) -> dict[str, Any]:
    """Validate, fetch and score ``raw_url``.

    Raises :class:`BlockedTargetError` or ``InvalidRequestError`` for input the
    scanner refuses; otherwise always returns a result, even when the target is
    unreachable.
    """
    settings = get_settings()
    started = time.perf_counter()

    target = await validate_url(raw_url)
    findings = static_findings(target, raw_url)

    fetched = await fetch_target(
        target,
        timeout_seconds=settings.url_scan_timeout_seconds,
        max_redirects=settings.url_scan_max_redirects,
        max_response_bytes=settings.url_scan_max_response_bytes,
        transport=transport,
    )
    findings.extend(fetched.findings)

    if len(fetched.redirect_chain) >= 2:
        findings.append(
            Finding(
                "long_redirect_chain",
                "medium",
                f"Liên kết này đi qua {len(fetched.redirect_chain)} lần chuyển hướng.",
                10,
            )
        )

    risk_score = min(100, sum(finding.weight for finding in findings))
    status = "failed" if not fetched.reachable else _status_for(risk_score)
    severity = _severity_for(risk_score)

    # VT is an independent lookup against its own database - runs
    # regardless of whether *our* server could reach the target, and never
    # blends into risk_score/severity above (see the module docstring).
    reputation = await get_url_reputation(target.url, provider=reputation_provider)

    return {
        "url": raw_url,
        "normalized_url": target.url,
        "hostname": target.hostname,
        "port": target.port,
        "scheme": target.scheme,
        "has_https": target.scheme == "https",
        "reachable": fetched.reachable,
        "status": status,
        "risk_score": risk_score,
        "severity": severity,
        "http_status": fetched.http_status,
        "final_url": fetched.final_url,
        "redirect_chain": fetched.redirect_chain,
        "redirect_count": len(fetched.redirect_chain),
        "headers": fetched.headers,
        "body_truncated": fetched.body_truncated,
        "failure_reason": fetched.failure_reason,
        "findings": [asdict(finding) for finding in findings],
        "recommendations": build_recommendations(findings, status),
        "reputation": reputation,
        "duration_ms": round((time.perf_counter() - started) * 1000, 2),
    }


def summarize(result: dict[str, Any]) -> str:
    """One-line human summary stored on the history record."""
    if result["status"] == "failed":
        return f"Không thể truy cập ({result.get('failure_reason') or 'unknown'})"
    top = [
        finding["code"]
        for finding in result["findings"]
        if finding["severity"] in ("high", "critical")
    ]
    status_label = {
        "safe": "an toàn",
        "suspicious": "đáng ngờ",
        "critical": "nghiêm trọng",
    }.get(result["status"], result["status"])
    if top:
        return f"{status_label} (rủi ro {result['risk_score']}): {', '.join(top[:3])}"
    return f"{status_label} (rủi ro {result['risk_score']})"


def blocked_summary(error: BlockedTargetError) -> str:
    return f"Bị chặn bởi lớp bảo vệ SSRF: {error.message}"
