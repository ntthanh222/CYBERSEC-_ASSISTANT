"""Scan run API: trigger -> finding creation, authorization, and scan
failure handling (partial-write rollback)."""
import uuid

from backend.database.models.rbac import UserRole
from backend.services import scan_orchestrator as scan_orchestrator_module

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


def _fake_scan_result(**overrides) -> dict:
    base = {
        "url": "https://example.com",
        "normalized_url": "https://example.com/",
        "hostname": "example.com",
        "port": 443,
        "scheme": "https",
        "has_https": True,
        "reachable": True,
        "status": "suspicious",
        "risk_score": 30,
        "severity": "medium",
        "http_status": 200,
        "final_url": "https://example.com/",
        "redirect_chain": [],
        "redirect_count": 0,
        "headers": {},
        "body_truncated": False,
        "failure_reason": None,
        "findings": [
            {"code": "no_https", "severity": "medium", "message": "No HTTPS.", "weight": 20},
            {"code": "long_url", "severity": "low", "message": "Long URL.", "weight": 5},
        ],
        "recommendations": [],
        "reputation": {"configured": False},
        "duration_ms": 12.3,
    }
    base.update(overrides)
    return base


def _patch_scan_url(monkeypatch, result: dict | None = None, *, exception: Exception | None = None):
    async def fake_scan_url(raw_url: str, **kwargs):
        if exception is not None:
            raise exception
        return result or _fake_scan_result()

    monkeypatch.setattr(scan_orchestrator_module, "scan_url", fake_scan_url)


# ─── Trigger -> finding creation ────────────────────────────────────────────


def test_trigger_scan_creates_findings(api_client, monkeypatch):
    workspace = _create_workspace(api_client)
    project = _create_project(api_client, workspace["id"])
    _patch_scan_url(monkeypatch)

    response = api_client.post(
        f"/api/projects/{project['id']}/scans", json={"target": "https://example.com"}
    )
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "completed"
    assert body["summary"]["medium"] == 1
    assert body["summary"]["low"] == 1

    findings = api_client.get(f"/api/projects/{project['id']}/findings").json()
    assert findings["total"] == 2
    codes = {item["rule_id"] for item in findings["items"]}
    assert codes == {"no_https", "long_url"}
    for item in findings["items"]:
        assert item["status"] == "open"
        assert item["scan_run_id"] == body["id"]


def test_rescanning_the_same_target_does_not_duplicate_findings(api_client, monkeypatch):
    workspace = _create_workspace(api_client)
    project = _create_project(api_client, workspace["id"])
    _patch_scan_url(monkeypatch)

    api_client.post(f"/api/projects/{project['id']}/scans", json={"target": "https://example.com"})
    second = api_client.post(
        f"/api/projects/{project['id']}/scans", json={"target": "https://example.com"}
    )
    assert second.status_code == 201

    findings = api_client.get(f"/api/projects/{project['id']}/findings").json()
    assert findings["total"] == 2  # still 2, not 4 - same fingerprint reused

    # The existing findings' last_seen_scan_run_id now points at the 2nd run.
    for item in findings["items"]:
        assert item["last_seen_scan_run_id"] == second.json()["id"]


# ─── Scan failure handling (partial-write rollback) ────────────────────────


def test_scan_failure_marks_run_failed_and_writes_no_findings(api_client, monkeypatch):
    workspace = _create_workspace(api_client)
    project = _create_project(api_client, workspace["id"])
    _patch_scan_url(monkeypatch, exception=RuntimeError("boom"))

    response = api_client.post(
        f"/api/projects/{project['id']}/scans", json={"target": "https://example.com"}
    )
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "failed"
    assert body["summary"]["error"] == "boom"

    findings = api_client.get(f"/api/projects/{project['id']}/findings").json()
    assert findings["total"] == 0

    scans = api_client.get(f"/api/projects/{project['id']}/scans").json()
    assert scans["total"] == 1
    assert scans["items"][0]["status"] == "failed"


# ─── Authorization ──────────────────────────────────────────────────────────


def test_developer_cannot_trigger_a_scan(api_client, switch_user, monkeypatch):
    workspace = _create_workspace(api_client)
    project = _create_project(api_client, workspace["id"])
    api_client.post(
        f"/api/projects/{project['id']}/members",
        json={"user_id": str(TEST_USER_B.id), "project_role": "developer"},
    )
    _patch_scan_url(monkeypatch)

    switch_user(TEST_USER_B)
    response = api_client.post(
        f"/api/projects/{project['id']}/scans", json={"target": "https://example.com"}
    )
    assert response.status_code == 403


def test_viewer_cannot_trigger_a_scan(api_client, switch_user, monkeypatch):
    workspace = _create_workspace(api_client)
    project = _create_project(api_client, workspace["id"])
    api_client.post(
        f"/api/projects/{project['id']}/members",
        json={"user_id": str(TEST_USER_B.id), "project_role": "viewer"},
    )
    _patch_scan_url(monkeypatch)

    switch_user(TEST_USER_B)
    response = api_client.post(
        f"/api/projects/{project['id']}/scans", json={"target": "https://example.com"}
    )
    assert response.status_code == 403


def test_viewer_can_list_scans(api_client, switch_user, monkeypatch):
    workspace = _create_workspace(api_client)
    project = _create_project(api_client, workspace["id"])
    api_client.post(
        f"/api/projects/{project['id']}/members",
        json={"user_id": str(TEST_USER_B.id), "project_role": "viewer"},
    )
    _patch_scan_url(monkeypatch)
    api_client.post(f"/api/projects/{project['id']}/scans", json={"target": "https://example.com"})

    switch_user(TEST_USER_B)
    response = api_client.get(f"/api/projects/{project['id']}/scans")
    assert response.status_code == 200
    assert response.json()["total"] == 1


def test_security_role_can_trigger_a_scan(api_client, switch_user, monkeypatch):
    workspace = _create_workspace(api_client)
    project = _create_project(api_client, workspace["id"])
    api_client.post(
        f"/api/projects/{project['id']}/members",
        json={"user_id": str(TEST_USER_B.id), "project_role": "security"},
    )
    _patch_scan_url(monkeypatch)

    switch_user(TEST_USER_B)
    response = api_client.post(
        f"/api/projects/{project['id']}/scans", json={"target": "https://example.com"}
    )
    assert response.status_code == 201


async def test_global_admin_can_trigger_a_scan_without_membership(
    api_client, db_sessionmaker, switch_user, monkeypatch
):
    workspace = _create_workspace(api_client)
    project = _create_project(api_client, workspace["id"])
    _patch_scan_url(monkeypatch)

    await _seed_role(db_sessionmaker, TEST_USER_B.id, role="admin")
    switch_user(TEST_USER_B)
    response = api_client.post(
        f"/api/projects/{project['id']}/scans", json={"target": "https://example.com"}
    )
    assert response.status_code == 201


def test_get_scan_from_a_different_project_is_404(api_client, monkeypatch):
    workspace = _create_workspace(api_client)
    project_a = _create_project(api_client, workspace["id"])
    project_b = _create_project(api_client, workspace["id"])
    _patch_scan_url(monkeypatch)

    scan = api_client.post(
        f"/api/projects/{project_a['id']}/scans", json={"target": "https://example.com"}
    ).json()

    response = api_client.get(f"/api/projects/{project_b['id']}/scans/{scan['id']}")
    assert response.status_code == 404


def test_scans_require_authentication(unauthenticated_client):
    response = unauthenticated_client.get(f"/api/projects/{uuid.uuid4()}/scans")
    assert response.status_code == 401
