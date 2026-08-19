"""Workspace API: CRUD, membership, last-owner-lockout, visibility."""
import uuid

from backend.database.models.rbac import UserRole

from .conftest import TEST_USER_A, TEST_USER_B


async def _seed_role(db_sessionmaker, user_id, *, role="user", is_active=True):
    async with db_sessionmaker() as session:
        session.add(UserRole(user_id=user_id, role=role, is_active=is_active))
        await session.commit()


def _workspace_payload(**overrides) -> dict:
    payload = {"name": "Acme Corp Security", "description": "Primary org workspace."}
    payload.update(overrides)
    return payload


# ─── CRUD ───────────────────────────────────────────────────────────────────


def test_create_workspace_returns_the_created_record(api_client):
    response = api_client.post("/api/workspaces", json=_workspace_payload())
    assert response.status_code == 201
    body = response.json()
    assert body["id"]
    assert body["name"] == "Acme Corp Security"
    assert body["created_by_user_id"] == str(TEST_USER_A.id)


def test_created_workspace_appears_in_the_list(api_client):
    api_client.post("/api/workspaces", json=_workspace_payload())
    page = api_client.get("/api/workspaces").json()
    assert page["total"] == 1
    assert page["items"][0]["name"] == "Acme Corp Security"


def test_get_one_workspace_by_id(api_client):
    created = api_client.post("/api/workspaces", json=_workspace_payload()).json()
    detail = api_client.get(f"/api/workspaces/{created['id']}")
    assert detail.status_code == 200
    assert detail.json()["name"] == "Acme Corp Security"


def test_get_nonexistent_workspace_is_404(api_client):
    response = api_client.get(f"/api/workspaces/{uuid.uuid4()}")
    assert response.status_code == 404


def test_update_workspace_as_owner(api_client):
    created = api_client.post("/api/workspaces", json=_workspace_payload()).json()
    response = api_client.patch(f"/api/workspaces/{created['id']}", json={"name": "Renamed Co"})
    assert response.status_code == 200
    assert response.json()["name"] == "Renamed Co"


def test_create_rejects_missing_name(api_client):
    response = api_client.post("/api/workspaces", json={"description": "no name"})
    assert response.status_code == 422


# ─── Membership ─────────────────────────────────────────────────────────────


def test_creator_is_auto_added_as_owner_member(api_client):
    created = api_client.post("/api/workspaces", json=_workspace_payload()).json()
    members = api_client.get(f"/api/workspaces/{created['id']}/members").json()["items"]
    assert len(members) == 1
    assert members[0]["user_id"] == str(TEST_USER_A.id)
    assert members[0]["workspace_role"] == "owner"


def test_owner_can_add_a_member(api_client):
    created = api_client.post("/api/workspaces", json=_workspace_payload()).json()
    response = api_client.post(
        f"/api/workspaces/{created['id']}/members",
        json={"user_id": str(TEST_USER_B.id), "workspace_role": "member"},
    )
    assert response.status_code == 201
    assert response.json()["workspace_role"] == "member"


def test_adding_an_existing_member_is_409(api_client):
    created = api_client.post("/api/workspaces", json=_workspace_payload()).json()
    response = api_client.post(
        f"/api/workspaces/{created['id']}/members",
        json={"user_id": str(TEST_USER_A.id), "workspace_role": "member"},
    )
    assert response.status_code == 409


def test_owner_can_change_a_members_role(api_client):
    created = api_client.post("/api/workspaces", json=_workspace_payload()).json()
    api_client.post(
        f"/api/workspaces/{created['id']}/members",
        json={"user_id": str(TEST_USER_B.id), "workspace_role": "member"},
    )
    response = api_client.patch(
        f"/api/workspaces/{created['id']}/members/{TEST_USER_B.id}",
        json={"workspace_role": "admin"},
    )
    assert response.status_code == 200
    assert response.json()["workspace_role"] == "admin"


