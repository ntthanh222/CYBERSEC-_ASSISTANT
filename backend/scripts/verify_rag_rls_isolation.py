"""One-shot live verification that RLS actually isolates two users' knowledge base data.

Mirrors :mod:`backend.scripts.verify_rls_isolation`'s approach for
``conversations``/``messages``, extended to ``knowledge_documents``/
``knowledge_chunks`` and their global-vs-private split. Not part of the
pytest suite - run manually against a throwaway Docker Postgres or a
Supabase project already migrated to 0005. Uses a placeholder embedding
vector (RLS does not depend on vector content); real embedding correctness
is exercised separately.

Usage::

    python -m backend.scripts.verify_rag_rls_isolation "postgresql://user:pass@host:port/db"
"""
import json
import sys
import uuid

import psycopg

_DIMENSION = 384
_PLACEHOLDER_VECTOR = "[" + ",".join("0" for _ in range(_DIMENSION)) + "]"


def _connect_as(dsn: str, user_id: uuid.UUID):
    conn = psycopg.connect(dsn, autocommit=False)
    with conn.cursor() as cur:
        cur.execute("SET LOCAL ROLE authenticated")
        cur.execute(
            "SELECT set_config('request.jwt.claims', %s, true)",
            (json.dumps({"sub": str(user_id), "role": "authenticated"}),),
        )
    return conn


