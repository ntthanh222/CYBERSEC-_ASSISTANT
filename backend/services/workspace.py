"""Workspace business logic - a thin layer over the repositories.

Mirrors ``backend.services.rbac.RbacService``'s "never leave the system
locked out" posture: removing or demoting the last ``owner`` member of a
workspace is blocked with a 409, exactly like RbacService blocks removing
the last active admin.
"""
import uuid
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.audit import log_audit_event
from backend.core.exceptions import ConflictError, InvalidRequestError, NotFoundError
from backend.database.models.workspace import WORKSPACE_ROLES, Workspace, WorkspaceMember
from backend.repositories.workspace import WorkspaceRepository
from backend.repositories.workspace_members import WorkspaceMemberRepository


class WorkspaceService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._workspaces = WorkspaceRepository(session)
        self._members = WorkspaceMemberRepository(session)

    async def create(
        self,
        *,
        name: str,
        description: Optional[str],
        created_by_user_id: uuid.UUID,
        actor: Optional[str],
    ) -> Workspace:
        workspace = await self._workspaces.create(
            name=name, description=description, created_by_user_id=created_by_user_id
        )
        await self._members.add(
            workspace_id=workspace.id, user_id=created_by_user_id, workspace_role="owner"
        )
        await self._session.commit()
        log_audit_event(
            event_type="workspace",
            action="workspace_created",
            resource=f"workspace:{workspace.id}",
            result="success",
            actor=actor,
        )
        return workspace

    async def get(self, workspace_id: uuid.UUID) -> Workspace:
        workspace = await self._workspaces.get(workspace_id)
        if workspace is None:
            raise NotFoundError("Workspace not found.")
        return workspace

    async def list(
        self, *, user_id: uuid.UUID, is_global_admin: bool, page: int, page_size: int
    ):
        return await self._workspaces.list_for_user(
            user_id=user_id, is_global_admin=is_global_admin, page=page, page_size=page_size
        )

    async def update(
        self,
        workspace_id: uuid.UUID,
        *,
        name: Optional[str],
        description: Optional[str],
        actor: Optional[str],
    ) -> Workspace:
        workspace = await self.get(workspace_id)
        workspace = await self._workspaces.update(workspace, name=name, description=description)
        await self._session.commit()
        log_audit_event(
            event_type="workspace",
            action="workspace_updated",
            resource=f"workspace:{workspace.id}",
            result="success",
            actor=actor,
        )
        return workspace

    async def list_members(self, workspace_id: uuid.UUID):
        return await self._members.list(workspace_id=workspace_id)

    async def add_member(
        self,
        workspace_id: uuid.UUID,
        *,
        user_id: uuid.UUID,
        workspace_role: str,
        actor: Optional[str],
    ) -> WorkspaceMember:
        if workspace_role not in WORKSPACE_ROLES:
            raise InvalidRequestError(f"workspace_role must be one of {sorted(WORKSPACE_ROLES)}.")
        await self.get(workspace_id)
        existing = await self._members.get(workspace_id=workspace_id, user_id=user_id)
        if existing is not None:
            raise ConflictError("This user is already a member of the workspace.")
        member = await self._members.add(
            workspace_id=workspace_id, user_id=user_id, workspace_role=workspace_role
        )
        await self._session.commit()
        log_audit_event(
            event_type="workspace",
            action="workspace_member_added",
            resource=f"workspace:{workspace_id}",
            result="success",
            actor=actor,
            metadata={"target_user_id": str(user_id), "workspace_role": workspace_role},
        )
        return member

    async def _ensure_not_last_owner(self, workspace_id: uuid.UUID, member: WorkspaceMember) -> None:
        """Blocks demoting/removing the last ``owner`` member of a workspace.

        Mirrors ``RbacService``'s last-active-admin lockout check exactly:
        the count is taken *before* the mutation, inside the same request, so
        the invariant can never be violated even under concurrent calls
        within one transaction.
        """
        if member.workspace_role != "owner":
            return
        if await self._members.count_by_role(workspace_id=workspace_id, role="owner") <= 1:
            raise ConflictError(
                "Cannot change this member: they are the workspace's only owner."
            )

    async def change_member_role(
        self,
        workspace_id: uuid.UUID,
        *,
        user_id: uuid.UUID,
        new_role: str,
        actor: Optional[str],
    ) -> WorkspaceMember:
        if new_role not in WORKSPACE_ROLES:
            raise InvalidRequestError(f"workspace_role must be one of {sorted(WORKSPACE_ROLES)}.")
        member = await self._members.get(workspace_id=workspace_id, user_id=user_id)
        if member is None:
            raise NotFoundError("Workspace member not found.")

        if member.workspace_role == "owner" and new_role != "owner":
            await self._ensure_not_last_owner(workspace_id, member)

        member = await self._members.update_role(member, workspace_role=new_role)
        await self._session.commit()
        log_audit_event(
            event_type="workspace",
            action="workspace_member_role_changed",
            resource=f"workspace:{workspace_id}",
            result="success",
            actor=actor,
            metadata={"target_user_id": str(user_id), "workspace_role": new_role},
        )
        return member

    async def remove_member(
        self, workspace_id: uuid.UUID, *, user_id: uuid.UUID, actor: Optional[str]
    ) -> None:
        member = await self._members.get(workspace_id=workspace_id, user_id=user_id)
        if member is None:
            raise NotFoundError("Workspace member not found.")

        await self._ensure_not_last_owner(workspace_id, member)

        await self._members.remove(member)
        await self._session.commit()
        log_audit_event(
            event_type="workspace",
            action="workspace_member_removed",
            resource=f"workspace:{workspace_id}",
            result="success",
            actor=actor,
            metadata={"target_user_id": str(user_id)},
        )