def test_owner_can_remove_a_member(api_client):
    created = api_client.post("/api/workspaces", json=_workspace_payload()).json()
    api_client.post(
        f"/api/workspaces/{created['id']}/members",
        json={"user_id": str(TEST_USER_B.id), "workspace_role": "member"},
    )
    response = api_client.delete(f"/api/workspaces/{created['id']}/members/{TEST_USER_B.id}")
    assert response.status_code == 204
    members = api_client.get(f"/api/workspaces/{created['id']}/members").json()["items"]
    assert len(members) == 1


def test_regular_member_cannot_add_members(api_client, switch_user):
    created = api_client.post("/api/workspaces", json=_workspace_payload()).json()
    api_client.post(
        f"/api/workspaces/{created['id']}/members",
        json={"user_id": str(TEST_USER_B.id), "workspace_role": "member"},
    )

    switch_user(TEST_USER_B)
    response = api_client.post(
        f"/api/workspaces/{created['id']}/members",
        json={"user_id": str(uuid.uuid4()), "workspace_role": "member"},
    )
    assert response.status_code == 403


# ─── Last-owner-lockout invariant ───────────────────────────────────────────


def test_demoting_the_last_owner_is_409(api_client):
    created = api_client.post("/api/workspaces", json=_workspace_payload()).json()
    response = api_client.patch(
        f"/api/workspaces/{created['id']}/members/{TEST_USER_A.id}",
        json={"workspace_role": "member"},
    )
    assert response.status_code == 409


def test_removing_the_last_owner_is_409(api_client):
    created = api_client.post("/api/workspaces", json=_workspace_payload()).json()
    response = api_client.delete(f"/api/workspaces/{created['id']}/members/{TEST_USER_A.id}")
    assert response.status_code == 409


def test_demoting_one_of_two_owners_is_allowed(api_client):
    created = api_client.post("/api/workspaces", json=_workspace_payload()).json()
    api_client.post(
        f"/api/workspaces/{created['id']}/members",
        json={"user_id": str(TEST_USER_B.id), "workspace_role": "owner"},
    )
    response = api_client.patch(
        f"/api/workspaces/{created['id']}/members/{TEST_USER_A.id}",
        json={"workspace_role": "member"},
    )
    assert response.status_code == 200


# ─── Visibility (404-on-invisible, cross-user isolation) ───────────────────


def test_non_member_gets_404_not_403(api_client, switch_user):
    created = api_client.post("/api/workspaces", json=_workspace_payload()).json()

    switch_user(TEST_USER_B)
    response = api_client.get(f"/api/workspaces/{created['id']}")
    assert response.status_code == 404


def test_non_member_does_not_see_workspace_in_list(api_client, switch_user):
    api_client.post("/api/workspaces", json=_workspace_payload())

    switch_user(TEST_USER_B)
    page = api_client.get("/api/workspaces").json()
    assert page["total"] == 0


# ─── Global admin bypass ────────────────────────────────────────────────────


async def test_global_admin_sees_every_workspace(api_client, db_sessionmaker, switch_user):
    created = api_client.post("/api/workspaces", json=_workspace_payload()).json()

    await _seed_role(db_sessionmaker, TEST_USER_B.id, role="admin")
    switch_user(TEST_USER_B)

    detail = api_client.get(f"/api/workspaces/{created['id']}")
    assert detail.status_code == 200

    page = api_client.get("/api/workspaces").json()
    assert page["total"] == 1


async def test_global_admin_can_manage_membership_without_a_membership_row(
    api_client, db_sessionmaker, switch_user
):
    created = api_client.post("/api/workspaces", json=_workspace_payload()).json()

    await _seed_role(db_sessionmaker, TEST_USER_B.id, role="admin")
    switch_user(TEST_USER_B)

    response = api_client.patch(f"/api/workspaces/{created['id']}", json={"name": "Admin Edit"})
    assert response.status_code == 200


# ─── Auth gating ─────────────────────────────────────────────────────────────


def test_list_requires_authentication(unauthenticated_client):
    response = unauthenticated_client.get("/api/workspaces")
    assert response.status_code == 401


def test_create_requires_authentication(unauthenticated_client):
    response = unauthenticated_client.post("/api/workspaces", json=_workspace_payload())
    assert response.status_code == 401
