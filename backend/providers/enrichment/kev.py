"""CISA Known Exploited Vulnerabilities (KEV) catalog provider (Task 6).

Downloads CISA's public KEV JSON feed:
``https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json``.
This is a public, keyless static JSON file - no registration, no API key, no
authentication of any kind (verified against CISA's own published KEV page,
which documents this exact URL as the machine-readable feed). If that URL
ever moves, ``kev_feed_url`` is the extension point.

Response shape (per CISA's documented KEV JSON schema)::

    {
        "title": "...",
        "catalogVersion": "...",
        "dateReleased": "...",
        "count": 1234,
        "vulnerabilities": [
            {"cveID": "CVE-2021-44228", "dateAdded": "2021-12-10", ...},
            ...
        ]
    }

**Whole-catalog caching, not per-CVE**: unlike EPSS (a per-CVE API call),
KEV publishes one JSON file covering every known-exploited CVE. Downloading
it fresh for every single CVE assessed would be wasteful and would hammer
CISA's server for no benefit - the catalog changes at most a few times a
week. So this provider downloads and Redis-caches the WHOLE catalog (as a
set of CVE ids) under one fixed key (``kev:v1``), with a TTL measured in
hours (``settings.kev_cache_ttl_seconds``, default 6h) rather than the ~1h
TTL used for per-CVE CVSS/EPSS data - see ``backend/config/settings.py``'s
field docstring for the full reasoning. ``is_kev(cve_id)`` then answers by
set membership against the cached (or freshly fetched) catalog, never by a
per-CVE network call.

**Fail-open by design, with a documented tradeoff**: if the catalog cannot
be fetched or parsed (network error, timeout, malformed JSON, non-200), this
returns ``is_kev=False`` for every CVE rather than raising and failing the
whole assessment. This is a deliberate tradeoff: "absence of proof isn't
proof of absence" (a CVE could genuinely be KEV-listed and we just can't
confirm it right now), but failing an entire CVE risk assessment because
CISA's feed is temporarily unreachable would be strictly worse for the
user than proceeding with "not confirmed KEV" - the assessment still runs
on its CVSS/EPSS signals, it just cannot escalate on KEV status until the
feed is reachable again. This mirrors the same fail-open posture
``EpssProvider`` and ``CveLookupService`` already use for their own
failure modes.

**A failed fetch is never cached.** ``_fetch_catalog`` distinguishes "the
feed was fetched and parsed, and legitimately contains zero entries" from
"the fetch/parse itself failed" by returning ``None`` for the latter (an
empty ``frozenset()`` is a real, cacheable answer; ``None`` never is).
``_catalog`` only calls ``_cache_set`` for a non-``None`` result. Caching a
failure would silently upgrade one transient CISA outage into "confirmed
NOT KEV for every CVE, for the full multi-hour TTL" - fail-open must apply
per request, not get baked into the cache as if it were real catalog data
that would otherwise take hours to self-correct even after CISA recovers.
This mirrors ``EpssProvider``'s "a miss is never cached" behaviour for the
exact same reason.
"""
import logging
from typing import Final, FrozenSet, Optional

import httpx

from backend.config.settings import get_settings
from backend.core.redis_client import get_redis
from backend.providers.enrichment.base import BaseKevProvider

logger = logging.getLogger("backend.providers.kev")

REQUEST_TIMEOUT_SECONDS: Final = 15.0
CACHE_KEY: Final = "kev:v1"


class KevProvider(BaseKevProvider):
    name = "kev"

    def __init__(
        self,
        *,
        feed_url: Optional[str] = None,
        transport: Optional[httpx.AsyncBaseTransport] = None,
        timeout_seconds: float = REQUEST_TIMEOUT_SECONDS,
    ) -> None:
        settings = get_settings()
        self._feed_url = feed_url or settings.kev_feed_url
        self._transport = transport
        self._timeout_seconds = timeout_seconds
        self._cache_ttl_seconds = settings.kev_cache_ttl_seconds

    async def _cache_get(self) -> Optional[FrozenSet[str]]:
        client = get_redis()
        if client is None:
            return None
        try:
            raw = await client.get(CACHE_KEY)
        except Exception as exc:  # noqa: BLE001 - cache is best-effort
            logger.warning(
                "kev_cache_read_failed",
                extra={"fields": {"exception_type": type(exc).__name__}},
            )
            return None
        if raw is None:
            return None
        return frozenset(raw.split(",")) if raw else frozenset()

    async def _cache_set(self, cve_ids: FrozenSet[str]) -> None:
        client = get_redis()
        if client is None:
            return
        try:
            await client.set(CACHE_KEY, ",".join(sorted(cve_ids)), ex=self._cache_ttl_seconds)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "kev_cache_write_failed",
                extra={"fields": {"exception_type": type(exc).__name__}},
            )

    async def _catalog(self) -> FrozenSet[str]:
        cached = await self._cache_get()
        if cached is not None:
            return cached

        catalog = await self._fetch_catalog()
        if catalog is None:
            # Fetch/parse failed - fail open for THIS call only (empty
            # catalog -> is_kev=False) without writing anything to the
            # cache, so the very next call retries the network instead of
            # serving a poisoned "confirmed empty" result for the full TTL.
            return frozenset()

        await self._cache_set(catalog)
        return catalog

    async def _fetch_catalog(self) -> Optional[FrozenSet[str]]:
        """Returns the parsed catalog, or ``None`` if the fetch/parse
        itself failed - never conflated with a legitimately empty catalog,
        which is a real ``frozenset()`` result. See ``_catalog``'s handling
        of this distinction and the module docstring."""
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout_seconds, transport=self._transport
            ) as client:
                response = await client.get(self._feed_url)
        except httpx.HTTPError as exc:
            logger.warning(
                "kev_catalog_fetch_failed",
                extra={"fields": {"exception_type": type(exc).__name__}},
            )
            return None

        if response.status_code != 200:
            logger.warning(
                "kev_catalog_fetch_non_200",
                extra={"fields": {"status_code": response.status_code}},
            )
            return None

        try:
            payload = response.json()
        except ValueError:
            logger.warning("kev_catalog_malformed")
            return None

        if not isinstance(payload, dict):
            return None
        entries = payload.get("vulnerabilities")
        if not isinstance(entries, list):
            return None

        return frozenset(
            entry["cveID"].strip().upper()
            for entry in entries
            if isinstance(entry, dict) and entry.get("cveID")
        )

    async def is_kev(self, cve_id: str) -> bool:
        catalog = await self._catalog()
        return cve_id.strip().upper() in catalog

    async def get(self, cve_id: str) -> bool:
        """Alias for :meth:`is_kev` - see ``BaseKevProvider`` for why both
        methods exist."""
        return await self.is_kev(cve_id)
