"""Task 4: cross-project "My Tasks" (GET /api/findings/my-tasks) -
aggregation across projects, filtering, and authorization isolation."""
import uuid

from backend.core.auth import AuthenticatedUser

from .conftest import TEST_USER_B


def _create_workspace(api_client) -> dict:
    return api_client.post(
        "/api/workspaces", json={"name": "Acme Corp Security", "description": None}
    ).json()


def _create_project(api_client, workspace_id: str, name: str = "Customer Portal") -> dict:
    return api_client.post(
        "/api/projects",
        json={
            "workspace_id": workspace_id,
            "name": name,
            "environment": "production",
            "criticality": "high",
            "internet_facing": True,
        },
    ).json()


def _finding_payload(**overrides) -> dict:
    payload = {
        "rule_id": "sqli",
        "category": "injection",
        "title": "SQL injection in login form",
        "evidence": "payload reflected",
        "impact": "Full DB read access",
        "remediation": "Use parameterized queries",
        "severity": "high",
        "target": "https://example.com/login",
    }
    payload.update(overrides)
    return payload


def _create_finding(api_client, project_id: str, **overrides) -> dict:
    response = api_client.post(
        f"/api/projects/{project_id}/findings", json=_finding_payload(**overrides)
    )
    assert response.status_code == 201, response.text
    return response.json()


def _add_member(api_client, project_id: str, user_id, role: str) -> None:
    response = api_client.post(
        f"/api/projects/{project_id}/members",
        json={"user_id": str(user_id), "project_role": role},
    )
    assert response.status_code == 201, response.text


def _set_assignee(api_client, project_id: str, finding_id: str, assignee_user_id) -> None:
    response = api_client.patch(
        f"/api/projects/{project_id}/findings/{finding_id}/assignee",
        json={"assignee_user_id": str(assignee_user_id)},
    )
    assert response.status_code == 200, response.text


def test_my_tasks_aggregates_across_two_projects(api_client, switch_user):
    workspace = _create_workspace(api_client)
    project_a = _create_project(api_client, workspace["id"], name="Portal A")
    project_b = _create_project(api_client, workspace["id"], name="Portal B")
    _add_member(api_client, project_a["id"], TEST_USER_B.id, "developer")
    _add_member(api_client, project_b["id"], TEST_USER_B.id, "developer")

    finding_a = _create_finding(api_client, project_a["id"], rule_id="a", target="https://x/a")
    finding_b = _create_finding(api_client, project_b["id"], rule_id="b", target="https://x/b")
    _set_assignee(api_client, project_a["id"], finding_a["id"], TEST_USER_B.id)
    _set_assignee(api_client, project_b["id"], finding_b["id"], TEST_USER_B.id)

    switch_user(TEST_USER_B)
    response = api_client.get("/api/findings/my-tasks")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 2
    project_names = {item["project_name"] for item in body["items"]}
    assert project_names == {"Portal A", "Portal B"}
    finding_ids = {item["id"] for item in body["items"]}
    assert finding_ids == {finding_a["id"], finding_b["id"]}


def test_my_tasks_filters_by_status_and_severity(api_client, switch_user):
    workspace = _create_workspace(api_client)
    project = _create_project(api_client, workspace["id"])
    _add_member(api_client, project["id"], TEST_USER_B.id, "developer")

    high = _create_finding(api_client, project["id"], rule_id="a", severity="high", target="https://x/a")
    low = _create_finding(api_client, project["id"], rule_id="b", severity="low", target="https://x/b")
    _set_assignee(api_client, project["id"], high["id"], TEST_USER_B.id)
    _set_assignee(api_client, project["id"], low["id"], TEST_USER_B.id)

    switch_user(TEST_USER_B)
    response = api_client.get("/api/findings/my-tasks?severity=low")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == low["id"]

    response = api_client.get("/api/findings/my-tasks?status=open")
    assert response.status_code == 200
    assert response.json()["total"] == 2


def test_my_tasks_filters_by_overdue(api_client, switch_user):
    workspace = _create_workspace(api_client)
    project = _create_project(api_client, workspace["id"])
    _add_member(api_client, project["id"], TEST_USER_B.id, "developer")
    finding = _create_finding(api_client, project["id"])
    _set_assignee(api_client, project["id"], finding["id"], TEST_USER_B.id)

    switch_user(TEST_USER_B)
    # A fresh "open" finding has no deadline set yet (deadline is only set on
    # confirmed), so it can never be overdue.
    response = api_client.get("/api/findings/my-tasks?overdue=true")
    assert response.status_code == 200
    assert response.json()["total"] == 0

    response = api_client.get("/api/findings/my-tasks?overdue=false")
    assert response.status_code == 200
    assert response.json()["total"] == 1


def test_my_tasks_never_shows_another_caller_assignments(api_client, switch_user):
    workspace = _create_workspace(api_client)
    project = _create_project(api_client, workspace["id"])
    _add_member(api_client, project["id"], TEST_USER_B.id, "developer")
    finding = _create_finding(api_client, project["id"])
    _set_assignee(api_client, project["id"], finding["id"], TEST_USER_B.id)

    # TEST_USER_A (the caller, project owner) has no assignments of their own.
    response = api_client.get("/api/findings/my-tasks")
    assert response.status_code == 200
    assert response.json()["total"] == 0

    # A third, unrelated authenticated user (never a member, never assigned
    # anything) also sees nothing - isolation holds regardless of identity.
    third_party = AuthenticatedUser(id=uuid.uuid4(), role="authenticated", claims={})
    switch_user(third_party)
    response = api_client.get("/api/findings/my-tasks")
    assert response.status_code == 200
    assert response.json()["total"] == 0


def test_my_tasks_requires_authentication(unauthenticated_client):
    response = unauthenticated_client.get("/api/findings/my-tasks")
    assert response.status_code == 401
