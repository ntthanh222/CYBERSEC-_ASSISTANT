"""CVE provider selection. Production only ever uses NVD."""
from functools import lru_cache

from backend.providers.cve.base import BaseCVEProvider
from backend.providers.cve.nvd import NvdProvider


@lru_cache
def get_cve_provider() -> BaseCVEProvider:
    return NvdProvider()


def reset_cve_provider() -> None:
    get_cve_provider.cache_clear()
