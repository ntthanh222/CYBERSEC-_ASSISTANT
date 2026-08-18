"""CVE lookup: validation, provider dispatch and Redis caching.

Cache-aside pattern: check Redis, on miss call the provider and populate the
cache, on any Redis error skip the cache entirely rather than fail the
request - the same "fail open" posture as the rate limiter, because a cache
outage must degrade performance, not correctness.
"""
import json
import logging
import re
from dataclasses import asdict
from datetime import datetime
from typing import Any, Final, Optional, Sequence

from backend.config.settings import get_settings
from backend.core.audit import log_audit_event
from backend.core.exceptions import InvalidRequestError
from backend.core.metrics import observe_cve_cache, observe_cve_lookup
from backend.core.redis_client import get_redis
from backend.core.timeutils import utcnow
from backend.providers.cve.base import BaseCVEProvider, CVERecord
from backend.providers.cve.registry import get_cve_provider

logger = logging.getLogger("backend.cve")

CVE_ID_PATTERN: Final = re.compile(r"^CVE-\d{4}-\d{4,}$", re.IGNORECASE)
CACHE_KEY_PREFIX: Final = "cve:v1:"
SEARCH_MAX_LIMIT: Final = 50


def validate_cve_id(cve_id: str) -> str:
    candidate = (cve_id or "").strip().upper()
    if not CVE_ID_PATTERN.match(candidate):
        raise InvalidRequestError(
            "Định dạng CVE id không hợp lệ. Cần theo mẫu CVE-YYYY-NNNN (ví dụ: CVE-2021-44228)."
        )
    return candidate


def _serialize(record: CVERecord) -> dict[str, Any]:
    data = asdict(record)
    data["published_at"] = record.published_at.isoformat() if record.published_at else None
    data["modified_at"] = record.modified_at.isoformat() if record.modified_at else None
    return data


def _deserialize(data: dict[str, Any]) -> CVERecord:
    def _parse(value: Optional[str]) -> Optional[datetime]:
        return datetime.fromisoformat(value) if value else None

    return CVERecord(
        cve_id=data["cve_id"],
        description=data["description"],
        published_at=_parse(data.get("published_at")),
        modified_at=_parse(data.get("modified_at")),
        cvss_score=data.get("cvss_score"),
        severity=data.get("severity"),
        vector=data.get("vector"),
        affected_products=tuple(data.get("affected_products", ())),
        references=tuple(data.get("references", ())),
        source=data.get("source", "unknown"),
    )


class CveLookupService:
    def __init__(self, *, provider: Optional[BaseCVEProvider] = None) -> None:
        self._provider = provider or get_cve_provider()
        self._settings = get_settings()

    async def _cache_get(self, cve_id: str) -> Optional[dict[str, Any]]:
        client = get_redis()
        if client is None:
            return None
        try:
            raw = await client.get(f"{CACHE_KEY_PREFIX}{cve_id}")
        except Exception as exc:  # noqa: BLE001 - cache is best-effort
            logger.warning(
                "cve_cache_read_failed",
                extra={"fields": {"exception_type": type(exc).__name__}},
            )
            return None
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (TypeError, ValueError):
            return None

    async def _cache_set(self, cve_id: str, record: CVERecord) -> None:
        client = get_redis()
        if client is None:
            return
        try:
            await client.set(
                f"{CACHE_KEY_PREFIX}{cve_id}",
                json.dumps(_serialize(record)),
                ex=self._settings.cve_cache_ttl_seconds,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "cve_cache_write_failed",
                extra={"fields": {"exception_type": type(exc).__name__}},
            )

    async def get(self, raw_cve_id: str, *, actor: Optional[str]) -> dict[str, Any]:
        cve_id = validate_cve_id(raw_cve_id)

        cached = await self._cache_get(cve_id)
        if cached is not None:
            observe_cve_cache("hit")
            observe_cve_lookup("success")
            self._audit(cve_id, actor, cached=True)
            return {**cached, "cached": True, "fetched_at": utcnow()}

        observe_cve_cache("miss")
        try:
            record = await self._provider.get(cve_id)
        except Exception:
            observe_cve_lookup("failure")
            raise

        await self._cache_set(cve_id, record)
        observe_cve_lookup("success")
        self._audit(cve_id, actor, cached=False)
        return {**_serialize(record), "cached": False, "fetched_at": utcnow()}

    async def search(self, query: str, *, limit: int) -> Sequence[dict[str, Any]]:
        clean_query = (query or "").strip()
        if not clean_query:
            raise InvalidRequestError("Cần nhập từ khóa tìm kiếm.")
        bounded_limit = min(max(limit, 1), SEARCH_MAX_LIMIT)
        try:
            records = await self._provider.search(clean_query, limit=bounded_limit)
        except Exception:
            observe_cve_lookup("failure")
            raise
        observe_cve_lookup("success")
        fetched_at = utcnow()
        return [
            {**_serialize(record), "cached": False, "fetched_at": fetched_at}
            for record in records
        ]

    @staticmethod
    def _audit(cve_id: str, actor: Optional[str], *, cached: bool) -> None:
        log_audit_event(
            event_type="cve_lookup",
            action="lookup_performed",
            resource=f"cve:{cve_id}",
            result="success",
            actor=actor,
            metadata={"cached": cached},
        )
