"""VirusTotal URL reputation provider (API v3).

Deliberately separate from the local SSRF/heuristic scanner
(``backend/services/url_scanner.py``) - the two answer different questions
that must never be blended into one score: "does this URL/request look
structurally suspicious" (local, always available, no network dependency)
versus "has the security community already flagged this URL" (external,
opt-in, requires a configured key). A URL with clean local findings and no
VirusTotal verdict must never be reported as "safe" on that basis alone -
the caller is responsible for keeping both facts visible separately; this
provider only ever answers "what does VirusTotal say", nothing more.

Error mapping mirrors :mod:`backend.providers.cve.nvd` and
:mod:`backend.providers.llm.gemini`: transport/5xx retried a bounded number
of times, 429 mapped to ``ProviderRateLimitedError``, 401/403 mapped to
``ProviderAuthenticationError`` (verified against VT's documented API-key
auth model - a rejected ``x-apikey`` header returns 401), and a response
that does not parse mapped to ``UpstreamMalformedError`` rather than allowed
to propagate a raw upstream body to the client.
"""
from __future__ import annotations

import asyncio
import base64
import logging
from typing import Any, Final, Optional

import httpx

from backend.config.settings import get_settings
from backend.core.exceptions import (
    ConfigurationMissingError,
    ProviderAuthenticationError,
    ProviderRateLimitedError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    UpstreamMalformedError,
)

logger = logging.getLogger("backend.providers.virustotal")

DEFAULT_BASE_URL: Final = "https://www.virustotal.com/api/v3"
REQUEST_TIMEOUT_SECONDS: Final = 15.0
MAX_ATTEMPTS: Final = 3
RETRY_BACKOFF_SECONDS: Final = 1.0
# How long to wait for a freshly-submitted analysis to finish before giving
# up and honestly reporting "pending" - VT's own queue can take much longer
# than a single HTTP request should ever block a caller for.
POLL_ATTEMPTS: Final = 3
POLL_INTERVAL_SECONDS: Final = 2.0


def _url_id(url: str) -> str:
    """VirusTotal's URL identifier: base64url(url), no padding - documented
    at https://docs.virustotal.com/reference/url-object, verified live."""
    return base64.urlsafe_b64encode(url.encode()).decode().rstrip("=")


