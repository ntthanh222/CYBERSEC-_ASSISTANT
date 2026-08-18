"""hybrid retrieval: full-text search column on knowledge_chunks

Revision ID: 0018
Revises: 0017

Adds a PostgreSQL generated ``tsvector`` column plus a GIN index, so
retrieval can combine pgvector semantic search with real PostgreSQL
full-text search (FINAL_MASTER_PROMPT_CYBERSEC_ASSISTANT.md section F) -
see ``backend/services/rag_hybrid.py`` and
``backend/repositories/knowledge.py``'s ``search_chunks_fulltext``.

Uses the ``simple`` text search configuration deliberately, not
``english``: this app's knowledge base mixes English and Vietnamese
cybersecurity content plus literal technical tokens (CVE IDs, hashes, MITRE
technique IDs) that English stemming would mangle (e.g. stripping
"scanning" to "scan" is fine for prose, but a CVE ID or IOC must match
exactly). ``simple`` tokenizes and lowercases without stemming or a
language-specific dictionary, which suits security-report text better than
prose stemming would - and PostgreSQL has no built-in Vietnamese dictionary
to select instead.

``GENERATED ALWAYS ... STORED`` keeps the column trivially in sync with
``content`` forever - no trigger, no application-level maintenance, and no
risk of it drifting out of date after an edit.
"""
from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE knowledge_chunks "
        "ADD COLUMN content_tsv tsvector "
        "GENERATED ALWAYS AS (to_tsvector('simple', content)) STORED"
    )
    op.execute(
        "CREATE INDEX ix_knowledge_chunks_content_tsv "
        "ON knowledge_chunks USING GIN (content_tsv)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_knowledge_chunks_content_tsv")
    op.execute("ALTER TABLE knowledge_chunks DROP COLUMN IF EXISTS content_tsv")
