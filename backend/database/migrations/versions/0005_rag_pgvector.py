"""phase 2.6: knowledge base tables, pgvector, row level security

Revision ID: 0005
Revises: 0004

Adds the Retrieval-Augmented Generation knowledge base: ``knowledge_documents``
(one row per ingested source, optionally owned by a user or NULL for a
system-managed document shared with every authenticated caller) and
``knowledge_chunks`` (the embedded, retrievable slices of a document's text,
owned only through its parent document - the same "no ownership column of its
own, derive it" pattern ``messages`` uses for ``conversations`` in migration
0004).

Vector index: HNSW over ``vector_cosine_ops``, not IVFFlat. IVFFlat's `lists`
parameter has to be tuned from the row count at index-build time (the common
guidance is ``rows / 1000``); a brand-new table has zero rows, so any list
count chosen now would be wrong once real data lands and would need a manual
``REINDEX`` later. HNSW builds and queries well from an empty table and
degrades gracefully as data grows, so it needs no retuning migration. This
tradeoff (slower to build, but no retune step and better recall at moderate
scale) is the right one for a table starting at zero rows; see
``docs/RAG_ARCHITECTURE.md`` for the query-plan measurement taken against the
hosted database once it holds real chunks.

Requires the `vector` extension, present by default on Supabase and enabled
here via `CREATE EXTENSION IF NOT EXISTS vector` for local/Docker Postgres
(the `pgvector/pgvector` image ships the extension files; this statement only
activates it for this database).
"""
import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

from backend.config.settings import get_settings

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

#: Fixed at migration-authoring time from the deployment's configured
#: EMBEDDING_DIMENSION. Changing the embedding model's dimension for an
#: existing deployment requires a new migration that resizes this column and
#: re-embeds every stored chunk - it is not a runtime-configurable value once
#: this migration has run.
_EMBEDDING_DIMENSION = get_settings().embedding_dimension

_HNSW_INDEX_NAME = "ix_knowledge_chunks_embedding_hnsw_cosine"


