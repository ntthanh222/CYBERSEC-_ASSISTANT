"""NIST NVD CVE provider.

Talks to the public NVD REST API 2.0 (https://nvd.nist.gov). ``NIST_NVD_API_KEY``
is optional - the API works without one at a lower rate limit - so this
provider is "configured" (usable) with or without a key. What Redis caching
buys is staying inside that anonymous rate limit at all.

Failure mapping mirrors :mod:`backend.providers.llm.gemini`: transport/5xx
retried a bounded number of times, 429 mapped to ``ProviderRateLimitedError``,
and a response that does not parse mapped to ``UpstreamMalformedError``
rather than allowed to propagate a raw upstream body to the client.

NVD's actual semantics for "not found" vs. "your API key is invalid" are the
opposite of what the endpoint's naming suggests, verified directly against
the live API: a genuinely nonexistent CVE gets an ordinary 200 with an empty
``vulnerabilities`` array (handled by the caller, :meth:`get`, already) -
NVD's 404 is reserved *exclusively* for a rejected ``apiKey`` (confirmed via
its ``message: Invalid apiKey.`` response header), even for a real CVE ID.
Treating 404 as "not found" would silently hide a broken/invalid configured
key behind a misleading "this CVE does not exist" result - so 404 is mapped
to :class:`~backend.core.exceptions.ProviderAuthenticationError` instead.
"""
import asyncio
import logging
from datetime import datetime
from typing import Any, Final, Optional, Sequence

import httpx

from backend.config.settings import get_settings
from backend.core.exceptions import (
    NotFoundError,
    ProviderAuthenticationError,
    ProviderRateLimitedError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    UpstreamMalformedError,
)
from backend.providers.cve.base import BaseCVEProvider, CVERecord

logger = logging.getLogger("backend.providers.nvd")

DEFAULT_BASE_URL: Final = "https://services.nvd.nist.gov/rest/json/cves/2.0"
REQUEST_TIMEOUT_SECONDS: Final = 15.0
MAX_ATTEMPTS: Final = 3
RETRY_BACKOFF_SECONDS: Final = 1.0


def _parse_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _extract_metrics(cve: dict[str, Any]) -> tuple[Optional[float], Optional[str], Optional[str]]:
    metrics = cve.get("metrics", {})
    # Prefer the newest CVSS version available; NVD publishes several.
    for key in ("cvssMetricV31", "cvssMetricV30", "cvssMetricV2"):
        entries = metrics.get(key)
        if entries:
            data = entries[0].get("cvssData", {})
            score = data.get("baseScore")
            severity = data.get("baseSeverity") or entries[0].get("baseSeverity")
            vector = data.get("vectorString")
            return score, (severity.lower() if severity else None), vector
    return None, None, None


def _extract_description(cve: dict[str, Any]) -> str:
    for entry in cve.get("descriptions", []):
        if entry.get("lang") == "en":
            return entry.get("value", "")
    descriptions = cve.get("descriptions", [])
    return descriptions[0].get("value", "") if descriptions else ""


def _extract_products(cve: dict[str, Any]) -> tuple[str, ...]:
    products: list[str] = []
    for configuration in cve.get("configurations", []):
        for node in configuration.get("nodes", []):
            for match in node.get("cpeMatch", []):
                criteria = match.get("criteria")
                if criteria:
                    products.append(criteria)
    # CPE strings are long and repetitive; cap what is returned.
    return tuple(dict.fromkeys(products))[:20]


def _extract_references(cve: dict[str, Any]) -> tuple[str, ...]:
    return tuple(ref.get("url") for ref in cve.get("references", []) if ref.get("url"))


def _to_record(cve: dict[str, Any]) -> CVERecord:
    score, severity, vector = _extract_metrics(cve)
    return CVERecord(
        cve_id=cve["id"],
        description=_extract_description(cve),
        published_at=_parse_datetime(cve.get("published")),
        modified_at=_parse_datetime(cve.get("lastModified")),
        cvss_score=score,
        severity=severity,
        vector=vector,
        affected_products=_extract_products(cve),
        references=_extract_references(cve),
        source="nvd",
    )


