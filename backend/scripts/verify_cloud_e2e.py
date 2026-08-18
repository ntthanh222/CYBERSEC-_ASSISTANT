"""One-shot live verification against a REAL hosted Supabase project.

Unlike verify_http_rls_isolation.py (local RSA keypair standing in for
Supabase's signing key, JWKS cache primed directly), this creates two real
users via the Supabase Auth Admin API, signs them in for real, and lets the
running FastAPI app fetch the project's real JWKS over the network. Every
layer is real: Supabase Auth -> JWKS -> backend.core.auth -> FastAPI ->
SQLAlchemy -> hosted PostgreSQL RLS.

Test users are prefixed ``phase25b-cloud-e2e-`` and deleted (which cascades
their conversations via the FK) at the end of the run, success or failure.

Usage - reads SUPABASE_URL / SUPABASE_PUBLISHABLE_KEY / SUPABASE_SECRET_KEY
/ DATABASE_URL / DATABASE_MIGRATION_URL from the environment (source .env
first). Must already be migrated to 0004.

    python -m backend.scripts.verify_cloud_e2e
"""
import asyncio
import os
import sys
import uuid

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import httpx  # noqa: E402

SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
PUBLISHABLE_KEY = os.environ["SUPABASE_PUBLISHABLE_KEY"]
SECRET_KEY = os.environ["SUPABASE_SECRET_KEY"]
TEST_PASSWORD = "Phase25b-CloudE2E-" + uuid.uuid4().hex  # nosec B105 - random, throwaway test credential


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


def main() -> int:
    from fastapi.testclient import TestClient

    from backend.main import app

    run_id = uuid.uuid4().hex[:8]
    email_a = f"phase25b-cloud-e2e-a-{run_id}@example.test"
    email_b = f"phase25b-cloud-e2e-b-{run_id}@example.test"
    user_ids: list[str] = []
    checks: list[tuple[str, bool]] = []

    try:
        user_a_id = create_user(email_a)
        user_ids.append(user_a_id)
        user_b_id = create_user(email_b)
        user_ids.append(user_b_id)

        # Real GoTrue tokens - forces a real network JWKS fetch by the app.
        token_a = sign_in(email_a)
        token_b = sign_in(email_b)

        with TestClient(app) as client:
            headers_a = {"Authorization": f"Bearer {token_a}"}
            headers_b = {"Authorization": f"Bearer {token_b}"}

            no_token = client.get("/api/chatbot/conversations")
            checks.append(("no token -> 401", no_token.status_code == 401))

            created = client.post(
                "/api/chatbot/conversations",
                json={"title": f"phase25b-cloud-e2e-{run_id}"},
                headers=headers_a,
            )
            checks.append(("A creates a conversation -> 201", created.status_code == 201))
            conv_id = created.json().get("id")

            own = client.get(f"/api/chatbot/conversations/{conv_id}", headers=headers_a)
            checks.append(("A reads A's own conversation -> 200", own.status_code == 200))

            cross = client.get(f"/api/chatbot/conversations/{conv_id}", headers=headers_b)
            checks.append(("B reads A's conversation -> 404", cross.status_code == 404))

            cross_delete = client.delete(f"/api/chatbot/conversations/{conv_id}", headers=headers_b)
            checks.append(("B deletes A's conversation -> 404", cross_delete.status_code == 404))

            still_there = client.get(f"/api/chatbot/conversations/{conv_id}", headers=headers_a)
            checks.append((
                "A's conversation survives B's delete attempt",
                still_there.status_code == 200,
            ))

            b_list = client.get("/api/chatbot/conversations", headers=headers_b)
            b_titles = {item["title"] for item in b_list.json()["items"]}
            checks.append((
                "B's conversation list excludes A's conversation",
                f"phase25b-cloud-e2e-{run_id}" not in b_titles,
            ))

            # Real cleanup through the API itself, as A.
            cleanup = client.delete(f"/api/chatbot/conversations/{conv_id}", headers=headers_a)
            checks.append(("A cleans up her own conversation -> 204", cleanup.status_code == 204))

    finally:
        for uid in user_ids:
            delete_user(uid)

    all_pass = True
    for name, ok in checks:
        print(f"{'PASS' if ok else 'FAIL'}: {name}")
        all_pass = all_pass and ok
    print(f"Test users created and deleted: {len(user_ids)}")
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
