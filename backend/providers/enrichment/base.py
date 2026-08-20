"""Enrichment provider contracts (Task 6).

Mirrors ``backend.providers.cve.base``'s shape (an ABC per provider family,
a small frozen result dataclass), but EPSS and KEV are two genuinely
different lookups - a per-CVE score/percentile vs. a whole-catalog
membership check - so this module keeps them as two small, provider-specific
ABCs rather than forcing one shared interface neither would fit well.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class EpssScore:
    cve_id: str
    score: float
    percentile: float


class BaseEnrichmentProvider(ABC):
    """Common marker/interface for enrichment providers, per the brief."""

    name: str = "base"

    @abstractmethod
    async def get(self, cve_id: str):
        """Fetch enrichment data for a single CVE."""


class BaseEpssProvider(BaseEnrichmentProvider):
    name = "epss_base"

    @abstractmethod
    async def get(self, cve_id: str) -> Optional[EpssScore]:
        """Fetch EPSS score+percentile for a CVE, or ``None`` if the CVE has
        no EPSS data (normal - EPSS only scores CVEs it has a model for) or
        the lookup failed (fail-open, never raises)."""


class BaseKevProvider(BaseEnrichmentProvider):
    name = "kev_base"

    @abstractmethod
    async def get(self, cve_id: str) -> bool:
        """Alias for ``is_kev`` - present so both provider families share
        the ``get(cve_id)`` shape named in the brief."""

    @abstractmethod
    async def is_kev(self, cve_id: str) -> bool:
        """Whether ``cve_id`` is in the CISA KEV catalog. Fails open to
        ``False`` (not confirmed KEV) if the catalog cannot be fetched -
        never raises."""
