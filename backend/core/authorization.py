"""App-level role authorization, layered on top of identity verification.

``backend.core.auth.get_current_user`` only proves *who* the caller is (a
verified JWT). It never proves *what they may do* - the JWT's own ``role``
claim is the Postgres RLS role (always ``authenticated``), not an app role,
and is never trusted for authorization. This module is the single place that
looks up the real, current role/active-state from the database on every
request, so a role change or deactivation takes effect immediately rather
than only after a token expires.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Optional

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.auth import AuthenticatedUser, get_current_user
from backend.core.exceptions import AuthenticationError, AuthorizationError
from backend.database.models.rbac import ROLE_RANK
from backend.database.session import get_db
from backend.repositories.rbac import RbacRepository


@dataclass(frozen=True)
class AppUser:
    """The caller's verified identity plus its DB-backed app role/state."""

    id: uuid.UUID
    email: Optional[str]
    role: str
    is_active: bool


async def get_app_user(
    user: AuthenticatedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> AppUser:
    """The caller's app-level role, read fresh from ``user_roles`` every call.

    A caller with no row yet (every identity predating this feature) is
    lazily assigned the ``user`` role here rather than failing - this must
    never break an existing Local Mode or hosted-Supabase session.
    """
    repo = RbacRepository(session)
    role_row = await repo.ensure_role(user.id)
    await session.commit()

    if not role_row.is_active:
        # Fail closed: a deactivated account's token stops working
        # immediately, indistinguishable from "not authenticated" to the
        # caller - it must not learn *why* access was refused.
        raise AuthenticationError()

    email = user.claims.get("email") if isinstance(user.claims, dict) else None
    return AppUser(id=user.id, email=email, role=role_row.role, is_active=role_row.is_active)


def _require_min_role(minimum: str, *, message: str):
    """Build a dependency that accepts ``minimum`` or anything ranked above it.

    A higher-ranked role (e.g. ``super_admin``) always satisfies a
    lower-ranked requirement (e.g. ``require_admin``) - the hierarchy is
    strictly additive, never a set of disjoint permissions.
    """

    async def _dependency(app_user: AppUser = Depends(get_app_user)) -> AppUser:
        if ROLE_RANK.get(app_user.role, -1) < ROLE_RANK[minimum]:
            raise AuthorizationError(message)
        return app_user

    return _dependency


require_developer = _require_min_role(
    "developer", message="Developer privileges are required for this action."
)
require_analyst = _require_min_role(
    "security_analyst", message="Security analyst privileges are required for this action."
)
require_admin = _require_min_role(
    "admin", message="Administrator privileges are required for this action."
)
require_super_admin = _require_min_role(
    "super_admin", message="Super administrator privileges are required for this action."
)
