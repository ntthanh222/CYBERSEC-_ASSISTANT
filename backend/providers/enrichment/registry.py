"""Enrichment provider selection (Task 6). Mirrors
``backend.providers.cve.registry``'s exact ``@lru_cache`` pattern."""
from functools import lru_cache

from backend.providers.enrichment.base import BaseEpssProvider, BaseKevProvider
from backend.providers.enrichment.epss import EpssProvider
from backend.providers.enrichment.kev import KevProvider


@lru_cache
def get_epss_provider() -> BaseEpssProvider:
    return EpssProvider()


@lru_cache
def get_kev_provider() -> BaseKevProvider:
    return KevProvider()


def reset_enrichment_providers() -> None:
    get_epss_provider.cache_clear()
    get_kev_provider.cache_clear()
