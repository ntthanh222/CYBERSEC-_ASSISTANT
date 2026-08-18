"""Admin-facing RBAC management: list/role-change/activation, audit trail.

Every mutation here enforces one invariant above all else: the system must
never end up with zero active admins (a permanent lockout with no path back
in without direct database access). Both ``change_role`` and ``set_active``
check this *inside* the same transaction that would otherwise violate it.
"""
import uuid
from typing import Any, Optional, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.audit import log_audit_event
from backend.core.context import get_request_id
from backend.core.exceptions import (
    AuthorizationError,
    ConflictError,
    InvalidRequestError,
    NotFoundError,
)
from backend.database.models.rbac import ROLE_RANK, ROLES
from backend.repositories.rbac import RbacRepository
from backend.services.notifications import NotificationService


class RbacService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = RbacRepository(session)

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
    ) -> tuple[Sequence[dict], int]:
        return await self._repo.list_users(
            page=page,
            page_size=page_size,
            search=search,
            role=role,
            status=status,
            source=source,
            hide_test_accounts=hide_test_accounts,
        )

    async def list_audit_log(
        self,
        *,
        page: int,
        page_size: int,
        search: Optional[str] = None,
        action: Optional[str] = None,
        actor_user_id: Optional[uuid.UUID] = None,
        target_user_id: Optional[uuid.UUID] = None,
    ):
        return await self._repo.list_audit_log(
            page=page,
            page_size=page_size,
            search=search,
            action=action,
            actor_user_id=actor_user_id,
            target_user_id=target_user_id,
        )

    async def change_role(
        self,
        target_user_id: uuid.UUID,
        *,
        new_role: str,
        actor_user_id: uuid.UUID,
        actor_role: str,
        actor: Optional[str],
    ) -> dict[str, Any]:
        if new_role not in ROLES:
            raise InvalidRequestError(f"role phải là một trong các giá trị {sorted(ROLES)}.")

        target = await self._repo.get_role(target_user_id)
        if target is None:
            raise NotFoundError("Không tìm thấy người dùng.")

        # Only a super_admin may create or reassign a super_admin account -
        # a plain admin can never manage the super_admin tier, including
        # its own account (self-promotion is impossible as a corollary,
        # but the explicit check below gives a clearer error message).
        managing_super_admin_tier = new_role == "super_admin" or target.role == "super_admin"
        if managing_super_admin_tier and actor_role != "super_admin":
            raise AuthorizationError(
                "Chỉ super administrator mới có thể quản lý các tài khoản super administrator."
            )
        if target_user_id == actor_user_id and new_role == "super_admin":
            raise AuthorizationError("Bạn không thể tự thăng cấp tài khoản của mình lên super administrator.")

        if target.role == "super_admin" and new_role != "super_admin" and target.is_active:
            if await self._repo.count_active_by_role("super_admin") <= 1:
                raise ConflictError(
                    "Không thể đổi vai trò tài khoản này: đây là super administrator đang hoạt động duy nhất."
                )
        if (
            ROLE_RANK[target.role] >= ROLE_RANK["admin"]
            and ROLE_RANK[new_role] < ROLE_RANK["admin"]
            and target.is_active
        ):
            if await self._repo.count_active_admins() <= 1:
                raise ConflictError(
                    "Không thể đổi vai trò tài khoản này: đây là administrator đang hoạt động duy nhất."
                )

        previous_role = target.role
        row = await self._repo.set_role(target_user_id, role=new_role)
        await self._repo.record_audit(
            actor_user_id=actor_user_id,
            action="role_changed",
            target_user_id=target_user_id,
            metadata={"from": previous_role, "to": new_role, "request_id": get_request_id()},
        )
        await self._session.commit()

        log_audit_event(
            event_type="rbac",
            action="role_changed",
            resource=f"user:{target_user_id}",
            result="success",
            actor=actor,
            metadata={"from": previous_role, "to": new_role},
        )
        await NotificationService(self._session).notify_users(
            [target_user_id],
            title="Vai trò tài khoản của bạn đã thay đổi",
            body=f"Vai trò của bạn đã đổi từ {previous_role} sang {new_role}.",
            category="system",
            severity="warning" if ROLE_RANK[new_role] < ROLE_RANK[previous_role] else "info",
            source_ref=f"user:{target_user_id}",
            actor=actor,
        )
        return {"user_id": target_user_id, "role": row.role, "is_active": row.is_active}

    async def set_active(
        self,
        target_user_id: uuid.UUID,
        *,
        is_active: bool,
        actor_user_id: uuid.UUID,
        actor_role: str,
        actor: Optional[str],
    ) -> dict[str, Any]:
        target = await self._repo.get_role(target_user_id)
        if target is None:
            raise NotFoundError("Không tìm thấy người dùng.")

        if target.role == "super_admin" and actor_role != "super_admin":
            raise AuthorizationError(
                "Chỉ super administrator mới có thể quản lý các tài khoản super administrator."
            )

        if not is_active and target.is_active:
            active_super_admins = await self._repo.count_active_by_role("super_admin")
            if target.role == "super_admin" and active_super_admins <= 1:
                raise ConflictError(
                    "Không thể vô hiệu hóa tài khoản này: đây là super administrator đang hoạt động duy nhất."
                )
            is_admin_tier = ROLE_RANK[target.role] >= ROLE_RANK["admin"]
            if is_admin_tier and await self._repo.count_active_admins() <= 1:
                raise ConflictError(
                    "Không thể vô hiệu hóa tài khoản này: đây là administrator đang hoạt động duy nhất."
                )

        row = await self._repo.set_active(target_user_id, is_active=is_active)
        await self._repo.record_audit(
            actor_user_id=actor_user_id,
            action="user_activated" if is_active else "user_deactivated",
            target_user_id=target_user_id,
            metadata={"request_id": get_request_id()},
        )
        await self._session.commit()

        log_audit_event(
            event_type="rbac",
            action="user_activated" if is_active else "user_deactivated",
            resource=f"user:{target_user_id}",
            result="success",
            actor=actor,
        )
        await NotificationService(self._session).notify_users(
            [target_user_id],
            title="Tài khoản của bạn đã được kích hoạt lại" if is_active else "Tài khoản của bạn đã bị vô hiệu hóa",
            body="",
            category="system",
            severity="info" if is_active else "warning",
            source_ref=f"user:{target_user_id}",
            actor=actor,
        )
        return {"user_id": target_user_id, "role": row.role, "is_active": row.is_active}
