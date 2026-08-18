"""RAG retriever contract and the null implementation used before Phase 2.6.

``retrieve`` takes ``user_id`` explicitly (not just an ambient session) so
every implementation is forced to scope its query to that caller - the same
"never trust the session alone" rule
:mod:`backend.repositories.conversation` documents for ownership checks.
"""
import uuid
from dataclasses import dataclass
from typing import Optional, Protocol, Sequence, runtime_checkable


@dataclass(frozen=True)
class RagDocument:
    """A retrieved chunk plus enough provenance to cite it honestly."""

    id: str
    title: str
    content: str
    score: float
    source: str
    document_id: Optional[str] = None
    page: Optional[int] = None
    heading: Optional[str] = None
    chunk_index: Optional[int] = None


@runtime_checkable
class RagRetriever(Protocol):
    """Anything that can supply grounding documents for a question."""

    @property
    def is_ready(self) -> bool:
        """Whether the retriever has an index it can actually search."""
        ...

    async def retrieve(
        self, query: str, *, user_id: uuid.UUID, limit: int = 4
    ) -> Sequence[RagDocument]:
        """Return the most relevant documents ``user_id`` is allowed to see."""
        ...


class NullRagRetriever:
    """No index, no documents, and it says so.

    ``is_ready`` is ``False`` and ``retrieve`` returns an empty sequence. An
    empty or not-yet-configured knowledge base reports zero documents rather
    than claiming readiness - it is honest behaviour, not a placeholder that
    pretends to work.
    """

    @property
    def is_ready(self) -> bool:
        return False

    async def retrieve(
        self, query: str, *, user_id: uuid.UUID, limit: int = 4
    ) -> Sequence[RagDocument]:
        return ()


def get_rag_retriever() -> RagRetriever:
    """Session-less fallback used only where no request-scoped session exists.

    Real retrieval requires a session bound as the ``authenticated`` Postgres
    role (Row Level Security scopes what it can see) - see
    :func:`backend.services.rag_retrieval.get_rag_retriever_for_session`,
    which every request path actually uses.
    """
    return NullRagRetriever()
