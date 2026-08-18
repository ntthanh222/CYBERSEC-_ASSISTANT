"""One-shot live verification of the real RAG application code path.

Unlike ``verify_rag_rls_isolation.py`` (raw SQL, placeholder vectors), this
exercises the actual :class:`backend.services.knowledge.KnowledgeService`
(extraction -> chunking -> real local embedding -> persistence) and
:class:`backend.services.rag_retrieval.PgVectorRagRetriever` (real cosine
search) through a real ``AsyncSession`` running as the ``authenticated``
Postgres role - the same code the API routes use. Requires the target
already migrated to 0005.

Usage::

    python -m backend.scripts.verify_rag_e2e "postgresql+psycopg://user:pass@host:port/db"
"""
import asyncio
import json
import sys
import uuid

import psycopg
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

if sys.platform == "win32":
    # psycopg's async driver needs a selector event loop; Windows defaults
    # to ProactorEventLoop, which it cannot use. Docker/Linux (production
    # and CI) are unaffected - this is a local-verification-only script.
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from backend.services.knowledge import KnowledgeService
from backend.services.rag_retrieval import PgVectorRagRetriever


async def _run(dsn: str) -> int:
    checks: list[tuple[str, bool]] = []

    admin_dsn = dsn.replace("postgresql+psycopg://", "postgresql://")
    admin = psycopg.connect(admin_dsn, autocommit=True)
    user_a = uuid.uuid4()
    user_b = uuid.uuid4()
    with admin.cursor() as cur:
        cur.execute("INSERT INTO auth.users (id) VALUES (%s), (%s)", (str(user_a), str(user_b)))
    admin.close()

    engine = create_async_engine(dsn, pool_size=2, max_overflow=0)
    maker = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)

    async def scoped_session(user_id: uuid.UUID) -> AsyncSession:
        session = maker()
        await session.execute(text("SET LOCAL ROLE authenticated"))
        await session.execute(
            text("SELECT set_config('request.jwt.claims', :claims, true)"),
            {"claims": json.dumps({"sub": str(user_id), "role": "authenticated"})},
        )
        return session

    # --- A uploads a private document with real content ---
    session_a = await scoped_session(user_a)
    service_a = KnowledgeService(session_a)
    outcome = await service_a.ingest(
        filename="incident-response.md",
        content_type="text/markdown",
        raw_bytes=(
            b"# Ransomware containment\n\n"
            b"Isolate the affected host from the network immediately. "
            b"Disable shared drives and revoke active sessions before "
            b"beginning forensic imaging.\n\n"
            b"# Phishing response\n\n"
            b"Quarantine the reported email cluster-wide and rotate any "
            b"credentials the recipient may have entered on a lookalike site."
        ),
        title="Incident Response Runbook",
        user_id=user_a,
        actor="verify-rag-e2e",
    )
    checks.append(
        ("A's document reaches status=ready", outcome.document.processing_status == "ready")
    )
    checks.append(("A's document produced chunks", outcome.document.chunk_count >= 2))
    await session_a.commit()
    await session_a.close()

    # --- Idempotent re-upload: identical content is not duplicated ---
    session_a2 = await scoped_session(user_a)
    service_a2 = KnowledgeService(session_a2)
    outcome2 = await service_a2.ingest(
        filename="incident-response.md",
        content_type="text/markdown",
        raw_bytes=(
            b"# Ransomware containment\n\n"
            b"Isolate the affected host from the network immediately. "
            b"Disable shared drives and revoke active sessions before "
            b"beginning forensic imaging.\n\n"
            b"# Phishing response\n\n"
            b"Quarantine the reported email cluster-wide and rotate any "
            b"credentials the recipient may have entered on a lookalike site."
        ),
        title="Incident Response Runbook",
        user_id=user_a,
        actor="verify-rag-e2e",
    )
    checks.append(("Duplicate upload is reused, not re-ingested", outcome2.reused is True))
    await session_a2.commit()
    await session_a2.close()

    # --- A retrieves her own document by real semantic similarity ---
    session_a3 = await scoped_session(user_a)
    retriever_a = PgVectorRagRetriever(session_a3)
    results_a = await retriever_a.retrieve(
        "how do we contain a ransomware infection?", user_id=user_a, limit=3
    )
    checks.append(("A's retrieval finds her own document", len(results_a) > 0))
    checks.append(
        (
            "Top result mentions containment content",
            bool(results_a) and "isolate" in results_a[0].content.lower(),
        )
    )
    checks.append(
        (
            "Citation carries a page/heading or source",
            bool(results_a) and (results_a[0].heading or results_a[0].source),
        )
    )
    await session_a3.close()

    # --- B cannot retrieve A's private document ---
    session_b = await scoped_session(user_b)
    retriever_b = PgVectorRagRetriever(session_b)
    results_b = await retriever_b.retrieve(
        "how do we contain a ransomware infection?", user_id=user_b, limit=3
    )
    checks.append(("B's retrieval finds nothing (no global doc, not A's)", len(results_b) == 0))
    await session_b.close()

    # --- An irrelevant query returns no context (honest empty grounding) ---
    session_a4 = await scoped_session(user_a)
    retriever_a4 = PgVectorRagRetriever(session_a4)
    results_irrelevant = await retriever_a4.retrieve(
        "what is the capital of France?", user_id=user_a, limit=3
    )
    checks.append(
        ("Irrelevant query returns no/low-confidence context", len(results_irrelevant) == 0)
    )
    await session_a4.close()

    await engine.dispose()

    all_pass = True
    for name, ok in checks:
        print(f"{'PASS' if ok else 'FAIL'}: {name}")
        all_pass = all_pass and ok
    return 0 if all_pass else 1


def main(dsn: str) -> int:
    return asyncio.run(_run(dsn))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
