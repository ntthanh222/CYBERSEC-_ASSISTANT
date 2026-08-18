"""pgvector-backed RAG retrieval - the real :class:`RagRetriever` for Phase 2.6.

Selected automatically whenever the current session is bound to PostgreSQL,
where pgvector and migration 0005's Row Level Security policies exist;
:class:`~backend.providers.rag.base.NullRagRetriever` is used on SQLite,
which the unit-test suite runs on and which has neither. See
:func:`get_rag_retriever_for_session`, which every request path uses.

Hybrid pipeline (FINAL_MASTER_PROMPT_CYBERSEC_ASSISTANT.md section F)::

    vector search ─┐
    full-text search ├─▶ merge + normalize ─▶ local rerank ─▶ MMR ─▶ top `limit`
    exact-match search ┘

A wider candidate pool (``rag_candidate_pool_size``, default 20) than what's
ever sent to the LLM is fetched on purpose - rerank/MMR need real
alternatives to choose among, not just the top few by one signal.
"""
import logging
import uuid
from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from backend.config.settings import get_settings
from backend.core.exceptions import AppError
from backend.core.rag_cache import get_cached_retrieval, set_cached_retrieval
from backend.providers.embeddings.base import BaseEmbeddingProvider
from backend.providers.embeddings.registry import get_embedding_provider
from backend.providers.rag.base import NullRagRetriever, RagDocument, RagRetriever
from backend.repositories.knowledge import KnowledgeRepository
from backend.services.rag_hybrid import extract_exact_match_terms, mmr_select, rerank_candidates

logger = logging.getLogger("backend.services.rag_retrieval")

#: Two chunks whose first N characters match (after casefolding) are treated
#: as near-duplicates and collapsed to the first, highest-scoring occurrence.
_DEDUPE_PREFIX_CHARS = 200


class PgVectorRagRetriever:
    """Hybrid (vector + full-text + exact-match) retrieval, reranked and
    MMR-diversified, with a version-invalidated Redis cache in front."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        embedding_provider: Optional[BaseEmbeddingProvider] = None,
    ) -> None:
        self._session = session
        self._repo = KnowledgeRepository(session)
        self._embeddings = embedding_provider or get_embedding_provider()
        settings = get_settings()
        self._similarity_threshold = settings.rag_similarity_threshold
        self._max_context_chars = settings.rag_max_context_chars
        self._candidate_pool_size = settings.rag_candidate_pool_size
        self._mmr_lambda = settings.rag_mmr_lambda

    @property
    def is_ready(self) -> bool:
        return True

    async def retrieve(
        self, query: str, *, user_id: uuid.UUID, limit: int = 4
    ) -> Sequence[RagDocument]:
        clean_query = (query or "").strip()
        if not clean_query:
            return ()

        cached = await get_cached_retrieval(user_id=user_id, query=clean_query)
        if cached is not None:
            return tuple(RagDocument(**item) for item in cached[:limit])

        candidates = await self._gather_candidates(clean_query, user_id=user_id)
        if not candidates:
            return ()

        reranked = rerank_candidates(candidates, query=clean_query)
        # MMR selects exactly `limit` (not the whole pool): its greedy order
        # is stable prefix-wise, so selecting k=limit directly is the same
        # top-limit result as selecting the full pool and truncating, for
        # less wasted work.
        diversified = mmr_select(reranked, k=limit, lambda_param=self._mmr_lambda)

        results: List[RagDocument] = []
        budget = self._max_context_chars
        for candidate in diversified:
            if len(results) >= limit or budget <= 0:
                break
            results.append(
                RagDocument(
                    id=candidate["id"],
                    title=candidate["title"],
                    content=candidate["content"],
                    score=round(float(candidate["rerank_score"]), 4),
                    source=candidate["source"],
                    document_id=candidate["document_id"],
                    page=candidate.get("page"),
                    heading=candidate.get("heading"),
                    chunk_index=candidate["chunk_index"],
                )
            )
            budget -= len(candidate["content"])

        await set_cached_retrieval(
            user_id=user_id, query=clean_query, results=[r.__dict__ for r in results]
        )
        return results

    async def _gather_candidates(
        self, query: str, *, user_id: uuid.UUID
    ) -> List[Dict[str, Any]]:
        pool = self._candidate_pool_size

        try:
            query_vector = await self._embeddings.embed_one(query)
        except AppError:
            # Retrieval must degrade to "no context found" - a broken
            # embedding provider must never break the chat turn itself. Full-
            # text and exact-match below don't need an embedding, so they
            # still run - a total outage of one signal is not a total outage
            # of retrieval.
            logger.warning("rag_query_embedding_failed")
            query_vector = None

        max_distance = 1.0 - self._similarity_threshold
        vector_rows = (
            await self._repo.search_chunks(
                user_id=user_id, query_embedding=query_vector, limit=pool, max_distance=max_distance
            )
            if query_vector is not None
            else []
        )
        fulltext_rows = await self._repo.search_chunks_fulltext(
            user_id=user_id, query_text=query, limit=pool
        )
        exact_terms = extract_exact_match_terms(query)
        exact_rows = await self._repo.search_chunks_exact(
            user_id=user_id, terms=exact_terms, limit=pool
        )

        merged: Dict[str, Dict[str, Any]] = {}
        seen_prefixes: set = set()

        def _add(chunk, score: float) -> None:
            key = str(chunk.id)
            existing = merged.get(key)
            if existing is not None:
                existing["relevance"] = max(existing["relevance"], score)
                return
            prefix = chunk.content[:_DEDUPE_PREFIX_CHARS].strip().casefold()
            if prefix in seen_prefixes:
                return
            seen_prefixes.add(prefix)
            document = chunk.document
            meta = chunk.meta or {}
            merged[key] = {
                "id": key,
                "title": document.title,
                "content": chunk.content,
                "source": document.source_name,
                "document_id": str(document.id),
                "page": meta.get("page"),
                "heading": meta.get("heading"),
                "chunk_index": chunk.chunk_index,
                "relevance": score,
            }

        for chunk, distance in vector_rows:
            _add(chunk, max(0.0, min(1.0, 1.0 - distance)))
        if fulltext_rows:
            max_rank = max(rank for _, rank in fulltext_rows) or 1.0
            for chunk, rank in fulltext_rows:
                _add(chunk, rank / max_rank)
        for chunk, score in exact_rows:
            # Exact match always wins - a literal CVE/IOC/technique-ID hit is
            # never outranked by a merely-similar vector/text score.
            _add(chunk, score)

        return list(merged.values())


def get_rag_retriever_for_session(session: AsyncSession) -> RagRetriever:
    """The real retriever on Postgres, the honest null one everywhere else."""
    bind = session.get_bind()
    dialect_name = getattr(getattr(bind, "dialect", None), "name", None)
    if dialect_name != "postgresql":
        return NullRagRetriever()
    return PgVectorRagRetriever(session)
