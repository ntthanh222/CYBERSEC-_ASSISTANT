"""One-shot live smoke test for the byte-level MIME sniffing fix (Codex block
on source ``649c6f4``), run against a REAL hosted Supabase project already
migrated to 0005.

Deliberately narrow in scope compared to :mod:`backend.scripts.verify_rag_e2e`
- this only proves the sniffing fix behaves correctly against real hosted
Postgres/pgvector, not the full RAG pipeline (already proven live in the
Phase 2.6 report). No migration is applied or replayed here.

Test data is prefixed ``phase26-mime-fix-smoke-`` and is fully deleted at the
end of the run, success or failure.

Usage - reads DATABASE_MIGRATION_URL from the process environment (load
.env into the shell first, e.g. ``set -a; . .env; set +a``). Never prints
the DSN or any credential.

    python -m backend.scripts.verify_rag_mime_smoke
"""
import asyncio
import json
import os
import sys
import uuid

import psycopg
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from backend.core.exceptions import UnsupportedMediaTypeError
from backend.services.knowledge import KnowledgeService

_PDF_BYTES = (
    b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF"
)


async def _run(dsn: str) -> int:
    checks: list[tuple[str, bool]] = []
    admin_dsn = dsn.replace("postgresql+psycopg://", "postgresql://")
    user_id = uuid.uuid4()

    admin = psycopg.connect(admin_dsn, autocommit=True)
    try:
        with admin.cursor() as cur:
            cur.execute("INSERT INTO auth.users (id) VALUES (%s)", (str(user_id),))

        engine = create_async_engine(dsn, pool_size=1, max_overflow=0)
        maker = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)

        async def scoped_session() -> AsyncSession:
            session = maker()
            await session.execute(text("SET LOCAL ROLE authenticated"))
            await session.execute(
                text("SELECT set_config('request.jwt.claims', :claims, true)"),
                {"claims": json.dumps({"sub": str(user_id), "role": "authenticated"})},
            )
            return session

        # 1. A legitimate Markdown upload still reaches ready against real
        #    hosted Postgres/pgvector.
        session = await scoped_session()
        service = KnowledgeService(session)
        outcome = await service.ingest(
            filename="phase26-mime-fix-smoke-notes.md",
            content_type="text/markdown",
            raw_bytes=b"# MIME fix smoke test\n\nReal document, real bytes, real hosted DB.",
            title="phase26-mime-fix-smoke",
            user_id=user_id,
            actor="verify-rag-mime-smoke",
        )
        checks.append(
            ("Legit Markdown upload reaches ready", outcome.document.processing_status == "ready")
        )
        await session.commit()
        await session.close()

        # 2. Real PDF bytes declared as text/plain -> hard 415, zero rows.
        session2 = await scoped_session()
        service2 = KnowledgeService(session2)
        rejected = False
        try:
            await service2.ingest(
                filename="phase26-mime-fix-smoke-fake.txt",
                content_type="text/plain",
                raw_bytes=_PDF_BYTES,
                title="phase26-mime-fix-smoke-mismatch",
                user_id=user_id,
                actor="verify-rag-mime-smoke",
            )
        except UnsupportedMediaTypeError:
            rejected = True
        checks.append(("PDF-bytes-declared-as-text upload is rejected", rejected))
        await session2.rollback()
        await session2.close()

        # 3. Confirm the rejected upload created no document row.
        session3 = await scoped_session()
        count = (
            await session3.execute(
                text(
                    "SELECT count(*) FROM knowledge_documents "
                    "WHERE owner_user_id = :uid AND source_name LIKE 'phase26-mime-fix-smoke-fake%'"
                ),
                {"uid": str(user_id)},
            )
        ).scalar_one()
        checks.append(("Rejected upload created zero document rows", count == 0))
        await session3.close()

        await engine.dispose()
    finally:
        # Cleanup: delete every row this run could have created, then the
        # throwaway user itself.
        with admin.cursor() as cur:
            cur.execute(
                "DELETE FROM knowledge_chunks WHERE document_id IN "
                "(SELECT id FROM knowledge_documents WHERE owner_user_id = %s)",
                (str(user_id),),
            )
            cur.execute("DELETE FROM knowledge_documents WHERE owner_user_id = %s", (str(user_id),))
            cur.execute("DELETE FROM auth.users WHERE id = %s", (str(user_id),))
        admin.close()

    all_pass = True
    for name, ok in checks:
        print(f"{'PASS' if ok else 'FAIL'}: {name}")
        all_pass = all_pass and ok
    return 0 if all_pass else 1


def main() -> int:
    dsn = os.environ["DATABASE_MIGRATION_URL"]
    return asyncio.run(_run(dsn))


if __name__ == "__main__":
    sys.exit(main())
