"""Project API: CRUD, membership, last-owner-lockout, workspace-owner
implied access, and visibility."""
import uuid

from backend.database.models.rbac import UserRole

from .conftest import TEST_USER_A, TEST_USER_B


async def _seed_role(db_sessionmaker, user_id, *, role="user", is_active=True):
    async with db_sessionmaker() as session:
        session.add(UserRole(user_id=user_id, role=role, is_active=is_active))
        await session.commit()


def _create_workspace(api_client) -> dict:
    return api_client.post(
        "/api/workspaces", json={"name": "Acme Corp Security", "description": None}
    ).json()


def _project_payload(workspace_id: str, **overrides) -> dict:
    payload = {
        "workspace_id": workspace_id,
        "name": "Customer Portal",
        "domain": "portal.acme.com",
        "environment": "production",
        "criticality": "high",
        "internet_facing": True,
        "technologies": [{"name": "Django", "version": "4.2"}],
    }
    payload.update(overrides)
    return payload


# ─── CRUD ───────────────────────────────────────────────────────────────────


def test_create_project_returns_the_created_record(api_client):
    workspace = _create_workspace(api_client)
    response = api_client.post("/api/projects", json=_project_payload(workspace["id"]))
    assert response.status_code == 201
    body = response.json()
    assert body["id"]
    assert body["name"] == "Customer Portal"
    assert body["workspace_id"] == workspace["id"]
    assert body["status"] == "active"
    assert body["technologies"] == [{"name": "Django", "version": "4.2"}]


def test_created_project_appears_in_the_list(api_client):
    workspace = _create_workspace(api_client)
    api_client.post("/api/projects", json=_project_payload(workspace["id"]))
    page = api_client.get("/api/projects").json()
    assert page["total"] == 1


def test_list_filters_by_workspace(api_client):
    workspace_a = _create_workspace(api_client)
    workspace_b = _create_workspace(api_client)
    api_client.post("/api/projects", json=_project_payload(workspace_a["id"], name="A"))
    api_client.post("/api/projects", json=_project_payload(workspace_b["id"], name="B"))

    page = api_client.get(f"/api/projects?workspace_id={workspace_a['id']}").json()
    assert page["total"] == 1
    assert page["items"][0]["name"] == "A"


def test_get_one_project_by_id(api_client):
    workspace = _create_workspace(api_client)
    created = api_client.post("/api/projects", json=_project_payload(workspace["id"])).json()
    detail = api_client.get(f"/api/projects/{created['id']}")
    assert detail.status_code == 200
    assert detail.json()["domain"] == "portal.acme.com"


def test_get_nonexistent_project_is_404(api_client):
    response = api_client.get(f"/api/projects/{uuid.uuid4()}")
    assert response.status_code == 404


def test_update_project_as_owner(api_client):
    workspace = _create_workspace(api_client)
    created = api_client.post("/api/projects", json=_project_payload(workspace["id"])).json()
    response = api_client.patch(f"/api/projects/{created['id']}", json={"name": "Renamed"})
    assert response.status_code == 200
    assert response.json()["name"] == "Renamed"


def test_create_requires_workspace_owner_or_admin(api_client, switch_user):
    workspace = _create_workspace(api_client)
    api_client.post(
        f"/api/workspaces/{workspace['id']}/members",
        json={"user_id": str(TEST_USER_B.id), "workspace_role": "member"},
    )

    switch_user(TEST_USER_B)
    response = api_client.post("/api/projects", json=_project_payload(workspace["id"]))
    assert response.status_code == 403


def test_create_404s_for_invisible_workspace(api_client, switch_user):
    workspace = _create_workspace(api_client)

    switch_user(TEST_USER_B)
    response = api_client.post("/api/projects", json=_project_payload(workspace["id"]))
    assert response.status_code == 404


# ─── Archiving ───────────────────────────────────────────────────────────────


def test_archive_sets_status_and_archived_at(api_client):
    workspace = _create_workspace(api_client)
    created = api_client.post("/api/projects", json=_project_payload(workspace["id"])).json()
    response = api_client.post(f"/api/projects/{created['id']}/archive")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "archived"
    assert body["archived_at"]


