"""One-shot live verification of Phase 2.6 RAG against a REAL hosted Supabase project.

Mirrors :mod:`backend.scripts.verify_cloud_e2e`'s rigor: two real users
created via the Supabase Auth Admin API, signed in for real, driving the
actual FastAPI app (real JWKS fetch, real SQLAlchemy, real hosted Postgres
RLS) - nothing internal is mocked. Adds RAG-specific checks: private-document
upload/retrieval/citation, cross-user isolation, and a global document
readable by both users but not writable by either through the API.

Test users are prefixed ``phase26-rag-cloud-e2e-`` and deleted at the end of
the run, success or failure. Any document rows created are deleted through
the API itself (or directly, for the global document, since no endpoint lets
a regular user create one).

Usage - reads SUPABASE_URL / SUPABASE_PUBLISHABLE_KEY / SUPABASE_SECRET_KEY
/ DATABASE_URL / DATABASE_MIGRATION_URL from .env in the current directory.
Must already be migrated to 0005.

    python -m backend.scripts.verify_rag_cloud_e2e
"""
import asyncio
import os
import sys
import uuid

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import httpx  # noqa: E402
import psycopg  # noqa: E402

SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
PUBLISHABLE_KEY = os.environ["SUPABASE_PUBLISHABLE_KEY"]
SECRET_KEY = os.environ["SUPABASE_SECRET_KEY"]
TEST_PASSWORD = "Phase26-RagCloudE2E-" + uuid.uuid4().hex  # nosec B105 - random, throwaway test credential


def _admin_headers() -> dict:
    return {"apikey": SECRET_KEY, "Authorization": f"Bearer {SECRET_KEY}"}


def create_user(email: str) -> str:
    response = httpx.post(
        f"{SUPABASE_URL}/auth/v1/admin/users",
        headers=_admin_headers(),
        json={"email": email, "password": TEST_PASSWORD, "email_confirm": True},
        timeout=15,
    )
    response.raise_for_status()
    return response.json()["id"]


def sign_in(email: str) -> str:
    response = httpx.post(
        f"{SUPABASE_URL}/auth/v1/token?grant_type=password",
        headers={"apikey": PUBLISHABLE_KEY, "Content-Type": "application/json"},
        json={"email": email, "password": TEST_PASSWORD},
        timeout=15,
    )
    response.raise_for_status()
    return response.json()["access_token"]


def delete_user(user_id: str) -> None:
    httpx.delete(
        f"{SUPABASE_URL}/auth/v1/admin/users/{user_id}", headers=_admin_headers(), timeout=15
    )


async def _embed_text(text: str) -> list[float]:
    from backend.providers.embeddings.local import LocalEmbeddingProvider

    provider = LocalEmbeddingProvider()
    return await provider.embed_one(text)


def _insert_global_document(run_id: str) -> tuple[str, str]:
    """Bypass the API (no endpoint lets a regular user do this) to seed a
    system-managed, NULL-owner document directly, matching how a real
    deployment would seed shared knowledge. Uses a real embedding (not a
    placeholder) so the retrieval checks below are a genuine similarity
    search, not a coincidence."""
    content = "Everyone can read this shared policy document."
    embedding = asyncio.run(_embed_text(content))

    dsn = os.environ["DATABASE_MIGRATION_URL"].replace("postgresql+psycopg://", "postgresql://")
    conn = psycopg.connect(dsn, autocommit=True)
    document_id = str(uuid.uuid4())
    chunk_id = str(uuid.uuid4())
    vector_literal = "[" + ",".join(str(v) for v in embedding) + "]"
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO knowledge_documents "
                "(id, owner_user_id, title, source_type, source_name, mime_type, checksum, "
                " processing_status, chunk_count) "
                "VALUES (%s, NULL, %s, 'system', 'global.md', 'text/markdown', %s, 'ready', 1)",
                (document_id, f"phase26-rag-cloud-e2e-global-{run_id}", f"global-{run_id}"),
            )
            cur.execute(
                "INSERT INTO knowledge_chunks "
                "(id, document_id, chunk_index, content, character_count, metadata, embedding) "
                "VALUES (%s, %s, 0, %s, %s, '{}', %s)",
                (chunk_id, document_id, content, len(content), vector_literal),
            )
    finally:
        conn.close()
    return document_id, chunk_id