def main(dsn: str) -> int:
    dsn = dsn.replace("postgresql+psycopg://", "postgresql://")
    admin = psycopg.connect(dsn, autocommit=True)
    user_a = uuid.uuid4()
    user_b = uuid.uuid4()
    global_doc_id = uuid.uuid4()
    with admin.cursor() as cur:
        cur.execute("INSERT INTO auth.users (id) VALUES (%s), (%s)", (str(user_a), str(user_b)))
        # A global (system-managed) document, inserted by the privileged
        # connecting role directly - never through the authenticated-role
        # RLS path, matching how migration 0005's INSERT policy forbids a
        # regular caller from creating one.
        cur.execute(
            "INSERT INTO knowledge_documents "
            "(id, owner_user_id, title, source_type, source_name, mime_type, checksum, "
            " processing_status, chunk_count) "
            "VALUES (%s, NULL, 'Global Policy', 'system', 'global.md', 'text/markdown', "
            " 'deadbeef', 'ready', 1)",
            (str(global_doc_id),),
        )
        cur.execute(
            "INSERT INTO knowledge_chunks "
            "(id, document_id, chunk_index, content, character_count, metadata, embedding) "
            "VALUES (%s, %s, 0, 'Everyone can read this.', 24, '{}', %s)",
            (str(uuid.uuid4()), str(global_doc_id), _PLACEHOLDER_VECTOR),
        )
    admin.close()

    checks: list[tuple[str, bool]] = []

    conn_a = _connect_as(dsn, user_a)
    private_doc_id = uuid.uuid4()
    with conn_a.cursor() as cur:
        cur.execute(
            "INSERT INTO knowledge_documents "
            "(id, owner_user_id, title, source_type, source_name, mime_type, checksum, "
            " processing_status, chunk_count) "
            "VALUES (%s, %s, 'A Private Doc', 'upload', 'a.txt', 'text/plain', 'abc123', "
            " 'ready', 1) RETURNING id",
            (str(private_doc_id), str(user_a)),
        )
        cur.fetchone()
        cur.execute(
            "INSERT INTO knowledge_chunks "
            "(id, document_id, chunk_index, content, character_count, metadata, embedding) "
            "VALUES (%s, %s, 0, 'A secret only A should read.', 27, '{}', %s)",
            (str(uuid.uuid4()), str(private_doc_id), _PLACEHOLDER_VECTOR),
        )
    # Commit A's legitimate rows *before* attempting the deliberately-failing
    # insert below - otherwise the rollback that failure triggers would also
    # undo these, since they would still be in the same transaction.
    conn_a.commit()

    with conn_a.cursor() as cur:
        cur.execute("SET LOCAL ROLE authenticated")
        cur.execute(
            "SELECT set_config('request.jwt.claims', %s, true)",
            (json.dumps({"sub": str(user_a), "role": "authenticated"}),),
        )
        cur.execute("SELECT id FROM knowledge_documents WHERE id = %s", (str(global_doc_id),))
        checks.append(("A can SELECT the global document", cur.fetchone() is not None))

        try:
            cur.execute(
                "INSERT INTO knowledge_documents "
                "(id, owner_user_id, title, source_type, source_name, mime_type, checksum, "
                " processing_status, chunk_count) "
                "VALUES (%s, NULL, 'Sneaky global', 'upload', 'x.txt', 'text/plain', "
                " 'zzz', 'ready', 0)",
                (str(uuid.uuid4()),),
            )
            conn_a.commit()
            checks.append(("A cannot INSERT a global (NULL-owner) document", False))
        except psycopg.errors.InsufficientPrivilege:
            conn_a.rollback()
            checks.append(("A cannot INSERT a global (NULL-owner) document", True))
    conn_a.commit()

    conn_b = _connect_as(dsn, user_b)
    with conn_b.cursor() as cur:
        cur.execute("SELECT id FROM knowledge_documents WHERE id = %s", (str(private_doc_id),))
        checks.append(("B cannot SELECT A's private document", cur.fetchone() is None))

        cur.execute(
            "SELECT id FROM knowledge_chunks WHERE document_id = %s", (str(private_doc_id),)
        )
        checks.append(("B cannot SELECT A's private chunks", cur.fetchone() is None))

        cur.execute("SELECT id FROM knowledge_documents WHERE id = %s", (str(global_doc_id),))
        checks.append(("B can SELECT the global document", cur.fetchone() is not None))

        cur.execute(
            "SELECT content FROM knowledge_chunks WHERE document_id = %s", (str(global_doc_id),)
        )
        checks.append(("B can SELECT the global document's chunks", cur.fetchone() is not None))

        cur.execute(
            "UPDATE knowledge_documents SET title = 'pwned' WHERE id = %s", (str(private_doc_id),)
        )
        checks.append(("B's UPDATE on A's document affects 0 rows", cur.rowcount == 0))

        cur.execute("DELETE FROM knowledge_documents WHERE id = %s", (str(private_doc_id),))
        checks.append(("B's DELETE on A's document affects 0 rows", cur.rowcount == 0))

        cur.execute("DELETE FROM knowledge_documents WHERE id = %s", (str(global_doc_id),))
        checks.append(("B's DELETE on the global document affects 0 rows", cur.rowcount == 0))

        try:
            cur.execute(
                "INSERT INTO knowledge_chunks "
                "(id, document_id, chunk_index, content, character_count, metadata, embedding) "
                "VALUES (%s, %s, 1, 'B tries to pollute the global doc.', 33, '{}', %s)",
                (str(uuid.uuid4()), str(global_doc_id), _PLACEHOLDER_VECTOR),
            )
            conn_b.commit()
            checks.append(("B cannot INSERT a chunk into the global document", False))
        except psycopg.errors.InsufficientPrivilege:
            conn_b.rollback()
            checks.append(("B cannot INSERT a chunk into the global document", True))
    conn_b.rollback()
    conn_b.close()

    conn_a2 = _connect_as(dsn, user_a)
    with conn_a2.cursor() as cur:
        cur.execute("SELECT title FROM knowledge_documents WHERE id = %s", (str(private_doc_id),))
        row = cur.fetchone()
        checks.append(
            (
                "A's document still exists and is unmodified",
                row is not None and row[0] == "A Private Doc",
            )
        )
    conn_a2.close()

    all_pass = True
    for name, ok in checks:
        print(f"{'PASS' if ok else 'FAIL'}: {name}")
        all_pass = all_pass and ok

    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
