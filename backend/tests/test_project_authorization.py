"""Unit tests for backend.core.project_authorization, isolated from the API
layer: exercises get_project_member/require_project_role directly against a
hand-built session, independent of routing/dependency-injection wiring.
"""
import uuid

import pytest

from backend.core.authorization import AppUser
from backend.core.exceptions import AuthorizationError, NotFoundError
from backend.core.project_authorization import get_project_member, require_project_role
from backend.database.models.project import Project, ProjectMember
from backend.database.models.workspace import Workspace, WorkspaceMember


def _app_user(user_id: uuid.UUID, *, role: str = "user") -> AppUser:
    return AppUser(id=user_id, email=None, role=role, is_active=True)


async def _seed_workspace_and_project(session, *, creator_id: uuid.UUID):
    workspace = Workspace(name="W", created_by_user_id=creator_id)
    session.add(workspace)
    await session.flush()
    project = Project(
        workspace_id=workspace.id,
        name="P",
        environment="production",
        criticality="high",
        owner_user_id=creator_id,
    )
    session.add(project)
    await session.flush()
    await session.commit()
    return workspace, project


async def test_get_project_member_returns_direct_membership_row(db_sessionmaker):
    async with db_sessionmaker() as session:
        creator_id = uuid.uuid4()
        workspace, project = await _seed_workspace_and_project(session, creator_id=creator_id)
        member = ProjectMember(project_id=project.id, user_id=creator_id, project_role="owner")
        session.add(member)
        await session.commit()

        result = await get_project_member(
            project.id, app_user=_app_user(creator_id), session=session
        )
        assert result is not None
        assert result.project_role == "owner"


async def test_get_project_member_404s_for_a_stranger(db_sessionmaker):
    async with db_sessionmaker() as session:
        creator_id = uuid.uuid4()
        _workspace, project = await _seed_workspace_and_project(session, creator_id=creator_id)

        with pytest.raises(NotFoundError):
            await get_project_member(
                project.id, app_user=_app_user(uuid.uuid4()), session=session
            )


async def test_get_project_member_404s_for_a_nonexistent_project(db_sessionmaker):
    async with db_sessionmaker() as session:
        with pytest.raises(NotFoundError):
            await get_project_member(
                uuid.uuid4(), app_user=_app_user(uuid.uuid4()), session=session
            )


async def test_get_project_member_bypasses_for_global_admin(db_sessionmaker):
    async with db_sessionmaker() as session:
        creator_id = uuid.uuid4()
        _workspace, project = await _seed_workspace_and_project(session, creator_id=creator_id)

        result = await get_project_member(
            project.id, app_user=_app_user(uuid.uuid4(), role="admin"), session=session
        )
        assert result is None


async def test_get_project_member_treats_workspace_owner_as_authorized(db_sessionmaker):
    async with db_sessionmaker() as session:
        creator_id = uuid.uuid4()
        workspace, project = await _seed_workspace_and_project(session, creator_id=creator_id)
        ws_admin_id = uuid.uuid4()
        session.add(
            WorkspaceMember(workspace_id=workspace.id, user_id=ws_admin_id, workspace_role="admin")
        )
        await session.commit()

        result = await get_project_member(
            project.id, app_user=_app_user(ws_admin_id), session=session
        )
        # None signals "authorized via bypass", exactly like the global-admin case.
        assert result is None


async def test_get_project_member_ignores_a_plain_workspace_member(db_sessionmaker):
    async with db_sessionmaker() as session:
        creator_id = uuid.uuid4()
        workspace, project = await _seed_workspace_and_project(session, creator_id=creator_id)
        plain_member_id = uuid.uuid4()
        session.add(
            WorkspaceMember(
                workspace_id=workspace.id, user_id=plain_member_id, workspace_role="member"
            )
        )
        await session.commit()

        with pytest.raises(NotFoundError):
            await get_project_member(
                project.id, app_user=_app_user(plain_member_id), session=session
            )


async def test_require_project_role_allows_a_listed_role():
    dependency = require_project_role("owner", "security")
    member = ProjectMember(
        id=uuid.uuid4(), project_id=uuid.uuid4(), user_id=uuid.uuid4(), project_role="owner"
    )
    result = await dependency(member=member)
    assert result is member


async def test_require_project_role_rejects_an_unlisted_role():
    dependency = require_project_role("owner", "security")
    member = ProjectMember(
        id=uuid.uuid4(), project_id=uuid.uuid4(), user_id=uuid.uuid4(), project_role="viewer"
    )
    with pytest.raises(AuthorizationError):
        await dependency(member=member)


async def test_require_project_role_does_not_imply_hierarchy_between_owner_and_security():
    """Set-based, not a linear rank: a route that only lists 'security' must
    reject an 'owner' project member that isn't also explicitly listed."""
    dependency = require_project_role("security")
    member = ProjectMember(
        id=uuid.uuid4(), project_id=uuid.uuid4(), user_id=uuid.uuid4(), project_role="owner"
    )
    with pytest.raises(AuthorizationError):
        await dependency(member=member)


async def test_require_project_role_passes_through_a_bypass():
    dependency = require_project_role("owner")
    result = await dependency(member=None)
    assert result is None
