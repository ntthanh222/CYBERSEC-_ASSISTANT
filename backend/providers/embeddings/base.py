"""Embedding provider contract.

Mirrors :mod:`backend.providers.llm.base`: an implementation reports its
``name`` honestly, exposes the vector width it actually produces, and raises
:mod:`backend.core.exceptions` types on failure rather than letting a driver
or vendor exception escape.
"""
from abc import ABC, abstractmethod
from typing import List, Sequence


class BaseEmbeddingProvider(ABC):
    """Turns text into a fixed-width vector for pgvector similarity search."""

    #: Stable identifier reported in ingestion/retrieval metadata.
    name: str = "base"

    @property
    @abstractmethod
    def is_configured(self) -> bool:
        """Whether this provider has everything it needs to run."""

    @property
    @abstractmethod
    def dimension(self) -> int:
        """The width of every vector this provider returns."""

    @abstractmethod
    async def embed(self, texts: Sequence[str]) -> List[List[float]]:
        """Embed a batch of texts, preserving order."""

    async def embed_one(self, text: str) -> List[float]:
        vectors = await self.embed([text])
        return vectors[0]
