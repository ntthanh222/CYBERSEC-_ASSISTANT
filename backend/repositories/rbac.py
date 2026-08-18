"""Local RBAC persistence: roles, local admin credentials, admin audit log."""
import uuid
from typing import Any, Optional, Sequence

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database.models.rbac import (
    ADMIN_TIER_ROLES,
    AdminAuditLog,
    LocalAdminCredential,
    UserRole,
)


class RbacRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_role(self, user_id: uuid.UUID) -> Optional[UserRole]:
        return await self._session.scalar(
            sa.select(UserRole).where(UserRole.user_id == user_id)
        )

    async def ensure_role(self, user_id: uuid.UUID, *, default_role: str = "user") -> UserRole:
        """Return the existing role row, or create one defaulting to ``default_role``.

        Every identity this app has ever seen (hosted-Supabase or the local
        demo session) predates this table, so a missing row means "never
        assigned a role yet", not "unauthorized" - it is lazily created here
        rather than at identity-creation time so no existing session breaks.
        """
        existing = await self.get_role(user_id)
        if existing is not None:
            return existing
        role = UserRole(user_id=user_id, role=default_role, is_active=True)
        self._session.add(role)
        await self._session.flush()
        return role

    async def list_active_admin_tier_user_ids(self) -> Sequence[uuid.UUID]:
        """Every active admin/super_admin - used to fan out a notification
        (e.g. a new critical alert/incident) to whoever has oversight
        responsibility, since this app has no per-user subscription model."""
        rows = await self._session.scalars(
            sa.select(UserRole.user_id).where(
                UserRole.role.in_(ADMIN_TIER_ROLES), UserRole.is_active.is_(True)
            )
        )
        return list(rows)

    async def any_admin_exists(self) -> bool:
        result = await self._session.scalar(
            sa.select(sa.func.count())
            .select_from(UserRole)
            .where(UserRole.role.in_(ADMIN_TIER_ROLES), UserRole.is_active.is_(True))
        )
        return int(result or 0) > 0

    async def count_active_admins(self) -> int:
        """Active accounts in the administrator tier (``admin`` or ``super_admin``).

        This is the invariant the system must never hit zero on - it would
        be a permanent lockout from ``/api/admin/*`` with no path back in
        without direct database access.
        """
        result = await self._session.scalar(
            sa.select(sa.func.count())
            .select_from(UserRole)
            .where(UserRole.role.in_(ADMIN_TIER_ROLES), UserRole.is_active.is_(True))
        )
        return int(result or 0)

    async def count_active_by_role(self, role: str) -> int:
        result = await self._session.scalar(
            sa.select(sa.func.count())
            .select_from(UserRole)
            .where(UserRole.role == role, UserRole.is_active.is_(True))
        )
        return int(result or 0)

    async def set_role(self, user_id: uuid.UUID, *, role: str) -> UserRole:
        row = await self.ensure_role(user_id)
        row.role = role
        await self._session.flush()
        return row

    async def set_active(self, user_id: uuid.UUID, *, is_active: bool) -> UserRole:
        row = await self.ensure_role(user_id)
        row.is_active = is_active
        await self._session.flush()
        return row

    async def create_local_admin_credential(
        self, *, user_id: uuid.UUID, username: str, password_hash: str
    ) -> LocalAdminCredential:
        credential = LocalAdminCredential(
            user_id=user_id, username=username, password_hash=password_hash
        )
        self._session.add(credential)
        await self._session.flush()
        return credential

    async def get_credential_by_username(self, username: str) -> Optional[LocalAdminCredential]:
        return await self._session.scalar(
            sa.select(LocalAdminCredential).where(LocalAdminCredential.username == username)
        )

    async def get_credential_by_user_id(
        self, user_id: uuid.UUID
    ) -> Optional[LocalAdminCredential]:
        return await self._session.scalar(
            sa.select(LocalAdminCredential).where(LocalAdminCredential.user_id == user_id)
        )

    async def touch_last_login(self, user_id: uuid.UUID, *, when: Any) -> None:
        credential = await self.get_credential_by_user_id(user_id)
        if credential is not None:
            credential.last_login_at = when
            await self._session.flush()

    async def list_users(
        self,
        *,
        page: int,
        page_size: int,
        search: Optional[str] = None,
        role: Optional[str] = None,
        status: Optional[str] = None,
        source: Optional[str] = None,
        hide_test_accounts: bool = True,
    ) -> tuple[Sequence[dict[str, Any]], int]:
        """Every identity that has a role row, joined with its email and
        (if any) local username - real Postgres only, since ``auth.users``
        is a raw-SQL schema/shim (see ``backend/api/local_auth.py``) never
        modeled in the ORM and therefore absent from the SQLite unit-test
        schema. Mirrors the existing "positive path needs real Postgres,
        exercised by the Docker/Playwright acceptance pass" convention
        `backend/tests/test_local_auth.py` already documents.
        """
        filters = []
        params: dict[str, Any] = {"offset": (page - 1) * page_size, "limit": page_size}
        if search:
            filters.append(
                "(LOWER(COALESCE(u.email, '')) LIKE :search "
                "OR LOWER(COALESCE(lac.username, '')) LIKE :search "
                "OR CAST(ur.user_id AS TEXT) LIKE :search)"
            )
            params["search"] = f"%{search.lower()}%"
        if role:
            filters.append("ur.role = :role")
            params["role"] = role
        if status == "active":
            filters.append("ur.is_active IS TRUE")
        elif status == "disabled":
            filters.append("ur.is_active IS FALSE")
        if source:
            filters.append(
                """
                CASE
                    WHEN COALESCE(u.email, '') LIKE '%@example.test'
                         OR COALESCE(u.email, '') LIKE '%.example.test' THEN 'test'
                    WHEN COALESCE(lac.username, '') LIKE 'demo_%'
                         OR COALESCE(u.email, '') LIKE '%.demo.invalid' THEN 'demo'
                    WHEN lac.username IS NOT NULL THEN 'local'
                    ELSE 'hosted'
                END = :source
                """
            )
            params["source"] = source
        if hide_test_accounts:
            filters.append(
                "COALESCE(u.email, '') NOT LIKE '%@example.test' "
                "AND COALESCE(u.email, '') NOT LIKE '%.example.test'"
            )
        where_sql = f"WHERE {' AND '.join(filters)}" if filters else ""
        # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
        # Justification: where_sql is built safely from fixed server-side strings; all dynamic data is passed via bound parameters.
        count_query = (
            "SELECT COUNT(*) AS total\n"  # nosec B608 -- SQL string is built safely without untrusted input directly interpolated.
            "FROM user_roles ur\n"
            "JOIN auth.users u ON u.id = ur.user_id\n"
            "LEFT JOIN local_admin_credentials lac ON lac.user_id = ur.user_id\n"
            f"{where_sql}"
        )  # nosec B608
        # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text -- where_sql is built from fixed strings and bound params only.
        count_row = await self._session.execute(sa.text(count_query), params)

        total = count_row.scalar()

        # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
        # Justification: where_sql is built safely from fixed server-side strings; all dynamic data is passed via bound parameters.
        data_query = (
            "SELECT\n"  # nosec B608 -- SQL string is built safely without untrusted input directly interpolated.
            "    ur.user_id AS user_id,\n"
            "    ur.role AS role,\n"
            "    ur.is_active AS is_active,\n"
            "    ur.created_at AS created_at,\n"
            "    ur.updated_at AS updated_at,\n"
            "    lac.username AS username,\n"
            "    lac.last_login_at AS last_login_at,\n"
            "    u.email AS email,\n"
            "    CASE\n"
            "        WHEN COALESCE(u.email, '') LIKE '%@example.test'\n"
            "             OR COALESCE(u.email, '') LIKE '%.example.test' THEN 'test'\n"
            "        WHEN COALESCE(lac.username, '') LIKE 'demo_%'\n"
            "             OR COALESCE(u.email, '') LIKE '%.demo.invalid' THEN 'demo'\n"
            "        WHEN lac.username IS NOT NULL THEN 'local'\n"
            "        ELSE 'hosted'\n"
            "    END AS source,\n"
            "    (\n"
            "        COALESCE(u.email, '') LIKE '%@example.test'\n"
            "        OR COALESCE(u.email, '') LIKE '%.example.test'\n"
            "    ) AS is_test_account\n"
            "FROM user_roles ur\n"
            "JOIN auth.users u ON u.id = ur.user_id\n"
            "LEFT JOIN local_admin_credentials lac ON lac.user_id = ur.user_id\n"
            f"{where_sql}\n"
            "ORDER BY ur.created_at DESC\n"
            "OFFSET :offset LIMIT :limit"
        )  # nosec B608
        # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text -- where_sql is built from fixed strings and bound params only.
        rows = await self._session.execute(sa.text(data_query), params)
        items = [dict(row._mapping) for row in rows.all()]
        return items, int(total or 0)

    async def record_audit(
        self,
        *,
        actor_user_id: Optional[uuid.UUID],
        action: str,
        target_user_id: Optional[uuid.UUID] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> AdminAuditLog:
        entry = AdminAuditLog(
            actor_user_id=actor_user_id,
            action=action,
            target_user_id=target_user_id,
            meta=metadata,
        )
        self._session.add(entry)
        await self._session.flush()
        return entry

    async def list_audit_log(
        self,
        *,
        page: int,
        page_size: int,
        search: Optional[str] = None,
        action: Optional[str] = None,
        actor_user_id: Optional[uuid.UUID] = None,
        target_user_id: Optional[uuid.UUID] = None,
    ) -> tuple[Sequence[AdminAuditLog], int]:
        conditions = []
        if search:
            pattern = f"%{search.lower()}%"
            conditions.append(
                sa.or_(
                    sa.func.lower(AdminAuditLog.action).like(pattern),
                    sa.cast(AdminAuditLog.actor_user_id, sa.String).like(pattern),
                    sa.cast(AdminAuditLog.target_user_id, sa.String).like(pattern),
                )
            )
        if action:
            conditions.append(AdminAuditLog.action == action)
        if actor_user_id:
            conditions.append(AdminAuditLog.actor_user_id == actor_user_id)
        if target_user_id:
            conditions.append(AdminAuditLog.target_user_id == target_user_id)
        total_stmt = sa.select(sa.func.count()).select_from(AdminAuditLog)
        list_stmt = sa.select(AdminAuditLog)
        if conditions:
            total_stmt = total_stmt.where(*conditions)
            list_stmt = list_stmt.where(*conditions)
        total = await self._session.scalar(total_stmt)
        rows = await self._session.scalars(
            list_stmt
            .order_by(AdminAuditLog.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(rows), int(total or 0)
