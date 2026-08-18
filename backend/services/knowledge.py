"""Knowledge base ingestion/management orchestration (Phase 2.6 RAG).

Pipeline for an upload::

    validate (mime/size/filename) -> checksum -> extract -> normalize
    -> chunk -> embed -> replace chunks (all-or-nothing) -> status READY

Everything happens in memory - the raw upload is never written to disk, so
there is no temp file to clean up and no path-traversal surface from a
filename. A document is created and committed as ``processing`` immediately
(so the caller gets an id right away), then either transitions to ``ready``
with a fully-populated chunk set, or to ``failed`` with a safe error message
and *zero* chunk rows - a partially embedded document is never left behind
(``replace_chunks`` deletes-then-inserts inside one flush, and any exception
before that point means nothing was ever added to the session).
"""
import hashlib
import logging
import os
import uuid
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.config.settings import get_settings
from backend.core.audit import log_audit_event
from backend.core.exceptions import (
    AppError,
    InvalidRequestError,
    NotFoundError,
    PayloadTooLargeError,
)
from backend.core.rag_cache import bump_knowledge_version
from backend.database.models.knowledge import KnowledgeChunk, KnowledgeDocument
from backend.providers.embeddings.base import BaseEmbeddingProvider
from backend.providers.embeddings.registry import get_embedding_provider
from backend.repositories.knowledge import KnowledgeRepository
from backend.services.knowledge_chunking import ExtractedSection, chunk_sections
from backend.services.knowledge_extraction import ExtractionResult, detect_kind, extract

logger = logging.getLogger("backend.services.knowledge")

TITLE_MAX_CHARS = 300


@dataclass(frozen=True)
class IngestionOutcome:
    document: KnowledgeDocument
    created: bool
    reused: bool


def _sanitize_filename(filename: str) -> str:
    """Strip any path component and control characters from a client filename.

    The filename is only ever used as a display string (``source_name``) - it
    is never used to open a path on disk - but it is defended anyway so a
    filename like ``../../etc/passwd`` or one containing a NUL byte can never
    reach a log line, response, or future code path unexpectedly.
    """
    base = os.path.basename((filename or "").replace("\\", "/")).strip()
    base = "".join(ch for ch in base if ch.isprintable())
    base = base.strip().lstrip(".")
    if not base:
        base = "document"
    return base[:TITLE_MAX_CHARS]


def _compute_checksum(sections_text: str) -> str:
    return hashlib.sha256(sections_text.encode("utf-8")).hexdigest()


