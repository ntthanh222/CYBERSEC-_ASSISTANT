"""Incident response API tests."""

from backend.database.models.rbac import UserRole

from backend.tests.conftest import TEST_USER_A, TEST_USER_B


def _payload(**overrides):
    payload = {
        "title": "Phishing infection containment",
        "description": "Endpoint contacted a suspicious domain after user click.",
        "severity": "medium",
        "status": "open",
        "assignee": "analyst@example.com",
        "asset_name": "Finance Laptop",
        "cve_id": "",
    }
    payload.update(overrides)
    return payload


def test_incident_crud_tasks_timeline_and_status(api_client):
    created = api_client.post("/api/incidents", json=_payload())
    assert created.status_code == 201
    incident = created.json()
    assert incident["title"] == "Phishing infection containment"

    listed = api_client.get("/api/incidents?search=phishing&severity=medium&status=open")
    assert listed.status_code == 200
    assert listed.json()["total"] == 1

    task = api_client.post(
        f"/api/incidents/{incident['id']}/tasks",
        json={"title": "Block domain", "owner": "analyst@example.com"},
    )
    assert task.status_code == 201
    task_body = task.json()
    assert task_body["status"] == "pending"

    task_update = api_client.patch(
        f"/api/incidents/tasks/{task_body['id']}",
        json={"status": "completed"},
    )
    assert task_update.status_code == 200
    assert task_update.json()["status"] == "completed"

    note = api_client.post(
        f"/api/incidents/{incident['id']}/notes", json={"message": "Host isolated."}
    )
    assert note.status_code == 201
    assert note.json()["event_type"] == "note"

    updated = api_client.patch(
        f"/api/incidents/{incident['id']}/status", json={"status": "contained"}
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "contained"

    detail = api_client.get(f"/api/incidents/{incident['id']}")
    assert detail.status_code == 200
    assert len(detail.json()["tasks"]) == 1
    assert any(event["message"] == "Host isolated." for event in detail.json()["timeline"])


def test_incidents_are_owner_isolated(api_client, switch_user):
    created = api_client.post("/api/incidents", json=_payload(title="Owner-only incident"))
    assert created.status_code == 201
    incident_id = created.json()["id"]

    switch_user(TEST_USER_B)
    assert api_client.get(f"/api/incidents/{incident_id}").status_code == 404
    listed = api_client.get("/api/incidents")
    assert listed.status_code == 200
    assert listed.json()["total"] == 0


def test_incident_validation_is_safe(api_client):
    invalid = api_client.post("/api/incidents", json=_payload(severity="urgent"))
    assert invalid.status_code == 422
    assert invalid.json()["message"] == "Invalid request."


def test_incident_routes_require_authentication(unauthenticated_client):
    response = unauthenticated_client.get("/api/incidents")
    assert response.status_code == 401


_UNKNOWN_ID = "00000000-0000-4000-8000-000000000000"


def test_incident_404_for_unknown_id(api_client):
    assert api_client.get(f"/api/incidents/{_UNKNOWN_ID}").status_code == 404


def test_incident_status_update_404_for_unknown_id(api_client):
    response = api_client.patch(f"/api/incidents/{_UNKNOWN_ID}/status", json={"status": "closed"})
    assert response.status_code == 404


def test_incident_task_create_404_for_unknown_incident(api_client):
    response = api_client.post(
        f"/api/incidents/{_UNKNOWN_ID}/tasks", json={"title": "x", "owner": "a@example.com"}
    )
    assert response.status_code == 404


def test_incident_task_status_404_for_unknown_task(api_client):
    response = api_client.patch(
        f"/api/incidents/tasks/{_UNKNOWN_ID}", json={"status": "completed"}
    )
    assert response.status_code == 404


def test_incident_note_404_for_unknown_incident(api_client):
    response = api_client.post(
        f"/api/incidents/{_UNKNOWN_ID}/notes", json={"message": "test"}
    )
    assert response.status_code == 404


async def test_a_critical_incident_notifies_admin_tier_users(api_client, db_sessionmaker):
    async with db_sessionmaker() as session:
        session.add(UserRole(user_id=TEST_USER_A.id, role="admin", is_active=True))
        await session.commit()

    created = api_client.post("/api/incidents", json=_payload(severity="critical"))
    assert created.status_code == 201

    notifications = api_client.get("/api/notifications").json()
    matching = [n for n in notifications["items"] if n["category"] == "incident"]
    assert matching
    assert matching[0]["severity"] == "critical"


async def test_a_medium_severity_incident_does_not_notify(api_client, db_sessionmaker):
    async with db_sessionmaker() as session:
        session.add(UserRole(user_id=TEST_USER_A.id, role="admin", is_active=True))
        await session.commit()

    api_client.post("/api/incidents", json=_payload(severity="medium"))

    notifications = api_client.get("/api/notifications").json()
    assert not [n for n in notifications["items"] if n["category"] == "incident"]