class VirusTotalProvider:
    name = "virustotal"

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        base_url: str = DEFAULT_BASE_URL,
        transport: Optional[httpx.AsyncBaseTransport] = None,
        timeout_seconds: float = REQUEST_TIMEOUT_SECONDS,
        max_attempts: int = MAX_ATTEMPTS,
        poll_attempts: int = POLL_ATTEMPTS,
        poll_interval_seconds: float = POLL_INTERVAL_SECONDS,
    ) -> None:
        settings = get_settings()
        self._api_key = api_key if api_key is not None else settings.virustotal_api_key
        self._base_url = base_url.rstrip("/")
        self._transport = transport
        self._timeout_seconds = timeout_seconds
        self._max_attempts = max_attempts
        self._poll_attempts = poll_attempts
        self._poll_interval_seconds = poll_interval_seconds

    @property
    def is_configured(self) -> bool:
        return bool(self._api_key)

    async def get_url_reputation(self, url: str) -> dict[str, Any]:
        """Real VirusTotal reputation for ``url``.

        Returns an existing report if VT has already scanned this URL
        (the common case - most URLs a real user checks have been seen
        before). Otherwise submits it fresh and polls briefly. Never
        fabricates a verdict: an analysis still running after the poll
        budget is reported as ``status: "pending"``, honestly, rather than
        blocking the caller indefinitely or guessing a result.
        """
        if not self._api_key:
            raise ConfigurationMissingError("VirusTotal is not configured on this server.")

        existing = await self._get_existing_report(url)
        if existing is not None:
            return existing

        analysis_id = await self._submit_url(url)
        for attempt in range(self._poll_attempts):
            if attempt:
                await asyncio.sleep(self._poll_interval_seconds)
            result = await self._get_analysis(analysis_id)
            if result is not None:
                return result

        return {
            "status": "pending",
            "malicious": 0,
            "suspicious": 0,
            "harmless": 0,
            "undetected": 0,
            "permalink": self._permalink(url),
        }

    async def _get_existing_report(self, url: str) -> Optional[dict[str, Any]]:
        response = await self._request("GET", f"/urls/{_url_id(url)}")
        if response.status_code == 404:
            return None
        data = self._parse_json(response)
        return self._stats_from_report(data, permalink=self._permalink(url))

    async def _submit_url(self, url: str) -> str:
        response = await self._request(
            "POST",
            "/urls",
            data={"url": url},
            headers_extra={"content-type": "application/x-www-form-urlencoded"},
        )
        data = self._parse_json(response)
        try:
            return data["data"]["id"]
        except (KeyError, TypeError) as exc:
            raise UpstreamMalformedError() from exc

    async def _get_analysis(self, analysis_id: str) -> Optional[dict[str, Any]]:
        response = await self._request("GET", f"/analyses/{analysis_id}")
        data = self._parse_json(response)
        try:
            status = data["data"]["attributes"]["status"]
        except (KeyError, TypeError) as exc:
            raise UpstreamMalformedError() from exc
        if status != "completed":
            return None
        try:
            stats = data["data"]["attributes"]["stats"]
        except (KeyError, TypeError) as exc:
            raise UpstreamMalformedError() from exc
        return {
            "status": "completed",
            "malicious": int(stats.get("malicious", 0)),
            "suspicious": int(stats.get("suspicious", 0)),
            "harmless": int(stats.get("harmless", 0)),
            "undetected": int(stats.get("undetected", 0)),
            "permalink": None,
        }

    @staticmethod
    def _stats_from_report(data: dict[str, Any], *, permalink: str) -> dict[str, Any]:
        try:
            stats = data["data"]["attributes"]["last_analysis_stats"]
        except (KeyError, TypeError) as exc:
            raise UpstreamMalformedError() from exc
        return {
            "status": "completed",
            "malicious": int(stats.get("malicious", 0)),
            "suspicious": int(stats.get("suspicious", 0)),
            "harmless": int(stats.get("harmless", 0)),
            "undetected": int(stats.get("undetected", 0)),
            "permalink": permalink,
        }

    @staticmethod
    def _permalink(url: str) -> str:
        return f"https://www.virustotal.com/gui/url/{_url_id(url)}"

    async def _request(
        self,
        method: str,
        path: str,
        *,
        data: Optional[dict[str, Any]] = None,
        headers_extra: Optional[dict[str, str]] = None,
    ) -> httpx.Response:
        headers = {"x-apikey": self._api_key}
        if headers_extra:
            headers.update(headers_extra)

        last_error: Exception = ProviderUnavailableError()
        async with httpx.AsyncClient(
            timeout=self._timeout_seconds, transport=self._transport
        ) as client:
            for attempt in range(1, self._max_attempts + 1):
                try:
                    response = await client.request(
                        method, f"{self._base_url}{path}", data=data, headers=headers
                    )
                except httpx.TimeoutException:
                    last_error = ProviderTimeoutError()
                except httpx.HTTPError:
                    last_error = ProviderUnavailableError()
                else:
                    if response.status_code == 429:
                        raise ProviderRateLimitedError(
                            "VirusTotal rate-limited this request. Try again shortly."
                        )
                    if response.status_code in (401, 403):
                        raise ProviderAuthenticationError(
                            "VirusTotal rejected the configured API key."
                        )
                    if response.status_code == 404:
                        # Caller-handled: "no existing report for this URL yet",
                        # not an error - callers that don't expect a 404 here
                        # (submit/analysis lookups) still fall through to the
                        # generic 4xx branch below via UpstreamMalformedError
                        # on the caller's own key lookup.
                        return response
                    if 400 <= response.status_code < 500:
                        raise UpstreamMalformedError("VirusTotal rejected the request.")
                    if response.status_code >= 500:
                        last_error = ProviderUnavailableError()
                    else:
                        return response

                if attempt < self._max_attempts:
                    await asyncio.sleep(RETRY_BACKOFF_SECONDS * attempt)

        logger.warning(
            "virustotal_request_failed",
            extra={"fields": {"attempts": self._max_attempts, "error": type(last_error).__name__}},
        )
        raise last_error

    @staticmethod
    def _parse_json(response: httpx.Response) -> dict[str, Any]:
        try:
            data = response.json()
        except ValueError as exc:
            raise UpstreamMalformedError() from exc
        if not isinstance(data, dict):
            raise UpstreamMalformedError()
        return data