def upgrade() -> None:
    op.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector"))

    op.create_table(
        "knowledge_documents",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("owner_user_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("source_type", sa.String(32), nullable=False, server_default="upload"),
        sa.Column("source_name", sa.String(300), nullable=False),
        sa.Column("mime_type", sa.String(128), nullable=False),
        sa.Column("checksum", sa.String(64), nullable=False),
        sa.Column(
            "processing_status", sa.String(16), nullable=False, server_default="pending"
        ),
        sa.Column("error_message", sa.String(500), nullable=True),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "source_type IN ('upload', 'system')", name="ck_knowledge_documents_source_type"
        ),
        sa.CheckConstraint(
            "processing_status IN ('pending', 'processing', 'ready', 'failed')",
            name="ck_knowledge_documents_processing_status",
        ),
        sa.ForeignKeyConstraint(
            ["owner_user_id"],
            ["auth.users.id"],
            name="fk_knowledge_documents_owner_user_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_knowledge_documents_owner_user_id", "knowledge_documents", ["owner_user_id"]
    )
    op.create_index("ix_knowledge_documents_checksum", "knowledge_documents", ["checksum"])

    op.create_table(
        "knowledge_chunks",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("document_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("character_count", sa.Integer(), nullable=False),
        sa.Column("metadata", postgresql_jsonb_or_json(), nullable=False, server_default="{}"),
        sa.Column("embedding", Vector(_EMBEDDING_DIMENSION), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["knowledge_documents.id"],
            name="fk_knowledge_chunks_document_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "document_id", "chunk_index", name="uq_knowledge_chunks_document_chunk"
        ),
    )
    op.create_index("ix_knowledge_chunks_document_id", "knowledge_chunks", ["document_id"])
    # index name is the hardcoded module constant _HNSW_INDEX_NAME, never
    # external input; SQL cannot bind identifiers as params.
    op.execute(
        sa.text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text -- static schema migration string
            f"CREATE INDEX {_HNSW_INDEX_NAME} ON knowledge_chunks "
            "USING hnsw (embedding vector_cosine_ops)"
        )
    )

    op.execute(
        sa.text("GRANT SELECT, INSERT, UPDATE, DELETE ON knowledge_documents TO authenticated")
    )
    op.execute(
        sa.text("GRANT SELECT, INSERT, UPDATE, DELETE ON knowledge_chunks TO authenticated")
    )

    for table in ("knowledge_documents", "knowledge_chunks"):
        op.execute(
            sa.text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text -- static schema migration string
                f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"
            )
        )
        # FORCE so even the table owner is subject to policy - this
        # application never queries these tables as the owner role (see
        # backend/database/session.py:get_rls_db).
        op.execute(
            sa.text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text -- static schema migration string
                f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"
            )
        )

    # knowledge_documents: read own + global; write/delete own only. A regular
    # authenticated caller can never create a global (owner_user_id IS NULL)
    # document - that is system-managed, seeded outside this RLS-protected
    # path - and can never assign another user's id as owner.
    op.execute(
        sa.text(
            "CREATE POLICY knowledge_documents_select ON knowledge_documents "
            "FOR SELECT "
            "USING (owner_user_id IS NULL OR owner_user_id = auth.uid())"
        )
    )
    op.execute(
        sa.text(
            "CREATE POLICY knowledge_documents_insert ON knowledge_documents "
            "FOR INSERT "
            "WITH CHECK (owner_user_id = auth.uid())"
        )
    )
    op.execute(
        sa.text(
            "CREATE POLICY knowledge_documents_update ON knowledge_documents "
            "FOR UPDATE "
            "USING (owner_user_id = auth.uid()) "
            "WITH CHECK (owner_user_id = auth.uid())"
        )
    )
    op.execute(
        sa.text(
            "CREATE POLICY knowledge_documents_delete ON knowledge_documents "
            "FOR DELETE "
            "USING (owner_user_id = auth.uid())"
        )
    )

    # knowledge_chunks: read follows the parent document's visibility (own +
    # global); write/delete only through a document the caller owns - nobody
    # can write chunks onto a global document via the authenticated role, and
    # nobody can write chunks onto another user's private document.
    op.execute(
        sa.text(
            "CREATE POLICY knowledge_chunks_select ON knowledge_chunks "
            "FOR SELECT "
            "USING (EXISTS ("
            "  SELECT 1 FROM knowledge_documents d "
            "  WHERE d.id = knowledge_chunks.document_id "
            "    AND (d.owner_user_id IS NULL OR d.owner_user_id = auth.uid())"
            "))"
        )
    )
    op.execute(
        sa.text(
            "CREATE POLICY knowledge_chunks_write ON knowledge_chunks "
            "FOR ALL "
            "USING (EXISTS ("
            "  SELECT 1 FROM knowledge_documents d "
            "  WHERE d.id = knowledge_chunks.document_id AND d.owner_user_id = auth.uid()"
            ")) "
            "WITH CHECK (EXISTS ("
            "  SELECT 1 FROM knowledge_documents d "
            "  WHERE d.id = knowledge_chunks.document_id AND d.owner_user_id = auth.uid()"
            "))"
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DROP POLICY IF EXISTS knowledge_chunks_write ON knowledge_chunks"))
    op.execute(sa.text("DROP POLICY IF EXISTS knowledge_chunks_select ON knowledge_chunks"))
    op.execute(
        sa.text("DROP POLICY IF EXISTS knowledge_documents_delete ON knowledge_documents")
    )
    op.execute(
        sa.text("DROP POLICY IF EXISTS knowledge_documents_update ON knowledge_documents")
    )
    op.execute(
        sa.text("DROP POLICY IF EXISTS knowledge_documents_insert ON knowledge_documents")
    )
    op.execute(
        sa.text("DROP POLICY IF EXISTS knowledge_documents_select ON knowledge_documents")
    )

    for table in ("knowledge_chunks", "knowledge_documents"):
        op.execute(
            sa.text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text -- static schema migration string
                f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY"
            )
        )
        op.execute(
            sa.text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text -- static schema migration string
                f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY"
            )
        )

    op.execute(
        sa.text("REVOKE SELECT, INSERT, UPDATE, DELETE ON knowledge_chunks FROM authenticated")
    )
    op.execute(
        sa.text(
            "REVOKE SELECT, INSERT, UPDATE, DELETE ON knowledge_documents FROM authenticated"
        )
    )

    op.execute(
        sa.text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text -- static schema migration string
            f"DROP INDEX IF EXISTS {_HNSW_INDEX_NAME}"
        )
    )
    op.drop_index("ix_knowledge_chunks_document_id", table_name="knowledge_chunks")
    op.drop_table("knowledge_chunks")

    op.drop_index("ix_knowledge_documents_checksum", table_name="knowledge_documents")
    op.drop_index("ix_knowledge_documents_owner_user_id", table_name="knowledge_documents")
    op.drop_table("knowledge_documents")

    # The `vector` extension is left installed on downgrade: it is a shared,
    # database-wide object that may be relied on by objects this migration
    # does not own, and dropping it is never required to reverse this
    # migration's own tables/columns.


def postgresql_jsonb_or_json() -> sa.types.TypeEngine:
    """JSONB on PostgreSQL, plain JSON elsewhere - matches backend.database.base.JSONVariant."""
    from sqlalchemy.dialects import postgresql

    return sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
