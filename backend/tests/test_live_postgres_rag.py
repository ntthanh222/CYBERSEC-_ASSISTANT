"""Live-Postgres integration tests for Phase 2.6 RAG (pgvector + RLS).

Skipped unless ``LIVE_POSTGRES_DSN`` is set (a Postgres already migrated to
revision 0005, with the ``vector`` extension available - e.g. the
``pgvector/pgvector`` Docker image or a Supabase project). See
``backend/tests/test_live_postgres_integration.py`` for why this shells out
to a subprocess rather than importing the verifier modules directly
(process-wide ``lru_cache`` singletons in settings/session make in-process
reconfiguration unsafe).

Run in isolation, e.g.::

    LIVE_POSTGRES_DSN="postgresql+psycopg://user:pass@host:port/db" \\
        pytest -q backend/tests/test_live_postgres_rag.py
"""
import os
import subprocess
import sys

import pytest

LIVE_DSN = os.environ.get("LIVE_POSTGRES_DSN")

pytestmark = pytest.mark.skipif(
    not LIVE_DSN,
    reason="LIVE_POSTGRES_DSN not set - these tests need a real Postgres migrated to 0005",
)


def _run_verifier(module: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", module, LIVE_DSN],
        capture_output=True,
        text=True,
        timeout=180,
    )


def test_raw_sql_rag_rls_isolation_including_global_documents():
    """Private documents/chunks are isolated per owner; a NULL-owner (global)
    document is readable by every user but writable by none of them through
    the authenticated role - exercised at the SQL level, independent of the
    application code."""
    result = _run_verifier("backend.scripts.verify_rag_rls_isolation")
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.count("PASS:") == 11, result.stdout


def test_real_ingestion_and_retrieval_over_the_application_code_path():
    """Real extraction -> chunking -> local embedding -> pgvector cosine
    search, through backend.services.knowledge.KnowledgeService and
    backend.services.rag_retrieval.PgVectorRagRetriever - the same code the
    API routes use, running as the authenticated role. Downloads/loads the
    local embedding model on first use, so this is slower than the other
    live checks."""
    result = _run_verifier("backend.scripts.verify_rag_e2e")
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.count("PASS:") == 8, result.stdout
