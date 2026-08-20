"""FIRST.org EPSS (Exploit Prediction Scoring System) provider (Task 6).

Talks to the public EPSS API: ``GET https://api.first.org/data/v1/epss?cve={cve_id}``.
This is a keyless, public API - FIRST.org does not require registration or
an API key for the EPSS endpoint (verified against FIRST.org's own published
API documentation at the time this provider was written). If that ever
changes, ``epss_base_url``/headers are the extension point, same as
``NvdProvider``'s optional-key handling - no such field exists here today
because none is needed.

Response shape (per FIRST.org's documented format)::

    {
        "status": "OK",
        "data": [
            {"cve": "CVE-2021-44228", "epss": "0.94427", "percentile": "0.99930", "date": "..."}
        ]
    }

``epss``/``percentile`` are STRING-encoded floats - parsed defensively here
rather than trusting the JSON type. A CVE with no EPSS data (not every CVE
has one - EPSS only scores CVEs its model covers) comes back with an empty
``data`` array; that is normal, not an error, and maps to ``None``.

**Caching**: unlike ``NvdProvider`` (which is a bare fetch, with
``CveLookupService`` owning the Redis cache-aside layer separately), this
provider owns its own Redis cache-aside layer directly - there is no
separate "EpssLookupService" in this task, so the cache-aside pattern
(cache key ``epss:v1:{cve_id}``, TTL ``settings.epss_cache_ttl_seconds``,
fail-open on any Redis error - same posture as
``backend.services.cve.CveLookupService``) lives here instead.

**Fail-open by design**: every failure mode (network error, timeout,
malformed response, empty data, Redis error) returns ``None`` rather than
raising. A missing/failing EPSS lookup must never block a CVE risk
assessment - ``cve_priority.assess`` already treats ``epss_score=None`` as
"unknown, weight CVSS more" rather than "safe". This is a deliberate,
narrower contract than ``BaseCVEProvider`` (which does raise on failure) -
EPSS is enrichment, not the primary record, so degrading gracefully matters
more here than surfacing the failure to the caller. A "no EPSS data for
this CVE" result (``None``) is deliberately NOT cached: caching a hard miss
would risk permanently hiding EPSS data that gets published for this CVE
later within the TTL window, and misses are cheap to re-fetch.
"""
import json
import logging
from typing import Any, Final, Optional

import httpx

from backend.config.settings import get_settings
from backend.core.redis_client import get_redis
from backend.providers.enrichment.base import BaseEpssProvider, EpssScore

logger = logging.getLogger("backend.providers.epss")

REQUEST_TIMEOUT_SECONDS: Final = 10.0
CACHE_KEY_PREFIX: Final = "epss:v1:"


def _parse_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class EpssProvider(BaseEpssProvider):
    name = "epss"

    def __init__(
        self,
        *,
        base_url: Optional[str] = None,
        transport: Optional[httpx.AsyncBaseTransport] = None,
        timeout_seconds: float = REQUEST_TIMEOUT_SECONDS,
    ) -> None:
        settings = get_settings()
        self._base_url = (base_url or settings.epss_base_url).rstrip("/")
        self._transport = transport
        self._timeout_seconds = timeout_seconds
        self._cache_ttl_seconds = settings.epss_cache_ttl_seconds

    async def _cache_get(self, cve_id: str) -> Optional[EpssScore]:
        client = get_redis()
        if client is None:
            return None
        try:
            raw = await client.get(f"{CACHE_KEY_PREFIX}{cve_id}")
        except Exception as exc:  # noqa: BLE001 - cache is best-effort
            logger.warning(
                "epss_cache_read_failed",
                extra={"fields": {"exception_type": type(exc).__name__}},
            )
            return None
        if raw is None:
            return None
        try:
            data = json.loads(raw)
            return EpssScore(cve_id=data["cve_id"], score=data["score"], percentile=data["percentile"])
        except (TypeError, ValueError, KeyError):
            return None

    async def _cache_set(self, cve_id: str, result: EpssScore) -> None:
        client = get_redis()
        if client is None:
            return
        try:
            await client.set(
                f"{CACHE_KEY_PREFIX}{cve_id}",
                json.dumps(
                    {"cve_id": result.cve_id, "score": result.score, "percentile": result.percentile}
                ),
                ex=self._cache_ttl_seconds,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "epss_cache_write_failed",
                extra={"fields": {"exception_type": type(exc).__name__}},
            )

    async def get(self, cve_id: str) -> Optional[EpssScore]:
        cve_id = cve_id.strip().upper()

        cached = await self._cache_get(cve_id)
        if cached is not None:
            return cached

        result = await self._fetch(cve_id)
        if result is not None:
            await self._cache_set(cve_id, result)
        return result

    async def _fetch(self, cve_id: str) -> Optional[EpssScore]:
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout_seconds, transport=self._transport
            ) as client:
                response = await client.get(self._base_url, params={"cve": cve_id})
        except httpx.HTTPError as exc:
            logger.warning(
                "epss_request_failed",
                extra={"fields": {"cve_id": cve_id, "exception_type": type(exc).__name__}},
            )
            return None

        if response.status_code != 200:
            logger.warning(
                "epss_request_non_200",
                extra={"fields": {"cve_id": cve_id, "status_code": response.status_code}},
            )
            return None

        try:
            payload = response.json()
        except ValueError:
            logger.warning("epss_response_malformed", extra={"fields": {"cve_id": cve_id}})
            return None

        if not isinstance(payload, dict):
            return None
        entries = payload.get("data")
        if not entries or not isinstance(entries, list):
            return None

        entry = entries[0]
        score = _parse_float(entry.get("epss"))
        percentile = _parse_float(entry.get("percentile"))
        if score is None or percentile is None:
            return None

        return EpssScore(cve_id=cve_id, score=score, percentile=percentile)
