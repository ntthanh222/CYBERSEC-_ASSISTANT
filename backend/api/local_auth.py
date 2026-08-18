"""Docker-local-only demo session ("Local Mode") - not hosted auth.

Exists purely so `docker compose up -d --build` produces a usable app with
zero manual setup: no hosted Supabase project, no `.env`, no token-minting
script run by hand. It creates (or reuses) one fixed local demo user and
mints the same kind of backend-verifiable HS256 token
`backend/scripts/uat_mint_test_session.py` has always minted for UAT/E2E use
- this just puts that behind a button instead of a script.

Hard-disabled outside `APP_ENV=local`: every route 404s (not just refuses
the token) when `settings.is_local` is false, so no staging/production
deployment can ever expose it. See
`backend/tests/test_local_auth.py::test_local_session_404s_outside_local`.
"""
from __future__ import annotations

import time
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

import jwt

from backend.config.settings import Settings, get_settings
from backend.core.auth import EXPECTED_AUDIENCE
from backend.core.authorization import AppUser, get_app_user
from backend.core.exceptions import NotFoundError
from backend.core.timeutils import to_iso_utc, utcnow
from backend.database.session import get_db
from backend.schemas.local_auth import LocalSessionResponse, LocalSessionUser
from backend.schemas.rbac import MeResponse

router = APIRouter(prefix="/api/auth", tags=["local-auth"])

#: Fixed identity so repeated "enter local mode" clicks reuse one demo
#: account and its data, instead of accumulating throwaway users.
_LOCAL_DEMO_EMAIL = "local-demo@localhost"
_SESSION_LIFETIME_SECONDS = 3600 * 12


async def create_auth_user(session: AsyncSession, *, email: str) -> uuid.UUID:
    """Insert a brand-new identity into the local ``auth.users`` shim.

    Used for local admin account creation - distinct from
    :func:`_ensure_local_demo_user`, which reuses one fixed identity. The
    caller is responsible for uniqueness (the column has a UNIQUE
    constraint, so a duplicate raises an ``IntegrityError``).
    """
    user_id = uuid.uuid4()
    await session.execute(
        text("INSERT INTO auth.users (id, email) VALUES (:id, :email)"),
        {"id": str(user_id), "email": email},
    )
    return user_id


async def _ensure_local_demo_user(session: AsyncSession) -> uuid.UUID:
    existing = await session.execute(
        text("SELECT id FROM auth.users WHERE email = :email"), {"email": _LOCAL_DEMO_EMAIL}
    )
    row = existing.first()
    if row is not None:
        return uuid.UUID(str(row[0]))

    user_id = uuid.uuid4()
    await session.execute(
        text("INSERT INTO auth.users (id, email) VALUES (:id, :email)"),
        {"id": str(user_id), "email": _LOCAL_DEMO_EMAIL},
    )
    await session.commit()
    return user_id


def mint_local_session(
    *, user_id: uuid.UUID, email: str, settings: Settings
) -> LocalSessionResponse:
    """Mint the same kind of backend-verifiable HS256 session token for any
    local identity (the fixed demo user, or a local admin account). The RLS
    ``role`` claim is always ``authenticated`` regardless of app-level role -
    app authorization never reads this claim, see
    :mod:`backend.core.authorization`.
    """
    now = int(time.time())
    expires_at = now + _SESSION_LIFETIME_SECONDS
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
    return LocalSessionResponse(
        access_token=token,
        expires_at=expires_at,
        user=LocalSessionUser(id=str(user_id), email=email, created_at=to_iso_utc(utcnow())),
    )


@router.post(
    "/local-session",
    response_model=LocalSessionResponse,
    summary="Start a Docker-local demo session (APP_ENV=local only)",
    description=(
        "Creates or reuses one fixed local demo user and returns a "
        "backend-verifiable session, with no hosted Supabase project and no "
        "manual token minting. Returns 404 outside APP_ENV=local, and also "
        "404s whenever Local Mode is disallowed (see `Settings.allow_local_mode` "
        "- disallowed by default once Demo Mode seeding or "
        "DEMO_REQUIRE_GEMINI is active, so this anonymous zero-credential "
        "session can never sit alongside the seeded demo accounts). This "
        "anonymous identity is fixed and role-less: it can never carry "
        "analyst/admin/super_admin, unlike the credentialed `/local-login`."
    ),
    responses={
        404: {"description": "Not available outside APP_ENV=local, or Local Mode is disallowed."}
    },
)
async def start_local_session(
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_db),
) -> LocalSessionResponse:
    if not settings.is_local or not settings.allow_local_mode:
        raise NotFoundError()

    user_id = await _ensure_local_demo_user(session)
    return mint_local_session(user_id=user_id, email=_LOCAL_DEMO_EMAIL, settings=settings)


@router.get(
    "/me",
    response_model=MeResponse,
    summary="The caller's verified identity and DB-backed app role",
    description=(
        "Works for any verified session (Local Mode or hosted Supabase). "
        "`role` and `is_active` are read fresh from the database on every "
        "call - never trusted from the token itself. A deactivated account "
        "gets a 401 here, same as everywhere else."
    ),
    responses={401: {"description": "Missing/invalid token, or the account is deactivated."}},
)
async def get_me(app_user: AppUser = Depends(get_app_user)) -> MeResponse:
    return MeResponse(
        id=str(app_user.id), email=app_user.email, role=app_user.role, is_active=app_user.is_active
    )