class KnowledgeService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        embedding_provider: Optional[BaseEmbeddingProvider] = None,
    ) -> None:
        self._session = session
        self._repo = KnowledgeRepository(session)
        self._embeddings = embedding_provider or get_embedding_provider()
        self._settings = get_settings()

    async def list_documents(self, *, user_id: uuid.UUID, page: int, page_size: int):
        return await self._repo.list_documents(user_id=user_id, page=page, page_size=page_size)

    async def get_document(
        self, document_id: uuid.UUID, *, user_id: uuid.UUID
    ) -> KnowledgeDocument:
        document = await self._repo.get(document_id, user_id=user_id)
        if document is None:
            raise NotFoundError("Không tìm thấy tài liệu.")
        return document

    async def delete_document(
        self, document_id: uuid.UUID, *, user_id: uuid.UUID, actor: Optional[str]
    ) -> None:
        document = await self._repo.get_owned(document_id, user_id=user_id)
        if document is None:
            raise NotFoundError("Không tìm thấy tài liệu.")
        await self._repo.delete(document)
        await self._session.commit()
        await bump_knowledge_version(user_id=document.owner_user_id)
        log_audit_event(
            event_type="knowledge",
            action="document_deleted",
            resource=f"knowledge_document:{document_id}",
            result="success",
            actor=actor,
        )

    async def ingest(
        self,
        *,
        filename: str,
        content_type: str,
        raw_bytes: bytes,
        title: Optional[str],
        user_id: Optional[uuid.UUID],
        actor: Optional[str],
    ) -> IngestionOutcome:
        """``user_id=None`` ingests a system/global document (visible to
        every caller, owned by nobody) - used only by the Demo Mode
        knowledge-pack seed (backend/services/demo_knowledge.py), never by
        the authenticated upload API route, which always passes a real
        caller id."""
        settings = self._settings
        if len(raw_bytes) > settings.rag_max_upload_bytes:
            raise PayloadTooLargeError(
                f"Tệp vượt quá kích thước tối đa cho phép là "
                f"{settings.rag_max_upload_bytes} byte."
            )
        if not raw_bytes:
            raise InvalidRequestError("Tệp tải lên trống.")

        safe_name = _sanitize_filename(filename)
        detected = detect_kind(raw_bytes, content_type, safe_name)
        kind = detected.kind
        extraction = extract(kind=kind, raw_bytes=raw_bytes, max_pages=settings.rag_max_pages)

        joined_text = "\n\n".join(section.text for section in extraction.sections)
        checksum = _compute_checksum(joined_text)

        existing = await self._repo.get_by_checksum(owner_user_id=user_id, checksum=checksum)
        if existing is not None and existing.processing_status in ("ready", "processing"):
            # Idempotent re-upload: identical content already ingested (or
            # currently being ingested) for this owner - do not duplicate it.
            return IngestionOutcome(document=existing, created=False, reused=True)

        clean_title = (title or "").strip() or safe_name
        if len(clean_title) > TITLE_MAX_CHARS:
            clean_title = clean_title[: TITLE_MAX_CHARS - 1].rstrip() + "…"

        if existing is not None:
            # A prior attempt failed - retry into the same row instead of
            # accumulating duplicate failed rows for identical content.
            document = existing
            document.processing_status = "processing"
            document.title = clean_title
            document.mime_type = content_type or f"application/{kind}"
            document.source_name = safe_name
            await self._session.flush()
        else:
            document = await self._repo.create_document(
                owner_user_id=user_id,
                title=clean_title,
                source_type="upload",
                source_name=safe_name,
                mime_type=content_type or f"application/{kind}",
                checksum=checksum,
            )
        await self._session.commit()

        await self._process(document, extraction=extraction, actor=actor)
        return IngestionOutcome(document=document, created=existing is None, reused=False)

    async def reprocess(
        self, document_id: uuid.UUID, *, user_id: uuid.UUID, actor: Optional[str]
    ) -> KnowledgeDocument:
        """Re-chunk and re-embed a document from its already-stored chunk text.

        The raw uploaded file is never retained (see module docstring), so
        reprocessing works from the document's existing chunk content instead
        of the original bytes - each existing chunk becomes a pseudo-section
        (keeping its page/heading), which is then re-chunked with the
        currently configured chunk size/overlap and re-embedded with the
        currently configured embedding provider. This is the real, useful
        case for "reprocess": picking up a changed chunking config or a
        redeployed embedding model, not recovering from a first-time failure
        (which has nothing to reprocess and must be re-uploaded).
        """
        document = await self._repo.get_owned_with_chunks(document_id, user_id=user_id)
        if document is None:
            raise NotFoundError("Không tìm thấy tài liệu.")
        existing_chunks = sorted(document.chunks, key=lambda c: c.chunk_index)
        if not existing_chunks:
            raise InvalidRequestError(
                "Tài liệu này chưa có nội dung để xử lý lại; hãy tải lên lại tài liệu."
            )

        sections = [
            ExtractedSection(
                text=chunk.content,
                page_number=(chunk.meta or {}).get("page"),
                heading=(chunk.meta or {}).get("heading"),
            )
            for chunk in existing_chunks
        ]
        document.processing_status = "processing"
        await self._session.commit()

        extraction = ExtractionResult(sections=sections, page_count=document.page_count)
        await self._process(document, extraction=extraction, actor=actor)
        return document

    async def _process(
        self, document: KnowledgeDocument, *, extraction, actor: Optional[str]
    ) -> None:
        settings = self._settings
        try:
            chunks = chunk_sections(
                extraction.sections,
                chunk_size=settings.rag_chunk_size_chars,
                overlap=settings.rag_chunk_overlap_chars,
                min_chunk_chars=settings.rag_min_chunk_chars,
            )
            if not chunks:
                raise InvalidRequestError("Tài liệu không tạo ra được đoạn nội dung nào sử dụng được.")
            if len(chunks) > settings.rag_max_chunks_per_document:
                raise PayloadTooLargeError(
                    "Tài liệu quá lớn: số đoạn nội dung tạo ra vượt quá "
                    f"giới hạn cấu hình là {settings.rag_max_chunks_per_document}."
                )

            vectors = await self._embeddings.embed([chunk.content for chunk in chunks])
            if len(vectors) != len(chunks):
                raise AppError("Số lượng vector embedding không khớp với số đoạn nội dung.")

            chunk_rows = [
                KnowledgeChunk(
                    document_id=document.id,
                    chunk_index=index,
                    content=chunk.content,
                    character_count=chunk.character_count,
                    meta=chunk.metadata,
                    embedding=vector,
                )
                for index, (chunk, vector) in enumerate(zip(chunks, vectors, strict=False))
            ]
            await self._repo.replace_chunks(document, chunk_rows)
            await self._repo.mark_ready(
                document, page_count=extraction.page_count, chunk_count=len(chunk_rows)
            )
            await self._session.commit()
            await bump_knowledge_version(user_id=document.owner_user_id)
            log_audit_event(
                event_type="knowledge",
                action="document_ingested",
                resource=f"knowledge_document:{document.id}",
                result="success",
                actor=actor,
                metadata={"chunk_count": len(chunk_rows)},
            )
        except AppError as exc:
            await self._session.rollback()
            await self._repo.mark_failed(document, error_message=exc.message)
            await self._session.commit()
            log_audit_event(
                event_type="knowledge",
                action="document_ingested",
                resource=f"knowledge_document:{document.id}",
                result="failure",
                actor=actor,
                metadata={"error": exc.error},
            )
        except Exception:
            await self._session.rollback()
            logger.exception(
                "knowledge_ingestion_failed", extra={"fields": {"document_id": str(document.id)}}
            )
            await self._repo.mark_failed(
                document, error_message="Xử lý thất bại do lỗi nội bộ."
            )
            await self._session.commit()
            log_audit_event(
                event_type="knowledge",
                action="document_ingested",
                resource=f"knowledge_document:{document.id}",
                result="failure",
                actor=actor,
                metadata={"error": "internal_error"},
            )
