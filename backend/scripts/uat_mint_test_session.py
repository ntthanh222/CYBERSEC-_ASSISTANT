"""Mint a test-safe Supabase-shaped session for Phase 2.7A Playwright UAT.

Runs inside the backend container against its own configured Postgres and
``SUPABASE_JWT_SECRET`` (see backend/tests/test_auth.py
TestVerifyAccessTokenLegacyHs256). Creates a local ``auth.users`` shim row
(see migration 0004) for the requested email if one does not already exist,
mints an HS256 access token the running backend's own
``verify_access_token`` will accept, and prints a single JSON object to
stdout: ``{"user_id": ..., "email": ..., "access_token": ...,
"expires_at": ...}``.

Playwright drives the UI as an authenticated user by writing this into
localStorage in the same shape the Supabase JS SDK persists after a real
login - no live GoTrue needed. Never used outside this disposable UAT
worktree; the JWT secret is a fixed local-only placeholder, not a real
credential.
"""
import argparse
import asyncio
import json
import sys
import time
import uuid

import jwt
from sqlalchemy import text

from backend.config.settings import get_settings
from backend.core.auth import EXPECTED_AUDIENCE
from backend.database.session import get_sessionmaker


async def _ensure_user(email: str) -> uuid.UUID:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        existing = await session.execute(
            text("SELECT id FROM auth.users WHERE email = :email"), {"email": email}
        )
        row = existing.first()
        if row is not None:
            return uuid.UUID(str(row[0]))

        user_id = uuid.uuid4()
        await session.execute(
            text("INSERT INTO auth.users (id, email) VALUES (:id, :email)"),
            {"id": str(user_id), "email": email},
        )
        await session.commit()
        return user_id


def _mint_token(user_id: uuid.UUID, email: str) -> tuple[str, int]:
    settings = get_settings()
    if not settings.supabase_jwt_secret:
        print("SUPABASE_JWT_SECRET not configured", file=sys.stderr)
        raise SystemExit(1)

    now = int(time.time())
    expires_at = now + 3600
    claims = {
        "sub": str(user_id),
        "email": email,
        "aud": EXPECTED_AUDIENCE,
        "role": EXPECTED_AUDIENCE,
        "iss": settings.supabase_issuer,
        "iat": now,
        "exp": expires_at,
    }
    token = jwt.encode(claims, settings.supabase_jwt_secret, algorithm="HS256")
    return token, expires_at


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--email", required=True)
    args = parser.parse_args()

    user_id = await _ensure_user(args.email)
    token, expires_at = _mint_token(user_id, args.email)

    print(
        json.dumps(
            {
                "user_id": str(user_id),
                "email": args.email,
                "access_token": token,
                "expires_at": expires_at,
            }
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
