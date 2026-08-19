"""Finding API: manual creation, every transition endpoint scenario
(success + 403/422 failures), authorization, and assignee setting."""
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
    api_client.post(
        f"/api/projects/{project_id}/members",
        json={"user_id": str(user_id), "project_role": role},
    )


# ─── Manual creation ────────────────────────────────────────────────────────


def test_owner_can_create_a_finding_manually(api_client):
    workspace = _create_workspace(api_client)
    project = _create_project(api_client, workspace["id"])
    body = _create_finding(api_client, project["id"])
    assert body["status"] == "open"
    assert body["scan_run_id"] is None
    assert body["severity"] == "high"


def test_developer_cannot_create_a_finding_manually(api_client, switch_user):
    workspace = _create_workspace(api_client)
    project = _create_project(api_client, workspace["id"])
    _add_member(api_client, project["id"], TEST_USER_B.id, "developer")

    switch_user(TEST_USER_B)
    response = api_client.post(
        f"/api/projects/{project['id']}/findings", json=_finding_payload()
    )
    assert response.status_code == 403


def test_creating_a_finding_with_invalid_severity_is_422(api_client):
    workspace = _create_workspace(api_client)
    project = _create_project(api_client, workspace["id"])
    response = api_client.post(
        f"/api/projects/{project['id']}/findings",
        json=_finding_payload(severity="apocalyptic"),
    )
    assert response.status_code == 422


# ─── Listing / filtering ────────────────────────────────────────────────────


def test_list_findings_filters_by_status_and_severity(api_client):
    workspace = _create_workspace(api_client)
    project = _create_project(api_client, workspace["id"])
    _create_finding(api_client, project["id"], rule_id="a", severity="high", target="https://x/a")
    _create_finding(api_client, project["id"], rule_id="b", severity="low", target="https://x/b")

    page = api_client.get(f"/api/projects/{project['id']}/findings?severity=low").json()
    assert page["total"] == 1
    assert page["items"][0]["rule_id"] == "b"


def test_finding_from_a_different_project_is_404(api_client):
    workspace = _create_workspace(api_client)
    project_a = _create_project(api_client, workspace["id"])
    project_b = _create_project(api_client, workspace["id"])
    finding = _create_finding(api_client, project_a["id"])

    response = api_client.get(f"/api/projects/{project_b['id']}/findings/{finding['id']}")
    assert response.status_code == 404


# ─── Transitions: success paths ─────────────────────────────────────────────


