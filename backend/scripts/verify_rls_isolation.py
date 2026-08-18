"""One-shot live verification that RLS actually isolates two users.

Not part of the pytest suite (it needs a real Postgres reachable at
``DATABASE_MIGRATION_URL`` / the target this script is pointed at, already
migrated to 0004) - run manually against a throwaway Docker Postgres or a
Supabase project after ``alembic upgrade head``. Exercises the exact
mechanism the running application uses (``SET LOCAL ROLE authenticated`` +
``request.jwt.claims``, see backend/database/session.py:get_rls_db), not a
superuser bypassing everything.

Usage::

    python -m backend.scripts.verify_rls_isolation "postgresql://user:pass@host:port/db"
"""
import json
import sys
import uuid

import psycopg


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
    # Accept either a plain libpq DSN or a SQLAlchemy-style
    # "postgresql+psycopg://" one (psycopg itself only understands the former).
    dsn = dsn.replace("postgresql+psycopg://", "postgresql://")
    admin = psycopg.connect(dsn, autocommit=True)
    user_a = uuid.uuid4()
    user_b = uuid.uuid4()
    with admin.cursor() as cur:
        cur.execute("INSERT INTO auth.users (id) VALUES (%s), (%s)", (str(user_a), str(user_b)))
    admin.close()

    checks: list[tuple[str, bool]] = []

    conn_a = _connect_as(dsn, user_a)
    with conn_a.cursor() as cur:
        cur.execute(
            "INSERT INTO conversations (id, title, user_id) VALUES (%s, %s, %s) RETURNING id",
            (str(uuid.uuid4()), "A's private conversation", str(user_a)),
        )
        conv_id = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO messages (id, conversation_id, role, content) "
            "VALUES (%s, %s, 'user', 'secret')",
            (str(uuid.uuid4()), str(conv_id)),
        )
    conn_a.commit()

    conn_b = _connect_as(dsn, user_b)
    with conn_b.cursor() as cur:
        cur.execute("SELECT * FROM conversations WHERE id = %s", (str(conv_id),))
        checks.append(("B cannot SELECT A's conversation", cur.fetchone() is None))

        cur.execute("SELECT * FROM messages WHERE conversation_id = %s", (str(conv_id),))
        checks.append(("B cannot SELECT A's messages", cur.fetchone() is None))

        cur.execute(
            "UPDATE conversations SET title = 'pwned' WHERE id = %s", (str(conv_id),)
        )
        checks.append(("B's UPDATE on A's row affects 0 rows", cur.rowcount == 0))

        cur.execute("DELETE FROM conversations WHERE id = %s", (str(conv_id),))
        checks.append(("B's DELETE on A's row affects 0 rows", cur.rowcount == 0))

        try:
            cur.execute(
                "INSERT INTO conversations (id, title, user_id) VALUES (%s, %s, %s)",
                (str(uuid.uuid4()), "B claims to be A", str(user_a)),
            )
            conn_b.commit()
            checks.append(("B cannot INSERT a row claiming to be A", False))
        except psycopg.errors.InsufficientPrivilege:
            conn_b.rollback()
            checks.append(("B cannot INSERT a row claiming to be A", True))
    conn_b.rollback()
    conn_b.close()

    conn_a2 = _connect_as(dsn, user_a)
    with conn_a2.cursor() as cur:
        cur.execute("SELECT title FROM conversations WHERE id = %s", (str(conv_id),))
        row = cur.fetchone()
        unchanged = row is not None and row[0] == "A's private conversation"
        checks.append(("A's conversation still exists and is unmodified", unchanged))
    conn_a2.close()

    conn_a3 = _connect_as(dsn, user_a)
    with conn_a3.cursor() as cur:
        cur.execute(
            "INSERT INTO assets (id, user_id, name, type, hostname, ip_address, "
            "operating_system, owner, department, business_criticality) "
            "VALUES (%s, %s, %s, 'server', 'a-host', '10.0.0.1', 'Linux', "
            "'A', 'A Dept', 'low') RETURNING id",
            (str(uuid.uuid4()), str(user_a), "A's private asset"),
        )
        asset_id = cur.fetchone()[0]
    conn_a3.commit()

    conn_b2 = _connect_as(dsn, user_b)
    with conn_b2.cursor() as cur:
        cur.execute("SELECT * FROM assets WHERE id = %s", (str(asset_id),))
        checks.append(("B cannot SELECT A's asset", cur.fetchone() is None))

        cur.execute("UPDATE assets SET name = 'pwned' WHERE id = %s", (str(asset_id),))
        checks.append(("B's UPDATE on A's asset affects 0 rows", cur.rowcount == 0))

        cur.execute("DELETE FROM assets WHERE id = %s", (str(asset_id),))
        checks.append(("B's DELETE on A's asset affects 0 rows", cur.rowcount == 0))

        try:
            cur.execute(
                "INSERT INTO assets (id, user_id, name, type, hostname, ip_address, "
                "operating_system, owner, department, business_criticality) "
                "VALUES (%s, %s, 'B claims to be A', 'server', 'b-host', '10.0.0.2', "
                "'Linux', 'B', 'B Dept', 'low')",
                (str(uuid.uuid4()), str(user_a)),
            )
            conn_b2.commit()
            checks.append(("B cannot INSERT an asset claiming to be A", False))
        except psycopg.errors.InsufficientPrivilege:
            conn_b2.rollback()
            checks.append(("B cannot INSERT an asset claiming to be A", True))
    conn_b2.rollback()
    conn_b2.close()

    conn_a4 = _connect_as(dsn, user_a)
    with conn_a4.cursor() as cur:
        cur.execute("SELECT name FROM assets WHERE id = %s", (str(asset_id),))
        row = cur.fetchone()
        unchanged = row is not None and row[0] == "A's private asset"
        checks.append(("A's asset still exists and is unmodified", unchanged))
    conn_a4.close()

    all_pass = True
    for name, ok in checks:
        print(f"{'PASS' if ok else 'FAIL'}: {name}")
        all_pass = all_pass and ok

    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
