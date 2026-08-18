"""CVE provider contract."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Sequence


@dataclass(frozen=True)
class CVERecord:
    cve_id: str
    description: str
    published_at: Optional[datetime]
    modified_at: Optional[datetime]
    cvss_score: Optional[float]
    severity: Optional[str]
    vector: Optional[str]
    affected_products: Sequence[str] = field(default_factory=tuple)
    references: Sequence[str] = field(default_factory=tuple)
    source: str = "unknown"


class BaseCVEProvider(ABC):
    name: str = "base"

    @property
    @abstractmethod
    def is_configured(self) -> bool:
        """Whether this provider can currently answer a lookup."""

    @abstractmethod
    async def get(self, cve_id: str) -> CVERecord:
        """Fetch a single CVE by id, or raise NotFoundError/AppError."""

    @abstractmethod
    async def search(self, query: str, *, limit: int) -> Sequence[CVERecord]:
        """Free-text search, best-effort, capped at ``limit`` results."""
