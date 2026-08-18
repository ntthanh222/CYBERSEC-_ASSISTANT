"""Fixture CVE provider - test-only.

Deliberately never wired into :func:`backend.providers.cve.registry` for
production use: the blueprint forbids returning fabricated data disguised as
real data. Tests import this class directly.
"""
from datetime import datetime, timezone
from typing import Sequence

from backend.core.exceptions import NotFoundError
from backend.providers.cve.base import BaseCVEProvider, CVERecord

_FIXTURES: dict[str, CVERecord] = {
    "CVE-2021-44228": CVERecord(
        cve_id="CVE-2021-44228",
        description="Apache Log4j2 JNDI features do not protect against attacker "
        "controlled LDAP and other JNDI related endpoints, enabling remote code "
        "execution.",
        published_at=datetime(2021, 12, 10, tzinfo=timezone.utc),
        modified_at=datetime(2023, 11, 7, tzinfo=timezone.utc),
        cvss_score=10.0,
        severity="critical",
        vector="CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:C/C:H/I:H/A:H",
        affected_products=("cpe:2.3:a:apache:log4j:2.14.1:*:*:*:*:*:*:*",),
        references=("https://nvd.nist.gov/vuln/detail/CVE-2021-44228",),
        source="nvd",
    ),
}


class FixtureCVEProvider(BaseCVEProvider):
    name = "fixture"

    @property
    def is_configured(self) -> bool:
        return True

    async def get(self, cve_id: str) -> CVERecord:
        try:
            return _FIXTURES[cve_id.upper()]
        except KeyError:
            raise NotFoundError(f"{cve_id} was not found.") from None

    async def search(self, query: str, *, limit: int) -> Sequence[CVERecord]:
        lowered = query.lower()
        matches = [
            record
            for record in _FIXTURES.values()
            if lowered in record.cve_id.lower() or lowered in record.description.lower()
        ]
        return tuple(matches[:limit])
