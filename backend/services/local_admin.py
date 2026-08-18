"""Local Mode admin: first-run bootstrap and password login.

Hard-scoped to ``APP_ENV=local`` at the route layer (see
``backend/api/local_admin.py``), exactly like ``backend/api/local_auth.py``'s
demo session - this is Docker-local convenience, never a hosted-auth
replacement. The app-level role/active state this mints into
lives in ``user_roles`` (see :mod:`backend.core.authorization`), decoupled
from how the identity was created.
"""
from __future__ import annotations

import re

from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from backend.api.local_auth import create_auth_user, mint_local_session
from backend.config.settings import Settings
from backend.core.audit import log_audit_event
from backend.core.exceptions import AuthenticationError, ConflictError, InvalidRequestError
from backend.core.password_hash import (
    MAX_PASSWORD_LENGTH,
    MIN_PASSWORD_LENGTH,
    hash_password,
    needs_rehash,
    verify_password,
)
from backend.core.timeutils import utcnow
from backend.repositories.rbac import RbacRepository
from backend.schemas.local_auth import LocalSessionResponse

#: Deliberately conservative: letters, digits, dot/underscore/hyphen. Blocks
#: anything that could be confused for an email address or contain control
#: characters, without being so strict it rejects a reasonable admin name.
_USERNAME_RE = re.compile(r"^[A-Za-z0-9._-]{3,64}$")


def _validate_username(username: str) -> str:
    cleaned = (username or "").strip()
    if not _USERNAME_RE.match(cleaned):
        raise InvalidRequestError(
            "Tên đăng nhập phải dài 3-64 ký tự: chỉ gồm chữ cái, chữ số, '.', '_' hoặc '-'."
        )
    return cleaned


def _validate_password(password: str) -> None:
    if len(password or "") < MIN_PASSWORD_LENGTH:
        raise InvalidRequestError(f"Mật khẩu phải có ít nhất {MIN_PASSWORD_LENGTH} ký tự.")
    if len(password or "") > MAX_PASSWORD_LENGTH:
        raise InvalidRequestError(f"Mật khẩu tối đa {MAX_PASSWORD_LENGTH} ký tự.")


class LocalAdminAuthService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = RbacRepository(session)

    async def setup_status(self) -> bool:
        return await self._repo.any_admin_exists()

    async def setup(
        self, *, username: str, password: str, settings: Settings
    ) -> LocalSessionResponse:
        """First-run admin creation. Raises :class:`ConflictError` (409) if
        an active admin already exists - this is a one-time bootstrap, not a
        general "create another admin" endpoint (that's
        ``PATCH /api/admin/users/{id}/role`` once one admin already exists).
        """
        if await self._repo.any_admin_exists():
            raise ConflictError("Đã tồn tại tài khoản quản trị viên.")

        clean_username = _validate_username(username)
        _validate_password(password)

        existing = await self._repo.get_credential_by_username(clean_username)
        if existing is not None:
            raise ConflictError("Tên đăng nhập này đã được sử dụng.")

        user_id = await create_auth_user(
            self._session, email=f"{clean_username}@local.admin.invalid"
        )
        await self._repo.set_role(user_id, role="admin")
        await self._repo.create_local_admin_credential(
            user_id=user_id,
            username=clean_username,
            password_hash=await run_in_threadpool(hash_password, password),
        )
        await self._repo.record_audit(
            actor_user_id=user_id, action="admin_bootstrap", target_user_id=user_id
        )
        await self._session.commit()

        log_audit_event(
            event_type="rbac",
            action="admin_bootstrap",
            resource=f"user:{user_id}",
            result="success",
        )
        return mint_local_session(
            user_id=user_id, email=f"{clean_username}@local.admin.invalid", settings=settings
        )

    async def login(
        self, *, username: str, password: str, settings: Settings
    ) -> LocalSessionResponse:
        clean_username = (username or "").strip()
        credential = await self._repo.get_credential_by_username(clean_username)

        # Always run a hash verify, even for an unknown username, against a
        # fixed dummy hash - so a timing difference between "unknown
        # username" and "wrong password" cannot be used to enumerate valid
        # admin usernames.
        candidate_hash = credential.password_hash if credential else _DUMMY_HASH
        password_ok = await run_in_threadpool(verify_password, password, candidate_hash)

        role_row = await self._repo.get_role(credential.user_id) if credential else None
        account_active = bool(role_row and role_row.is_active)

        if credential is None or not password_ok or not account_active:
            log_audit_event(
                event_type="rbac",
                action="admin_login_failed",
                resource=f"username:{clean_username}",
                result="failure",
            )
            raise AuthenticationError("Tên đăng nhập hoặc mật khẩu không đúng.")

        if needs_rehash(credential.password_hash):
            credential.password_hash = await run_in_threadpool(hash_password, password)

        await self._repo.touch_last_login(credential.user_id, when=utcnow())
        await self._repo.record_audit(
            actor_user_id=credential.user_id,
            action="admin_login",
            target_user_id=credential.user_id,
        )
        await self._session.commit()

        log_audit_event(
            event_type="rbac",
            action="admin_login",
            resource=f"user:{credential.user_id}",
            result="success",
        )
        return mint_local_session(
            user_id=credential.user_id,
            email=f"{clean_username}@local.admin.invalid",
            settings=settings,
        )

#: A real Argon2id hash of a value nobody can type (never used to grant
#: access) - exists purely so an unknown-username login takes the same code
#: path/latency as a known-username wrong-password login.
_DUMMY_HASH = hash_password("this-hash-is-never-a-valid-password-9f3b2c7e")
