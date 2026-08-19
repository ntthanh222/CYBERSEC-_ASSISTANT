"""Task 4: validated Finding assignment (FindingService.set_assignee) and
the eligible-assignees listing endpoint.

Assignee-setting authorization (owner/security may, developer may not) is
already covered by test_findings_api.py's ``test_owner_can_set_assignee``/
``test_developer_cannot_set_assignee`` - this file focuses on the *new*
Task 4 behaviour: eligibility validation of the target user, unassign
always succeeding, and the eligible-assignees endpoint's contents.
"""
from .conftest import TEST_USER_A, TEST_USER_B


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


def _set_assignee(api_client, project_id: str, finding_id: str, assignee_user_id):
    return api_client.patch(
        f"/api/projects/{project_id}/findings/{finding_id}/assignee",
        json={"assignee_user_id": str(assignee_user_id) if assignee_user_id else None},
    )


# ─── Eligible assignment succeeds ───────────────────────────────────────────


def test_assigning_to_a_developer_member_succeeds(api_client):
    workspace = _create_workspace(api_client)
    project = _create_project(api_client, workspace["id"])
    _add_member(api_client, project["id"], TEST_USER_B.id, "developer")
    finding = _create_finding(api_client, project["id"])

    response = _set_assignee(api_client, project["id"], finding["id"], TEST_USER_B.id)
    assert response.status_code == 200, response.text
    assert response.json()["assignee_user_id"] == str(TEST_USER_B.id)


def test_assigning_to_a_security_member_succeeds(api_client):
    workspace = _create_workspace(api_client)
    project = _create_project(api_client, workspace["id"])
    _add_member(api_client, project["id"], TEST_USER_B.id, "security")
    finding = _create_finding(api_client, project["id"])

    response = _set_assignee(api_client, project["id"], finding["id"], TEST_USER_B.id)
    assert response.status_code == 200, response.text
    assert response.json()["assignee_user_id"] == str(TEST_USER_B.id)


def test_assigning_to_an_owner_member_succeeds(api_client):
    workspace = _create_workspace(api_client)
    project = _create_project(api_client, workspace["id"])
    _add_member(api_client, project["id"], TEST_USER_B.id, "owner")
    finding = _create_finding(api_client, project["id"])

    response = _set_assignee(api_client, project["id"], finding["id"], TEST_USER_B.id)
    assert response.status_code == 200, response.text
    assert response.json()["assignee_user_id"] == str(TEST_USER_B.id)


# ─── Ineligible assignment is rejected with a clear 422 ────────────────────


def test_assigning_to_a_viewer_member_is_422(api_client):
    workspace = _create_workspace(api_client)
    project = _create_project(api_client, workspace["id"])
    _add_member(api_client, project["id"], TEST_USER_B.id, "viewer")
    finding = _create_finding(api_client, project["id"])

    response = _set_assignee(api_client, project["id"], finding["id"], TEST_USER_B.id)
    assert response.status_code == 422, response.text
    body = response.json()
    assert body["error"] == "invalid_assignee"


def test_assigning_to_a_non_member_is_422(api_client):
    workspace = _create_workspace(api_client)
    project = _create_project(api_client, workspace["id"])
    finding = _create_finding(api_client, project["id"])
    # TEST_USER_B is never added as a project member.

    response = _set_assignee(api_client, project["id"], finding["id"], TEST_USER_B.id)
    assert response.status_code == 422, response.text
    assert response.json()["error"] == "invalid_assignee"


# ─── Unassigning is always safe ─────────────────────────────────────────────


def test_clearing_the_assignee_always_succeeds(api_client):
    workspace = _create_workspace(api_client)
    project = _create_project(api_client, workspace["id"])
    _add_member(api_client, project["id"], TEST_USER_B.id, "developer")
    finding = _create_finding(api_client, project["id"])

    assigned = _set_assignee(api_client, project["id"], finding["id"], TEST_USER_B.id)
    assert assigned.status_code == 200

    cleared = _set_assignee(api_client, project["id"], finding["id"], None)
    assert cleared.status_code == 200
    assert cleared.json()["assignee_user_id"] is None


def test_clearing_an_already_unassigned_finding_succeeds(api_client):
    workspace = _create_workspace(api_client)
    project = _create_project(api_client, workspace["id"])
    finding = _create_finding(api_client, project["id"])

    response = _set_assignee(api_client, project["id"], finding["id"], None)
    assert response.status_code == 200
    assert response.json()["assignee_user_id"] is None


# ─── Eligible-assignees listing endpoint ────────────────────────────────────


def test_eligible_assignees_returns_developer_security_owner_not_viewer(api_client):
    workspace = _create_workspace(api_client)
    project = _create_project(api_client, workspace["id"])
    _add_member(api_client, project["id"], TEST_USER_B.id, "developer")

    response = api_client.get(f"/api/projects/{project['id']}/findings/eligible-assignees")
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    user_ids = {item["user_id"] for item in items}
    # TEST_USER_A is the project creator/owner (auto-added), TEST_USER_B was
    # just added as developer - both are eligible.
    assert str(TEST_USER_A.id) in user_ids
    assert str(TEST_USER_B.id) in user_ids
    roles = {item["project_role"] for item in items}
    assert roles <= {"developer", "security", "owner"}


def test_eligible_assignees_excludes_viewers(api_client):
    workspace = _create_workspace(api_client)
    project = _create_project(api_client, workspace["id"])
    _add_member(api_client, project["id"], TEST_USER_B.id, "viewer")

    response = api_client.get(f"/api/projects/{project['id']}/findings/eligible-assignees")
    assert response.status_code == 200, response.text
    user_ids = {item["user_id"] for item in response.json()["items"]}
    assert str(TEST_USER_B.id) not in user_ids
