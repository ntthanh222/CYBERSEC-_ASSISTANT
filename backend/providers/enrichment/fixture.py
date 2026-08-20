"""Fixture enrichment providers - test-only.

Deliberately never wired into :mod:`backend.providers.enrichment.registry`
for production use, same rationale as ``backend.providers.cve.fixture``.
Tests import these classes directly instead of hitting the real FIRST.org/
CISA network.
"""
from typing import Dict, Optional

from backend.providers.enrichment.base import BaseEpssProvider, BaseKevProvider, EpssScore

_EPSS_FIXTURES: Dict[str, EpssScore] = {
    "CVE-2021-44228": EpssScore(cve_id="CVE-2021-44228", score=0.94427, percentile=0.99930),
}

_KEV_FIXTURES = frozenset({"CVE-2021-44228"})


class FixtureEpssProvider(BaseEpssProvider):
    name = "fixture_epss"

    async def get(self, cve_id: str) -> Optional[EpssScore]:
        return _EPSS_FIXTURES.get(cve_id.strip().upper())


class FixtureKevProvider(BaseKevProvider):
    name = "fixture_kev"

    async def is_kev(self, cve_id: str) -> bool:
        return cve_id.strip().upper() in _KEV_FIXTURES

    async def get(self, cve_id: str) -> bool:
        return await self.is_kev(cve_id)