def test_archived_project_excluded_from_default_list(api_client):
    workspace = _create_workspace(api_client)
    created = api_client.post("/api/projects", json=_project_payload(workspace["id"])).json()
    api_client.post(f"/api/projects/{created['id']}/archive")

    page = api_client.get("/api/projects").json()
    assert page["total"] == 0

    page_with_archived = api_client.get("/api/projects?include_archived=true").json()
    assert page_with_archived["total"] == 1


def test_archived_project_still_fetchable_by_id(api_client):
    workspace = _create_workspace(api_client)
    created = api_client.post("/api/projects", json=_project_payload(workspace["id"])).json()
    api_client.post(f"/api/projects/{created['id']}/archive")

    detail = api_client.get(f"/api/projects/{created['id']}")
    assert detail.status_code == 200
    assert detail.json()["status"] == "archived"


# ─── Membership ─────────────────────────────────────────────────────────────


def test_creator_is_auto_added_as_owner_member(api_client):
    workspace = _create_workspace(api_client)
    created = api_client.post("/api/projects", json=_project_payload(workspace["id"])).json()
    members = api_client.get(f"/api/projects/{created['id']}/members").json()["items"]
    assert len(members) == 1
    assert members[0]["user_id"] == str(TEST_USER_A.id)
    assert members[0]["project_role"] == "owner"


def test_owner_can_add_a_developer_member(api_client):
    workspace = _create_workspace(api_client)
    created = api_client.post("/api/projects", json=_project_payload(workspace["id"])).json()
    response = api_client.post(
        f"/api/projects/{created['id']}/members",
        json={"user_id": str(TEST_USER_B.id), "project_role": "developer"},
    )
    assert response.status_code == 201
    assert response.json()["project_role"] == "developer"


def test_adding_an_existing_member_is_409(api_client):
    workspace = _create_workspace(api_client)
    created = api_client.post("/api/projects", json=_project_payload(workspace["id"])).json()
    response = api_client.post(
        f"/api/projects/{created['id']}/members",
        json={"user_id": str(TEST_USER_A.id), "project_role": "developer"},
    )
    assert response.status_code == 409


def test_owner_can_change_a_members_role(api_client):
    workspace = _create_workspace(api_client)
    created = api_client.post("/api/projects", json=_project_payload(workspace["id"])).json()
    api_client.post(
        f"/api/projects/{created['id']}/members",
        json={"user_id": str(TEST_USER_B.id), "project_role": "viewer"},
    )
    response = api_client.patch(
        f"/api/projects/{created['id']}/members/{TEST_USER_B.id}",
        json={"project_role": "security"},
    )
    assert response.status_code == 200
    assert response.json()["project_role"] == "security"


def test_owner_can_remove_a_member(api_client):
    workspace = _create_workspace(api_client)
    created = api_client.post("/api/projects", json=_project_payload(workspace["id"])).json()
    api_client.post(
        f"/api/projects/{created['id']}/members",
        json={"user_id": str(TEST_USER_B.id), "project_role": "viewer"},
    )
    response = api_client.delete(f"/api/projects/{created['id']}/members/{TEST_USER_B.id}")
    assert response.status_code == 204


def test_viewer_cannot_add_members(api_client, switch_user):
    workspace = _create_workspace(api_client)
    created = api_client.post("/api/projects", json=_project_payload(workspace["id"])).json()
    api_client.post(
        f"/api/projects/{created['id']}/members",
        json={"user_id": str(TEST_USER_B.id), "project_role": "viewer"},
    )

    switch_user(TEST_USER_B)
    response = api_client.post(
        f"/api/projects/{created['id']}/members",
        json={"user_id": str(uuid.uuid4()), "project_role": "viewer"},
    )
    assert response.status_code == 403


# ─── Last-owner-lockout invariant ───────────────────────────────────────────


def test_demoting_the_last_owner_is_409(api_client):
    workspace = _create_workspace(api_client)
    created = api_client.post("/api/projects", json=_project_payload(workspace["id"])).json()
    response = api_client.patch(
        f"/api/projects/{created['id']}/members/{TEST_USER_A.id}",
        json={"project_role": "developer"},
    )
    assert response.status_code == 409


def test_removing_the_last_owner_is_409(api_client):
    workspace = _create_workspace(api_client)
    created = api_client.post("/api/projects", json=_project_payload(workspace["id"])).json()
    response = api_client.delete(f"/api/projects/{created['id']}/members/{TEST_USER_A.id}")
    assert response.status_code == 409


