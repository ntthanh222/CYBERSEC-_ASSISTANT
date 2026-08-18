"""Knowledge document/chunk persistence.

Every method that can touch another user's row filters explicitly on
ownership - the service-layer check that Row Level Security (migration 0005)
backs up, not a substitute for it. Mirrors
:mod:`backend.repositories.conversation`'s "defense in depth" rule: a global
document (``owner_user_id IS NULL``) is visible to every caller, a private
one only to its owner.
"""
import uuid
from typing import Any, Optional, Sequence, Tuple

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.database.models.knowledge import KnowledgeChunk, KnowledgeDocument


def _visible_to(user_id: uuid.UUID) -> sa.ColumnElement[bool]:
    return sa.or_(
        KnowledgeDocument.owner_user_id.is_(None),
        KnowledgeDocument.owner_user_id == user_id,
    )


class KnowledgeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_document(
        self,
        *,
        owner_user_id: uuid.UUID,
        title: str,
        source_type: str,
        source_name: str,
        mime_type: str,
        checksum: str,
    ) -> KnowledgeDocument:
        document = KnowledgeDocument(
            owner_user_id=owner_user_id,
            title=title,
            source_type=source_type,
            source_name=source_name,
            mime_type=mime_type,
            checksum=checksum,
            processing_status="processing",
        )
        self._session.add(document)
        await self._session.flush()
        return document

    async def get_by_checksum(
        self, *, owner_user_id: Optional[uuid.UUID], checksum: str
    ) -> Optional[KnowledgeDocument]:
        owner_condition = (
            KnowledgeDocument.owner_user_id.is_(None)
            if owner_user_id is None
            else KnowledgeDocument.owner_user_id == owner_user_id
        )
        return await self._session.scalar(
            sa.select(KnowledgeDocument).where(
                owner_condition,
                KnowledgeDocument.checksum == checksum,
            )
        )

    async def get(
        self, document_id: uuid.UUID, *, user_id: uuid.UUID
    ) -> Optional[KnowledgeDocument]:
        """A document ``user_id`` may *read* - their own, or a global one."""
        return await self._session.scalar(
            sa.select(KnowledgeDocument).where(
                KnowledgeDocument.id == document_id, _visible_to(user_id)
            )
        )

    async def get_owned(
        self, document_id: uuid.UUID, *, user_id: uuid.UUID
    ) -> Optional[KnowledgeDocument]:
        """A document ``user_id`` may *modify* - their own private uploads only."""
        return await self._session.scalar(
            sa.select(KnowledgeDocument).where(
                KnowledgeDocument.id == document_id,
                KnowledgeDocument.owner_user_id == user_id,
            )
        )

    async def get_owned_with_chunks(
        self, document_id: uuid.UUID, *, user_id: uuid.UUID
    ) -> Optional[KnowledgeDocument]:
        return await self._session.scalar(
            sa.select(KnowledgeDocument)
            .where(
                KnowledgeDocument.id == document_id,
                KnowledgeDocument.owner_user_id == user_id,
            )
            .options(selectinload(KnowledgeDocument.chunks))
        )

    async def list_documents(
        self, *, user_id: uuid.UUID, page: int, page_size: int
    ) -> Tuple[Sequence[KnowledgeDocument], int]:
        filters = [_visible_to(user_id)]
        total = await self._session.scalar(
            sa.select(sa.func.count()).select_from(KnowledgeDocument).where(*filters)
        )
        rows = await self._session.scalars(
            sa.select(KnowledgeDocument)
            .where(*filters)
            .order_by(KnowledgeDocument.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(rows), int(total or 0)

    async def delete(self, document: KnowledgeDocument) -> None:
        # Chunks go with it: FK is ON DELETE CASCADE, relationship is
        # delete-orphan, so no orphaned chunk can survive.
        await self._session.delete(document)

    async def replace_chunks(
        self, document: KnowledgeDocument, chunks: Sequence[KnowledgeChunk]
    ) -> None:
        await self._session.execute(
            sa.delete(KnowledgeChunk).where(KnowledgeChunk.document_id == document.id)
        )
        for chunk in chunks:
            self._session.add(chunk)
        await self._session.flush()

    async def mark_ready(
        self, document: KnowledgeDocument, *, page_count: Optional[int], chunk_count: int
    ) -> None:
        document.processing_status = "ready"
        document.error_message = None
        document.page_count = page_count
        document.chunk_count = chunk_count
        await self._session.flush()

    async def mark_failed(self, document: KnowledgeDocument, *, error_message: str) -> None:
        document.processing_status = "failed"
        document.error_message = error_message[:500]
        await self._session.flush()

    async def search_chunks(
        self,
        *,
        user_id: uuid.UUID,
        query_embedding: Sequence[float],
        limit: int,
        max_distance: float,
    ) -> Sequence[Tuple[KnowledgeChunk, float]]:
        """Nearest chunks by cosine distance, scoped to what ``user_id`` may read.

        Postgres/pgvector only - the caller (:mod:`backend.services.
        rag_retrieval`) never routes here on a non-PostgreSQL session.
        """
        distance = KnowledgeChunk.embedding.cosine_distance(list(query_embedding))
        stmt = (
            sa.select(KnowledgeChunk, distance.label("distance"))
            .join(KnowledgeDocument, KnowledgeDocument.id == KnowledgeChunk.document_id)
            .where(
                _visible_to(user_id),
                KnowledgeDocument.processing_status == "ready",
                distance <= max_distance,
            )
            .order_by(distance.asc())
            .limit(limit)
            .options(selectinload(KnowledgeChunk.document))
        )
        rows = await self._session.execute(stmt)
        return [(row[0], float(row[1])) for row in rows.all()]

    async def _hydrate(
        self, id_to_score: dict[str, float]
    ) -> Sequence[Tuple[KnowledgeChunk, float]]:
        if not id_to_score:
            return []
        chunks = await self._session.scalars(
            sa.select(KnowledgeChunk)
            .where(KnowledgeChunk.id.in_(id_to_score.keys()))
            .options(selectinload(KnowledgeChunk.document))
        )
        return [(chunk, id_to_score[str(chunk.id)]) for chunk in chunks]

    async def search_chunks_fulltext(
        self, *, user_id: uuid.UUID, query_text: str, limit: int
    ) -> Sequence[Tuple[KnowledgeChunk, float]]:
        """PostgreSQL full-text search over ``knowledge_chunks.content_tsv``
        (migration 0018 - a generated column, always in sync with
        ``content``). ``simple`` config: no stemming, so a CVE ID or hash
        matches literally rather than being mangled by English stemming.
        Postgres-only, mirrors :meth:`search_chunks`'s scoping rules.
        """
        rows = await self._session.execute(
            sa.text(
                """
                SELECT kc.id AS id,
                       ts_rank(kc.content_tsv, plainto_tsquery('simple', :query)) AS rank
                FROM knowledge_chunks kc
                JOIN knowledge_documents kd ON kd.id = kc.document_id
                WHERE (kd.owner_user_id IS NULL OR kd.owner_user_id = :user_id)
                  AND kd.processing_status = 'ready'
                  AND kc.content_tsv @@ plainto_tsquery('simple', :query)
                ORDER BY rank DESC
                LIMIT :limit
                """
            ),
            {"query": query_text, "user_id": str(user_id), "limit": limit},
        )
        id_to_rank = {str(row.id): float(row.rank) for row in rows.all()}
        return await self._hydrate(id_to_rank)

    async def search_chunks_exact(
        self, *, user_id: uuid.UUID, terms: Sequence[str], limit: int
    ) -> Sequence[Tuple[KnowledgeChunk, float]]:
        """Chunks containing any of ``terms`` verbatim (case-insensitive) -
        exact-match priority for CVE IDs, IPs, hashes, MITRE technique IDs,
        domains and ports (see ``backend.services.rag_hybrid.
        extract_exact_match_terms``). Every term is bound as its own
        parameter - only the placeholder *names* are interpolated into the
        query text, never a term's value, so this stays injection-safe even
        though the term list length is dynamic.
        """
        if not terms:
            return []
        conditions = " OR ".join(f"kc.content ILIKE :term{i}" for i in range(len(terms)))
        params: dict[str, Any] = {f"term{i}": f"%{term}%" for i, term in enumerate(terms)}
        params.update({"user_id": str(user_id), "limit": limit})
        rows = await self._session.execute(
            # `conditions` interpolates only placeholder names (:term0,
            # :term1, ...) derived from range(len(terms)) - never a term's
            # actual value, which is always bound via `params` above. Both
            # scanners flag any f-string reaching sa.text() on sight and
            # cannot see that distinction from the pattern alone - verified
            # safe by inspection, not a suppression of a real finding.
            # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text  # noqa: E501
            sa.text(
                f"""
                SELECT DISTINCT kc.id AS id
                FROM knowledge_chunks kc
                JOIN knowledge_documents kd ON kd.id = kc.document_id
                WHERE (kd.owner_user_id IS NULL OR kd.owner_user_id = :user_id)
                  AND kd.processing_status = 'ready'
                  AND ({conditions})
                LIMIT :limit
                """  # nosec B608
            ),
            params,
        )
        # A fixed high score: exact matches are prioritized over any
        # vector/text rank score (both normalized to [0, 1]) rather than
        # competing with them numerically.
        id_to_score = {str(row.id): 1.0 for row in rows.all()}
        return await self._hydrate(id_to_score)
