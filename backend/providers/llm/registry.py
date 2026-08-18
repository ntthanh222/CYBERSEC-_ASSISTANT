"""Provider selection.

Exactly one rule: use Gemini when - and only when - an API key is configured;
otherwise use the local knowledge base. There is no third state where the API
reports Gemini without having called it.
"""
from functools import lru_cache

from backend.providers.llm.base import BaseLLMProvider
from backend.providers.llm.gemini import GeminiProvider
from backend.providers.llm.local import LocalKnowledgeProvider


@lru_cache
def get_llm_provider() -> BaseLLMProvider:
    gemini = GeminiProvider()
    if gemini.is_configured:
        return gemini
    return LocalKnowledgeProvider()


def reset_llm_provider() -> None:
    """Drop the cached provider (used when settings change, e.g. in tests)."""
    get_llm_provider.cache_clear()