def test_owner_can_confirm_an_open_finding(api_client):
    workspace = _create_workspace(api_client)
    project = _create_project(api_client, workspace["id"])
    finding = _create_finding(api_client, project["id"])

    response = api_client.post(
        f"/api/projects/{project['id']}/findings/{finding['id']}/transition",
        json={"to_status": "confirmed"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "confirmed"


def test_developer_assignee_can_move_in_progress_to_fixed(api_client, switch_user):
    workspace = _create_workspace(api_client)
    project = _create_project(api_client, workspace["id"])
    _add_member(api_client, project["id"], TEST_USER_B.id, "developer")
    finding = _create_finding(api_client, project["id"], assignee_user_id=str(TEST_USER_B.id))

    api_client.post(
        f"/api/projects/{project['id']}/findings/{finding['id']}/transition",
        json={"to_status": "confirmed"},
    )
    api_client.post(
        f"/api/projects/{project['id']}/findings/{finding['id']}/transition",
        json={"to_status": "in_progress"},
    )

    switch_user(TEST_USER_B)
    response = api_client.post(
        f"/api/projects/{project['id']}/findings/{finding['id']}/transition",
        json={"to_status": "fixed"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "fixed"


def test_owner_can_verify_and_close_after_developer_fixes(api_client, switch_user):
    workspace = _create_workspace(api_client)
    project = _create_project(api_client, workspace["id"])
    _add_member(api_client, project["id"], TEST_USER_B.id, "developer")
    finding = _create_finding(api_client, project["id"], assignee_user_id=str(TEST_USER_B.id))

    api_client.post(
        f"/api/projects/{project['id']}/findings/{finding['id']}/transition",
        json={"to_status": "confirmed"},
    )
    api_client.post(
        f"/api/projects/{project['id']}/findings/{finding['id']}/transition",
        json={"to_status": "in_progress"},
    )
    switch_user(TEST_USER_B)
    api_client.post(
        f"/api/projects/{project['id']}/findings/{finding['id']}/transition",
        json={"to_status": "fixed"},
    )

    switch_user(TEST_USER_A)
    verify = api_client.post(
        f"/api/projects/{project['id']}/findings/{finding['id']}/transition",
        json={"to_status": "verified"},
    )
    assert verify.status_code == 200
    close = api_client.post(
        f"/api/projects/{project['id']}/findings/{finding['id']}/transition",
        json={"to_status": "closed"},
    )
    assert close.status_code == 200
    assert close.json()["status"] == "closed"
    assert close.json()["closed_at"] is not None


def test_false_positive_with_reason_succeeds(api_client):
    workspace = _create_workspace(api_client)
    project = _create_project(api_client, workspace["id"])
    finding = _create_finding(api_client, project["id"])

    response = api_client.post(
        f"/api/projects/{project['id']}/findings/{finding['id']}/transition",
        json={"to_status": "false_positive", "reason": "Confirmed benign after manual review."},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "false_positive"
    assert response.json()["resolution_reason"] == "Confirmed benign after manual review."


# ─── Transitions: hard "developer can never verify/close" rule ─────────────


def test_developer_assignee_cannot_verify_even_though_they_are_assignee(api_client, switch_user):
    workspace = _create_workspace(api_client)
    project = _create_project(api_client, workspace["id"])
    _add_member(api_client, project["id"], TEST_USER_B.id, "developer")
    finding = _create_finding(api_client, project["id"], assignee_user_id=str(TEST_USER_B.id))

    api_client.post(
        f"/api/projects/{project['id']}/findings/{finding['id']}/transition",
        json={"to_status": "confirmed"},
    )
    api_client.post(
        f"/api/projects/{project['id']}/findings/{finding['id']}/transition",
        json={"to_status": "in_progress"},
    )
    switch_user(TEST_USER_B)
    api_client.post(
        f"/api/projects/{project['id']}/findings/{finding['id']}/transition",
        json={"to_status": "fixed"},
    )

    response = api_client.post(
        f"/api/projects/{project['id']}/findings/{finding['id']}/transition",
        json={"to_status": "verified"},
    )
    assert response.status_code == 403


# ─── Transitions: failure paths ────────────────────────────────────────────


def test_developer_non_assignee_cannot_move_in_progress_to_fixed(api_client, switch_user):
    workspace = _create_workspace(api_client)
    project = _create_project(api_client, workspace["id"])
    _add_member(api_client, project["id"], TEST_USER_B.id, "developer")
    finding = _create_finding(api_client, project["id"])  # no assignee set

    api_client.post(
        f"/api/projects/{project['id']}/findings/{finding['id']}/transition",
        json={"to_status": "confirmed"},
    )
    api_client.post(
        f"/api/projects/{project['id']}/findings/{finding['id']}/transition",
        json={"to_status": "in_progress"},
    )

    switch_user(TEST_USER_B)
    response = api_client.post(
        f"/api/projects/{project['id']}/findings/{finding['id']}/transition",
        json={"to_status": "fixed"},
    )
    assert response.status_code == 403


def test_viewer_cannot_transition_a_finding(api_client, switch_user):
    workspace = _create_workspace(api_client)
    project = _create_project(api_client, workspace["id"])
    _add_member(api_client, project["id"], TEST_USER_B.id, "viewer")
    finding = _create_finding(api_client, project["id"])

    switch_user(TEST_USER_B)
    response = api_client.post(
        f"/api/projects/{project['id']}/findings/{finding['id']}/transition",
        json={"to_status": "confirmed"},
    )
    assert response.status_code == 403


def test_false_positive_without_reason_is_422(api_client):
    workspace = _create_workspace(api_client)
    project = _create_project(api_client, workspace["id"])
    finding = _create_finding(api_client, project["id"])

    response = api_client.post(
        f"/api/projects/{project['id']}/findings/{finding['id']}/transition",
        json={"to_status": "false_positive"},
    )
    assert response.status_code == 422


def test_invalid_edge_is_422(api_client):
    workspace = _create_workspace(api_client)
    project = _create_project(api_client, workspace["id"])
    finding = _create_finding(api_client, project["id"])

    response = api_client.post(
        f"/api/projects/{project['id']}/findings/{finding['id']}/transition",
        json={"to_status": "verified"},  # open -> verified is not a real edge
    )
    assert response.status_code == 422


async def test_global_admin_may_transition_without_project_membership(
    api_client, db_sessionmaker, switch_user
):
    workspace = _create_workspace(api_client)
    project = _create_project(api_client, workspace["id"])
    finding = _create_finding(api_client, project["id"])

    await _seed_role(db_sessionmaker, TEST_USER_B.id, role="admin")
    switch_user(TEST_USER_B)
    response = api_client.post(
        f"/api/projects/{project['id']}/findings/{finding['id']}/transition",
        json={"to_status": "confirmed"},
    )
    assert response.status_code == 200


# ─── Assignee setting ───────────────────────────────────────────────────────


def test_owner_can_set_assignee(api_client):
    workspace = _create_workspace(api_client)
    project = _create_project(api_client, workspace["id"])
    _add_member(api_client, project["id"], TEST_USER_B.id, "developer")
    finding = _create_finding(api_client, project["id"])

    response = api_client.patch(
        f"/api/projects/{project['id']}/findings/{finding['id']}/assignee",
        json={"assignee_user_id": str(TEST_USER_B.id)},
    )
    assert response.status_code == 200
    assert response.json()["assignee_user_id"] == str(TEST_USER_B.id)


def test_developer_cannot_set_assignee(api_client, switch_user):
    workspace = _create_workspace(api_client)
    project = _create_project(api_client, workspace["id"])
    _add_member(api_client, project["id"], TEST_USER_B.id, "developer")
    finding = _create_finding(api_client, project["id"])

    switch_user(TEST_USER_B)
    response = api_client.patch(
        f"/api/projects/{project['id']}/findings/{finding['id']}/assignee",
        json={"assignee_user_id": str(TEST_USER_B.id)},
    )
    assert response.status_code == 403


def test_findings_require_authentication(unauthenticated_client):
    response = unauthenticated_client.get(f"/api/projects/{uuid.uuid4()}/findings")
    assert response.status_code == 401