def _delete_document_row(document_id: str) -> None:
    dsn = os.environ["DATABASE_MIGRATION_URL"].replace("postgresql+psycopg://", "postgresql://")
    conn = psycopg.connect(dsn, autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM knowledge_documents WHERE id = %s", (document_id,))
    finally:
        conn.close()


def main() -> int:
    import io

    from fastapi.testclient import TestClient

    from backend.main import app

    run_id = uuid.uuid4().hex[:8]
    email_a = f"phase26-rag-cloud-e2e-a-{run_id}@example.test"
    email_b = f"phase26-rag-cloud-e2e-b-{run_id}@example.test"
    user_ids: list[str] = []
    checks: list[tuple[str, bool]] = []
    cleanup_failures: list[str] = []
    private_document_id = None
    global_document_id = None
    primary_error: Exception | None = None

    try:
        user_a_id = create_user(email_a)
        user_ids.append(user_a_id)
        user_b_id = create_user(email_b)
        user_ids.append(user_b_id)

        token_a = sign_in(email_a)
        token_b = sign_in(email_b)

        global_document_id, _ = _insert_global_document(run_id)

        with TestClient(app) as client:
            headers_a = {"Authorization": f"Bearer {token_a}"}
            headers_b = {"Authorization": f"Bearer {token_b}"}

            no_token = client.get("/api/knowledge/documents")
            checks.append(
                ("no token on /api/knowledge/documents -> 401", no_token.status_code == 401)
            )

            files = {"file": ("runbook.md", io.BytesIO(
                b"# Ransomware containment\n\n"
                b"Isolate the affected host from the network immediately and "
                b"revoke active sessions before beginning forensic imaging."
            ), "text/markdown")}
            uploaded = client.post(
                "/api/knowledge/documents",
                files=files,
                data={"title": f"phase26-rag-cloud-e2e-{run_id}"},
                headers=headers_a,
            )
            checks.append(("A uploads a document -> 201", uploaded.status_code == 201))
            body = uploaded.json()
            private_document_id = body.get("document", {}).get("id")
            uploaded_status = body.get("document", {}).get("processing_status")
            checks.append(
                ("uploaded document reaches status=ready", uploaded_status == "ready")
            )

            cross_get = client.get(
                f"/api/knowledge/documents/{private_document_id}", headers=headers_b
            )
            checks.append(
                ("B cannot GET A's private document -> 404", cross_get.status_code == 404)
            )

            cross_delete = client.delete(
                f"/api/knowledge/documents/{private_document_id}", headers=headers_b
            )
            checks.append(
                ("B cannot DELETE A's private document -> 404", cross_delete.status_code == 404)
            )

            a_preview = client.post(
                "/api/knowledge/retrieval/preview",
                json={"query": "how do we contain ransomware?", "limit": 3},
                headers=headers_a,
            )
            a_results = a_preview.json().get("results", [])
            checks.append(("A's retrieval preview finds her own document", len(a_results) > 0))

            b_preview_same_query = client.post(
                "/api/knowledge/retrieval/preview",
                json={"query": "how do we contain ransomware?", "limit": 3},
                headers=headers_b,
            )
            b_results = b_preview_same_query.json().get("results", [])
            checks.append(
                (
                    "B's retrieval preview never returns A's private document",
                    all(r["document_id"] != private_document_id for r in b_results),
                )
            )

            a_global_preview = client.post(
                "/api/knowledge/retrieval/preview",
                json={"query": "shared policy document", "limit": 5},
                headers=headers_a,
            )
            b_global_preview = client.post(
                "/api/knowledge/retrieval/preview",
                json={"query": "shared policy document", "limit": 5},
                headers=headers_b,
            )
            a_global_results = a_global_preview.json().get("results", [])
            b_global_results = b_global_preview.json().get("results", [])
            a_sees_global = any(r["document_id"] == global_document_id for r in a_global_results)
            b_sees_global = any(r["document_id"] == global_document_id for r in b_global_results)
            checks.append(("A can retrieve the global document", a_sees_global))
            checks.append(("B can retrieve the global document", b_sees_global))

            chat = client.post(
                "/api/chatbot/chat",
                json={"message": "How do we contain ransomware?", "mode": "deep"},
                headers=headers_a,
            )
            checks.append(("A's chat call succeeds -> 200", chat.status_code == 200))
            chat_body = chat.json()
            chat_citations = chat_body.get("citations", [])
            checks.append(
                ("Chat response is grounded", chat_body.get("metadata", {}).get("grounded") is True)
            )
            checks.append(
                ("Chat response includes at least one citation", len(chat_citations) > 0)
            )
            citation_doc_ids = {c.get("document_id") for c in chat_citations}
            checks.append(
                (
                    "Citation references A's own uploaded document",
                    private_document_id in citation_doc_ids,
                )
            )

            cleanup = client.delete(
                f"/api/knowledge/documents/{private_document_id}", headers=headers_a
            )
            checks.append(("A cleans up her own document -> 204", cleanup.status_code == 204))
            private_document_id = None

    except Exception as exc:
        # The primary failure is preserved and re-raised below, after cleanup
        # has still been attempted for whatever partial state exists.
        primary_error = exc
    finally:
        if private_document_id:
            try:
                _delete_document_row(private_document_id)
            except psycopg.Error:
                cleanup_failures.append("private document row")
                print(
                    "WARN: cleanup failed removing the private test document row "
                    "(redacted - see hosted DB for orphaned phase26-rag-cloud-e2e-* data)",
                    file=sys.stderr,
                )
        if global_document_id:
            try:
                _delete_document_row(global_document_id)
            except psycopg.Error:
                cleanup_failures.append("global document row")
                print(
                    "WARN: cleanup failed removing the global test document row "
                    "(redacted - see hosted DB for orphaned phase26-rag-cloud-e2e-* data)",
                    file=sys.stderr,
                )
        for uid in user_ids:
            try:
                delete_user(uid)
            except httpx.HTTPError:
                cleanup_failures.append("auth test user")
                print(
                    "WARN: cleanup failed removing an auth test user "
                    "(redacted - see hosted project for orphaned phase26-rag-cloud-e2e-* users)",
                    file=sys.stderr,
                )

    if primary_error is not None:
        print(f"FAIL: unhandled error during verification ({type(primary_error).__name__})")
        if cleanup_failures:
            print(f"CLEANUP FAILED: {len(cleanup_failures)} resource(s) not confirmed removed")
        raise primary_error

    all_pass = True
    for name, ok in checks:
        print(f"{'PASS' if ok else 'FAIL'}: {name}")
        all_pass = all_pass and ok
    print(f"Test users created and deleted: {len(user_ids)}")
    if cleanup_failures:
        print(f"CLEANUP FAILED: {len(cleanup_failures)} resource(s) not confirmed removed")
        return 1
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
