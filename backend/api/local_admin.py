"""Local Mode admin bootstrap and password login (APP_ENV=local only).

Every route 404s outside ``APP_ENV=local``, identically to
``backend/api/local_auth.py``'s demo session - this is Docker-local
convenience for administering the box, never a hosted-auth replacement.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config.settings import Settings, get_settings
from backend.core.exceptions import NotFoundError
from backend.core.rate_limit import rate_limit
from backend.database.session import get_db
from backend.schemas.local_auth import LocalSessionResponse
from backend.schemas.rbac import AdminLoginRequest, AdminSetupRequest, AdminSetupStatusResponse
from backend.services.local_admin import LocalAdminAuthService

router = APIRouter(prefix="/api/auth/local-admin", tags=["local-admin"])

# Unified Local Mode sign-in, one level up from /local-admin - any account
# created via the bootstrap/seed flow (demo_user, demo_analyst,
# demo_superadmin, or a hand-created admin) signs in here regardless of its
# role. Kept as a *second* router (not nested under the /local-admin prefix
# above) so the URL doesn't read as admin-only, matching the single-/login
# unification goal - the old /local-admin/login path below still works
# unchanged for any existing caller.
unified_login_router = APIRouter(prefix="/api/auth", tags=["local-auth"])

login_rate_limit = rate_limit(bucket="local_admin_login", limit=10, window_seconds=60)
unified_login_rate_limit = rate_limit(bucket="local_login", limit=10, window_seconds=60)


def _require_local(settings: Settings) -> None:
    if not settings.is_local:
        raise NotFoundError()


@router.get(
    "/setup-status",
    response_model=AdminSetupStatusResponse,
    summary="Whether a local administrator account already exists",
    responses={404: {"description": "Not available outside APP_ENV=local."}},
)
async def setup_status(
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_db),
) -> AdminSetupStatusResponse:
    _require_local(settings)
    service = LocalAdminAuthService(session)
    return AdminSetupStatusResponse(admin_exists=await service.setup_status())


@router.post(
    "/setup",
    response_model=LocalSessionResponse,
    status_code=201,
    summary="First-run local administrator setup",
    description=(
        "Creates the first local admin account with a caller-chosen "
        "username/password. Only works once - a second call returns 409 "
        "once any active admin exists."
    ),
    responses={
        404: {"description": "Not available outside APP_ENV=local."},
        409: {"description": "An administrator account already exists."},
        422: {"description": "Invalid username or password."},
    },
)
async def setup(
    payload: AdminSetupRequest,
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_db),
) -> LocalSessionResponse:
    _require_local(settings)
    service = LocalAdminAuthService(session)
    return await service.setup(
        username=payload.username, password=payload.password, settings=settings
    )


@router.post(
    "/login",
    response_model=LocalSessionResponse,
    summary="Local administrator login",
    responses={
        401: {"description": "Invalid username/password, or the account is deactivated."},
        404: {"description": "Not available outside APP_ENV=local."},
        429: {"description": "Too many login attempts."},
    },
    dependencies=[Depends(login_rate_limit)],
)
async def login(
    payload: AdminLoginRequest,
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_db),
) -> LocalSessionResponse:
    _require_local(settings)
    service = LocalAdminAuthService(session)
    return await service.login(
        username=payload.username, password=payload.password, settings=settings
    )


@unified_login_router.post(
    "/local-login",
    response_model=LocalSessionResponse,
    summary="Unified Local Mode sign-in (any role)",
    description=(
        "The single username/password sign-in for every Local Mode account - "
        "demo_user, demo_analyst, demo_superadmin, or a "
        "hand-created admin. The account's actual role (read fresh from the "
        "database, never from this request) decides what it can do after "
        "signing in - this endpoint itself has no notion of role."
    ),
    responses={
        401: {"description": "Invalid username/password, or the account is deactivated."},
        404: {"description": "Not available outside APP_ENV=local."},
        429: {"description": "Too many login attempts."},
    },
    dependencies=[Depends(unified_login_rate_limit)],
)
async def unified_login(
    payload: AdminLoginRequest,
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_db),
) -> LocalSessionResponse:
    _require_local(settings)
    service = LocalAdminAuthService(session)
    return await service.login(
        username=payload.username, password=payload.password, settings=settings
    )