def test_demoting_one_of_two_owners_is_allowed(api_client):
    workspace = _create_workspace(api_client)
    created = api_client.post("/api/projects", json=_project_payload(workspace["id"])).json()
    api_client.post(
        f"/api/projects/{created['id']}/members",
        json={"user_id": str(TEST_USER_B.id), "project_role": "owner"},
    )
    response = api_client.patch(
        f"/api/projects/{created['id']}/members/{TEST_USER_A.id}",
        json={"project_role": "viewer"},
    )
    assert response.status_code == 200


# ─── Workspace-owner/admin implied access ──────────────────────────────────


def test_workspace_owner_can_see_project_without_a_project_member_row(api_client, switch_user):
    workspace = _create_workspace(api_client)
    api_client.post(
        f"/api/workspaces/{workspace['id']}/members",
        json={"user_id": str(TEST_USER_B.id), "workspace_role": "admin"},
    )
    created = api_client.post("/api/projects", json=_project_payload(workspace["id"])).json()

    switch_user(TEST_USER_B)
    detail = api_client.get(f"/api/projects/{created['id']}")
    assert detail.status_code == 200

    members_before = api_client.get(f"/api/projects/{created['id']}/members").json()["items"]
    assert all(member["user_id"] != str(TEST_USER_B.id) for member in members_before)


def test_workspace_admin_can_manage_project_members_without_a_project_member_row(
    api_client, switch_user
):
    workspace = _create_workspace(api_client)
    api_client.post(
        f"/api/workspaces/{workspace['id']}/members",
        json={"user_id": str(TEST_USER_B.id), "workspace_role": "admin"},
    )
    created = api_client.post("/api/projects", json=_project_payload(workspace["id"])).json()

    switch_user(TEST_USER_B)
    response = api_client.post(
        f"/api/projects/{created['id']}/members",
        json={"user_id": str(uuid.uuid4()), "project_role": "developer"},
    )
    assert response.status_code == 201


def test_plain_workspace_member_has_no_implied_project_access(api_client, switch_user):
    workspace = _create_workspace(api_client)
    api_client.post(
        f"/api/workspaces/{workspace['id']}/members",
        json={"user_id": str(TEST_USER_B.id), "workspace_role": "member"},
    )
    created = api_client.post("/api/projects", json=_project_payload(workspace["id"])).json()

    switch_user(TEST_USER_B)
    detail = api_client.get(f"/api/projects/{created['id']}")
    assert detail.status_code == 404


# ─── Visibility ─────────────────────────────────────────────────────────────


def test_non_member_gets_404_not_403(api_client, switch_user):
    workspace = _create_workspace(api_client)
    created = api_client.post("/api/projects", json=_project_payload(workspace["id"])).json()

    switch_user(TEST_USER_B)
    response = api_client.get(f"/api/projects/{created['id']}")
    assert response.status_code == 404


def test_non_member_does_not_see_project_in_list(api_client, switch_user):
    workspace = _create_workspace(api_client)
    api_client.post("/api/projects", json=_project_payload(workspace["id"]))

    switch_user(TEST_USER_B)
    page = api_client.get("/api/projects").json()
    assert page["total"] == 0


# ─── Global admin bypass ────────────────────────────────────────────────────


async def test_global_admin_sees_every_project(api_client, db_sessionmaker, switch_user):
    workspace = _create_workspace(api_client)
    created = api_client.post("/api/projects", json=_project_payload(workspace["id"])).json()

    await _seed_role(db_sessionmaker, TEST_USER_B.id, role="admin")
    switch_user(TEST_USER_B)

    detail = api_client.get(f"/api/projects/{created['id']}")
    assert detail.status_code == 200
    page = api_client.get("/api/projects").json()
    assert page["total"] == 1


async def test_global_admin_can_create_project_in_any_workspace(
    api_client, db_sessionmaker, switch_user
):
    workspace = _create_workspace(api_client)

    await _seed_role(db_sessionmaker, TEST_USER_B.id, role="admin")
    switch_user(TEST_USER_B)

    response = api_client.post("/api/projects", json=_project_payload(workspace["id"]))
    assert response.status_code == 201


# ─── Auth gating ─────────────────────────────────────────────────────────────


def test_list_requires_authentication(unauthenticated_client):
    response = unauthenticated_client.get("/api/projects")
    assert response.status_code == 401