class NvdProvider(BaseCVEProvider):
    name = "nvd"

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        base_url: str = DEFAULT_BASE_URL,
        transport: Optional[httpx.AsyncBaseTransport] = None,
        timeout_seconds: float = REQUEST_TIMEOUT_SECONDS,
        max_attempts: int = MAX_ATTEMPTS,
    ) -> None:
        settings = get_settings()
        self._api_key = api_key if api_key is not None else settings.nist_nvd_api_key
        self._base_url = base_url.rstrip("/")
        self._transport = transport
        self._timeout_seconds = timeout_seconds
        self._max_attempts = max_attempts

    @property
    def is_configured(self) -> bool:
        # The NVD API answers anonymous requests at a lower rate limit, so the
        # provider is usable without a key - unlike Gemini, there is no
        # "not configured" state to report here.
        return True

    async def get(self, cve_id: str) -> CVERecord:
        data = await self._request({"cveId": cve_id})
        vulnerabilities = data.get("vulnerabilities", [])
        if not vulnerabilities:
            raise NotFoundError(f"{cve_id} was not found in the NVD database.")
        return _to_record(vulnerabilities[0]["cve"])

    async def search(self, query: str, *, limit: int) -> Sequence[CVERecord]:
        data = await self._request({"keywordSearch": query, "resultsPerPage": limit})
        return tuple(
            _to_record(item["cve"]) for item in data.get("vulnerabilities", [])
        )

    async def _request(self, params: dict[str, Any]) -> dict[str, Any]:
        try:
            return await self._request_once(params, use_api_key=bool(self._api_key))
        except ProviderAuthenticationError:
            if not self._api_key:
                raise
            # A configured key NVD actively rejects must not take the whole
            # lookup down with it: fall back to the same anonymous (no-key,
            # lower-rate-limit) request every deployment already works
            # without a key. The rejected-key condition itself was already
            # logged by _request_once below - callers/ops can tell
            # BLOCKED_INVALID_KEY apart from a genuine anonymous failure via
            # that log line, even though the client gets real CVE data back.
            logger.warning(
                "nvd_api_key_rejected_falling_back_to_anonymous",
                extra={"fields": {"reason": "BLOCKED_INVALID_KEY"}},
            )
            return await self._request_once(params, use_api_key=False)

    async def _request_once(
        self, params: dict[str, Any], *, use_api_key: bool
    ) -> dict[str, Any]:
        headers = {}
        if use_api_key and self._api_key:
            headers["apiKey"] = self._api_key

        last_error: Exception = ProviderUnavailableError()
        async with httpx.AsyncClient(
            timeout=self._timeout_seconds, transport=self._transport
        ) as client:
            for attempt in range(1, self._max_attempts + 1):
                try:
                    response = await client.get(
                        self._base_url, params=params, headers=headers
                    )
                except httpx.TimeoutException:
                    last_error = ProviderTimeoutError()
                except httpx.HTTPError:
                    last_error = ProviderUnavailableError()
                else:
                    if response.status_code == 429:
                        raise ProviderRateLimitedError(
                            "The NVD API rate-limited this request. Try again shortly."
                        )
                    if response.status_code == 404:
                        # Never NVD's "not found" (that's a 200 with an empty
                        # vulnerabilities array, handled by the caller) -
                        # this status is specific to a rejected apiKey, with
                        # or without a key actually configured.
                        raise ProviderAuthenticationError(
                            "The NVD API rejected the configured API key."
                            if use_api_key and self._api_key
                            else "The NVD API returned an unexpected 404."
                        )
                    if 400 <= response.status_code < 500:
                        raise UpstreamMalformedError(
                            "The NVD API rejected the request."
                        )
                    if response.status_code >= 500:
                        last_error = ProviderUnavailableError()
                    else:
                        try:
                            data = response.json()
                        except ValueError as exc:
                            raise UpstreamMalformedError() from exc
                        if not isinstance(data, dict):
                            raise UpstreamMalformedError()
                        return data

                if attempt < self._max_attempts:
                    await asyncio.sleep(RETRY_BACKOFF_SECONDS * attempt)

        logger.warning(
            "nvd_request_failed",
            extra={"fields": {"attempts": self._max_attempts, "error": type(last_error).__name__}},
        )
        raise last_error
