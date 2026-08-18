"""Live proof that RLS enforces along the REAL request path:

    real Bearer JWT -> backend.core.auth (real crypto verification)
    -> FastAPI dependency injection (get_current_user, get_rls_db)
    -> real SQLAlchemy AsyncSession -> real PostgreSQL RLS policies

Nothing in this codebase's own layers is mocked or overridden - not
get_current_user, not get_db/get_rls_db, not the FastAPI app. The only
thing primed directly (not fetched over HTTPS) is the JWKS document that
would normally come from Supabase - a locally generated RSA keypair
stands in for Supabase's own signing key, exactly as in
backend/tests/test_auth.py, so no real Supabase project is required to
prove the mechanism.

Sets environment variables and only THEN imports backend.main - Settings
and the SQLAlchemy engine are process-wide lru_cache singletons, so this
must run as its own process, never inside the shared pytest session.

Usage::

    python -m backend.scripts.verify_http_rls_isolation "postgresql+psycopg://user:pass@host:port/db"
"""
import asyncio
import os
import sys
import time
import uuid

if sys.platform == "win32":
    # psycopg's async driver needs a selector event loop; Windows defaults
    # to ProactorEventLoop, which it cannot use. Docker/Linux (production
    # and CI) are unaffected - this is a local-verification-only script.
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

if len(sys.argv) < 2:
    print("usage: verify_http_rls_isolation.py <postgresql+psycopg DSN, already migrated to 0004>")
    sys.exit(2)

DSN = sys.argv[1]
FAKE_SUPABASE_URL = "https://phase25b-completion-check.supabase.co"

os.environ["APP_ENV"] = "local"  # TLS enforcement is orthogonal to Auth; this DB has no TLS.
os.environ["DATABASE_URL"] = DSN
os.environ["DATABASE_MIGRATION_URL"] = DSN
os.environ["DATABASE_SSL_MODE"] = ""
os.environ["SUPABASE_URL"] = FAKE_SUPABASE_URL
os.environ["CORS_ORIGINS"] = "http://testserver"

import jwt as pyjwt  # noqa: E402
import psycopg  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from backend.core import auth as auth_module  # noqa: E402

ISSUER = f"{FAKE_SUPABASE_URL}/auth/v1"
KID = "verify-http-rls-key"


def _mint_token(private_key, user_id: uuid.UUID) -> str:
    now = int(time.time())
    claims = {
        "sub": str(user_id),
        "aud": "authenticated",
        "iss": ISSUER,
        "role": "authenticated",
        "iat": now,
        "exp": now + 3600,
    }
    return pyjwt.encode(claims, private_key, algorithm="RS256", headers={"kid": KID})


def main() -> int:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_jwk = pyjwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key(), as_dict=False)

    # Prime the JWKS cache directly instead of serving real HTTPS - the
    # verification code path (backend/core/auth.py) runs completely for
    # real; only the external network fetch is stood in for.
    from jwt.algorithms import RSAAlgorithm

    auth_module._reset_jwks_cache_for_tests()
    auth_module._jwks_cache._keys = {KID: RSAAlgorithm.from_jwk(public_jwk)}
    auth_module._jwks_cache._fetched_at = time.monotonic()
    auth_module._jwks_cache._jwks_url = f"{FAKE_SUPABASE_URL}/auth/v1/.well-known/jwks.json"

    user_a = uuid.uuid4()
    user_b = uuid.uuid4()
    admin = psycopg.connect(DSN.replace("postgresql+psycopg://", "postgresql://"), autocommit=True)
    with admin.cursor() as cur:
        cur.execute("INSERT INTO auth.users (id) VALUES (%s), (%s)", (str(user_a), str(user_b)))
    admin.close()

    token_a = _mint_token(private_key, user_a)
    token_b = _mint_token(private_key, user_b)

    from backend.main import app  # import AFTER env vars are set

    checks: list[tuple[str, bool]] = []
    with TestClient(app) as client:
        headers_a = {"Authorization": f"Bearer {token_a}"}
        headers_b = {"Authorization": f"Bearer {token_b}"}

        no_token = client.get("/api/chatbot/conversations")
        checks.append(("no token -> 401", no_token.status_code == 401))

        bad_token = client.get(
            "/api/chatbot/conversations", headers={"Authorization": "Bearer not-a-real-jwt"}
        )
        checks.append(("garbage token -> 401", bad_token.status_code == 401))

        created = client.post(
            "/api/chatbot/conversations", json={"title": "A's real conversation"}, headers=headers_a
        )
        checks.append(("A creates a conversation -> 201", created.status_code == 201))
        conv_id = created.json().get("id")

        own = client.get(f"/api/chatbot/conversations/{conv_id}", headers=headers_a)
        checks.append(("A reads A's own conversation -> 200", own.status_code == 200))

        cross = client.get(f"/api/chatbot/conversations/{conv_id}", headers=headers_b)
        checks.append((
            "B reads A's conversation -> 404 (not 403 - no id probing)",
            cross.status_code == 404,
        ))

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
            "A's real conversation" not in b_titles,
        ))

    all_pass = True
    for name, ok in checks:
        print(f"{'PASS' if ok else 'FAIL'}: {name}")
        all_pass = all_pass and ok
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
