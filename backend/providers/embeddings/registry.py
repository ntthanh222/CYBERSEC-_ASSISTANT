"""Embedding provider selection.

Deliberately the reverse of :mod:`backend.providers.llm.registry`'s rule.
The LLM registry prefers an external provider whenever one is configured;
here the **local** provider is the default and always wins unless an
operator explicitly opts in with ``EMBEDDING_PROVIDER=gemini`` *and*
configures ``GEMINI_API_KEY``. Embeddings run over every document a user
uploads, so silently upgrading to a cloud provider just because a key
happens to be present would violate the requirement that private documents
never leave the process by default.
"""
from functools import lru_cache

from backend.config.settings import get_settings
from backend.providers.embeddings.base import BaseEmbeddingProvider
from backend.providers.embeddings.gemini import GeminiEmbeddingProvider
from backend.providers.embeddings.local import LocalEmbeddingProvider


@lru_cache
def get_embedding_provider() -> BaseEmbeddingProvider:
    settings = get_settings()
    if settings.embedding_cloud_configured:
        return GeminiEmbeddingProvider()
    return LocalEmbeddingProvider()


def reset_embedding_provider() -> None:
    """Drop the cached provider (used when settings change, e.g. in tests)."""
    get_embedding_provider.cache_clear()
