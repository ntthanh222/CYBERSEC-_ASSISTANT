"""Knowledge base models for Phase 2.6 Retrieval-Augmented Generation.

Two tables:

* ``knowledge_documents`` - one row per ingested source. ``owner_user_id`` is
  NULL for a system-managed document readable by every authenticated caller,
  or set to the uploading user's id for a private one. Migration 0005's Row
  Level Security policies enforce this exact split independently of the
  service-layer ownership checks in :mod:`backend.services.knowledge`.
* ``knowledge_chunks`` - the embedded, retrievable slices of a document's
  text. A chunk has no ownership column of its own; ownership is derived
  entirely through the parent document, mirroring how ``messages`` derives
  ownership from ``conversations`` (migration 0004).

Neither table stores a password, access token, refresh token, API key, or the
raw uploaded file bytes - only extracted text and safe metadata.
"""
import uuid
from typing import Any, Dict, List, Optional

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.engine.interfaces import Dialect
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator, TypeEngine

from backend.config.settings import get_settings
from backend.database.base import (
    Base,
    CreatedAtMixin,
    JSONVariant,
    TimestampMixin,
    UuidPrimaryKeyMixin,
    UuidType,
)

DOCUMENT_SOURCE_TYPES = ("upload", "system")
DOCUMENT_PROCESSING_STATUSES = ("pending", "processing", "ready", "failed")


class EmbeddingVector(TypeDecorator):
    """``vector(N)`` on PostgreSQL; a plain JSON float array everywhere else.

    Unit tests run on SQLite, which has no pgvector extension - this keeps the
    ORM layer importable and round-trippable there. Similarity search itself
    is Postgres-only (:mod:`backend.services.rag_retrieval`) and is verified
    against real Postgres, never on SQLite.
    """

    impl = sa.JSON
    cache_ok = True
    # TypeDecorator does not inherit its wrapped type's comparator by default,
    # so without this, `.cosine_distance()`/`.l2_distance()` etc. from
    # pgvector.sqlalchemy.Vector would not be reachable through this column -
    # this is what makes backend.repositories.knowledge.search_chunks' use of
    # KnowledgeChunk.embedding.cosine_distance(...) work.
    comparator_factory = Vector.comparator_factory

    def __init__(self, dimension: int, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.dimension = dimension

    def load_dialect_impl(self, dialect: Dialect) -> TypeEngine:
        if dialect.name == "postgresql":
            return dialect.type_descriptor(Vector(self.dimension))
        return dialect.type_descriptor(sa.JSON())


def _configured_embedding_dimension() -> int:
    return get_settings().embedding_dimension


class KnowledgeDocument(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "knowledge_documents"

    # NULL = a system-managed document visible to every authenticated user.
    # A UUID = a private document, readable/writable only by that user. Always
    # set from the verified JWT `sub` claim on upload, never client input.
    owner_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(UuidType, nullable=True)
    title: Mapped[str] = mapped_column(sa.String(300), nullable=False)
    source_type: Mapped[str] = mapped_column(sa.String(32), nullable=False, default="upload")
    source_name: Mapped[str] = mapped_column(sa.String(300), nullable=False)
    mime_type: Mapped[str] = mapped_column(sa.String(128), nullable=False)
    # SHA-256 of the extracted, normalized text - not of the raw upload bytes,
    # so the same content re-saved under a different file format is still
    # caught as a duplicate. Backs idempotent re-upload.
    checksum: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    processing_status: Mapped[str] = mapped_column(
        sa.String(16), nullable=False, default="pending"
    )
    # Author-written, safe text only - never a stack trace, driver message, or
    # file path. Same rule as backend.core.exceptions.AppError.message.
    error_message: Mapped[Optional[str]] = mapped_column(sa.String(500), nullable=True)
    page_count: Mapped[Optional[int]] = mapped_column(sa.Integer, nullable=True)
    chunk_count: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)

    chunks: Mapped[List["KnowledgeChunk"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="KnowledgeChunk.chunk_index",
    )

    __table_args__ = (
        sa.CheckConstraint(
            "source_type IN ('upload', 'system')", name="ck_knowledge_documents_source_type"
        ),
        sa.CheckConstraint(
            "processing_status IN ('pending', 'processing', 'ready', 'failed')",
            name="ck_knowledge_documents_processing_status",
        ),
        sa.Index("ix_knowledge_documents_owner_user_id", "owner_user_id"),
        sa.Index("ix_knowledge_documents_checksum", "checksum"),
    )


class KnowledgeChunk(UuidPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "knowledge_chunks"

    document_id: Mapped[uuid.UUID] = mapped_column(
        UuidType,
        sa.ForeignKey("knowledge_documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    chunk_index: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    content: Mapped[str] = mapped_column(sa.Text, nullable=False)
    character_count: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    # page number, heading, source label, chunk provenance - never a secret.
    meta: Mapped[Dict[str, Any]] = mapped_column(
        "metadata", JSONVariant, nullable=False, default=dict
    )
    embedding: Mapped[List[float]] = mapped_column(
        EmbeddingVector(_configured_embedding_dimension()), nullable=False
    )

    document: Mapped[KnowledgeDocument] = relationship(back_populates="chunks")

    __table_args__ = (
        sa.UniqueConstraint(
            "document_id", "chunk_index", name="uq_knowledge_chunks_document_chunk"
        ),
        sa.Index("ix_knowledge_chunks_document_id", "document_id"),
    )
