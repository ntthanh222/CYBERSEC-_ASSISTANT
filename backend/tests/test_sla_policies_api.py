"""SLA policy API: admin global-default CRUD, project effective-policy
read, and project-override set/clear, plus authorization (Task 3)."""
from backend.database.models.rbac import UserRole

from .conftest import TEST_USER_B


async def _seed_role(db_sessionmaker, user_id, *, role="user", is_active=True):
    async with db_sessionmaker() as session:
        session.add(UserRole(user_id=user_id, role=role, is_active=is_active))
        await session.commit()


def _create_workspace(api_client) -> dict:
    return api_client.post(
        "/api/workspaces", json={"name": "Acme Corp Security", "description": None}
    ).json()


def _create_project(api_client, workspace_id: str) -> dict:
    return api_client.post(
        "/api/projects",
        json={
            "workspace_id": workspace_id,
            "name": "Customer Portal",
            "environment": "production",
            "criticality": "high",
            "internet_facing": True,
        },
    ).json()


# ─── Admin global defaults ──────────────────────────────────────────────────


async def test_non_admin_cannot_list_global_sla_policies(api_client):
    response = api_client.get("/api/admin/sla-policies")
    assert response.status_code == 403


async def test_admin_can_list_and_update_global_sla_policies(api_client, db_sessionmaker):
    # api_client defaults to TEST_USER_A - seed that identity as admin so no
    # switch_user is needed.
    from .conftest import TEST_USER_A

    await _seed_role(db_sessionmaker, TEST_USER_A.id, role="admin")

    response = api_client.patch("/api/admin/sla-policies/high", json={"hours_to_deadline": 48})
    assert response.status_code == 200, response.text
    assert response.json()["hours_to_deadline"] == 48
    assert response.json()["project_id"] is None

    listing = api_client.get("/api/admin/sla-policies").json()
    high = next(item for item in listing if item["severity"] == "high")
    assert high["hours_to_deadline"] == 48


async def test_admin_can_create_a_low_severity_default_that_ships_with_none(
    api_client, db_sessionmaker
):
    from .conftest import TEST_USER_A

    await _seed_role(db_sessionmaker, TEST_USER_A.id, role="admin")

    response = api_client.patch("/api/admin/sla-policies/low", json={"hours_to_deadline": 336})
    assert response.status_code == 200
    assert response.json()["severity"] == "low"
    assert response.json()["hours_to_deadline"] == 336


async def test_updating_an_unknown_severity_is_404(api_client, db_sessionmaker):
    from .conftest import TEST_USER_A

    await _seed_role(db_sessionmaker, TEST_USER_A.id, role="admin")

    response = api_client.patch(
        "/api/admin/sla-policies/apocalyptic", json={"hours_to_deadline": 1}
    )
    assert response.status_code == 404


async def test_updating_global_policy_with_non_positive_hours_is_422(api_client, db_sessionmaker):
    from .conftest import TEST_USER_A

    await _seed_role(db_sessionmaker, TEST_USER_A.id, role="admin")

    response = api_client.patch("/api/admin/sla-policies/high", json={"hours_to_deadline": 0})
    assert response.status_code == 422


# ─── Project effective policy + overrides ──────────────────────────────────


async def test_effective_policy_falls_back_to_global_default(api_client, db_sessionmaker):
    from .conftest import TEST_USER_A

    await _seed_role(db_sessionmaker, TEST_USER_A.id, role="admin")
    api_client.patch("/api/admin/sla-policies/critical", json={"hours_to_deadline": 24})

    workspace = _create_workspace(api_client)
    project = _create_project(api_client, workspace["id"])

    effective = api_client.get(f"/api/projects/{project['id']}/sla-policies").json()
    critical = next(item for item in effective if item["severity"] == "critical")
    assert critical["hours_to_deadline"] == 24
    assert critical["source"] == "global_default"

    low = next(item for item in effective if item["severity"] == "low")
    assert low["hours_to_deadline"] is None
    assert low["source"] == "none"


async def test_owner_can_set_and_clear_a_project_override(api_client, db_sessionmaker):
    from .conftest import TEST_USER_A

    await _seed_role(db_sessionmaker, TEST_USER_A.id, role="admin")
    api_client.patch("/api/admin/sla-policies/high", json={"hours_to_deadline": 72})

    workspace = _create_workspace(api_client)
    project = _create_project(api_client, workspace["id"])

    override = api_client.put(
        f"/api/projects/{project['id']}/sla-policies/high", json={"hours_to_deadline": 8}
    )
    assert override.status_code == 200, override.text
    assert override.json()["hours_to_deadline"] == 8
    assert override.json()["source"] == "project_override"

    effective = api_client.get(f"/api/projects/{project['id']}/sla-policies").json()
    high = next(item for item in effective if item["severity"] == "high")
    assert high["hours_to_deadline"] == 8
    assert high["source"] == "project_override"

    cleared = api_client.put(
        f"/api/projects/{project['id']}/sla-policies/high", json={"hours_to_deadline": None}
    )
    assert cleared.status_code == 200
    assert cleared.json()["source"] == "global_default"
    assert cleared.json()["hours_to_deadline"] == 72


def test_developer_cannot_set_a_project_sla_override(api_client, switch_user):
    workspace = _create_workspace(api_client)
    project = _create_project(api_client, workspace["id"])
    api_client.post(
        f"/api/projects/{project['id']}/members",
        json={"user_id": str(TEST_USER_B.id), "project_role": "developer"},
    )

    switch_user(TEST_USER_B)
    response = api_client.put(
        f"/api/projects/{project['id']}/sla-policies/high", json={"hours_to_deadline": 1}
    )
    assert response.status_code == 403


def test_viewer_can_read_effective_policy(api_client, switch_user):
    workspace = _create_workspace(api_client)
    project = _create_project(api_client, workspace["id"])
    api_client.post(
        f"/api/projects/{project['id']}/members",
        json={"user_id": str(TEST_USER_B.id), "project_role": "viewer"},
    )

    switch_user(TEST_USER_B)
    response = api_client.get(f"/api/projects/{project['id']}/sla-policies")
    assert response.status_code == 200
    assert len(response.json()) == 4  # one row per FINDING_SEVERITIES entry


def test_sla_policies_require_authentication(unauthenticated_client):
    response = unauthenticated_client.get("/api/admin/sla-policies")
    assert response.status_code == 401
