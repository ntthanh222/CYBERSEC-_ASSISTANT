"""Shared test doubles for knowledge-base tests (not itself a test module)."""
from backend.core.exceptions import ProviderUnavailableError
from backend.providers.embeddings.base import BaseEmbeddingProvider


class FakeEmbeddingProvider(BaseEmbeddingProvider):
    """Deterministic, instant, no-network stand-in for the real local model."""

    name = "fake"

    def __init__(self, dimension: int = 8, *, fail: bool = False) -> None:
        self._dimension = dimension
        self._fail = fail

    @property
    def is_configured(self) -> bool:
        return True

    @property
    def dimension(self) -> int:
        return self._dimension

    async def embed(self, texts):
        if self._fail:
            raise ProviderUnavailableError("fake embedding failure")
        return [[float((hash(text) % 97) + i) for i in range(self._dimension)] for text in texts]
