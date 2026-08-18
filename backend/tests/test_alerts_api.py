"""Alert center API tests."""
from backend.database.models.rbac import UserRole

from backend.tests.conftest import TEST_USER_A, TEST_USER_B


def _payload(**overrides):
    payload = {
        "title": "Suspicious outbound connection",
        "description": "Endpoint attempted outbound connection to a known bad host.",
        "severity": "high",
        "source": "EDR",
        "status": "new",
        "asset_name": "Finance Laptop",
        "ioc_value": "malware.example",
        "evidence": "process=browser.exe dest=malware.example",
    }
    payload.update(overrides)
    return payload


def test_alert_crud_filters_and_status(api_client):
    created = api_client.post("/api/alerts", json=_payload())
    assert created.status_code == 201
    alert = created.json()
    assert alert["title"] == "Suspicious outbound connection"

    listed = api_client.get("/api/alerts?search=outbound&severity=high&status=new")
    assert listed.status_code == 200
    assert listed.json()["total"] == 1

    detail = api_client.get(f"/api/alerts/{alert['id']}")
    assert detail.status_code == 200
    assert detail.json()["evidence"].startswith("process=")

    updated = api_client.patch(
        f"/api/alerts/{alert['id']}/status",
        json={"status": "investigating"},
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "investigating"


def test_alerts_are_owner_isolated(api_client, switch_user):
    created = api_client.post("/api/alerts", json=_payload(title="Owner-only alert"))
    assert created.status_code == 201
    alert_id = created.json()["id"]

    switch_user(TEST_USER_B)
    assert api_client.get(f"/api/alerts/{alert_id}").status_code == 404
    listed = api_client.get("/api/alerts")
    assert listed.status_code == 200
    assert listed.json()["total"] == 0


def test_alert_validation_is_safe(api_client):
    invalid = api_client.post("/api/alerts", json=_payload(severity="urgent"))
    assert invalid.status_code == 422
    assert invalid.json()["message"] == "Invalid request."


def test_alert_routes_require_authentication(unauthenticated_client):
    response = unauthenticated_client.get("/api/alerts")
    assert response.status_code == 401


def test_alert_detail_and_status_404_for_unknown_id(api_client):
    unknown_id = "00000000-0000-4000-8000-000000000000"
    assert api_client.get(f"/api/alerts/{unknown_id}").status_code == 404
    response = api_client.patch(
        f"/api/alerts/{unknown_id}/status", json={"status": "acknowledged"}
    )
    assert response.status_code == 404


async def test_a_critical_alert_notifies_admin_tier_users(api_client, db_sessionmaker):
    """Real event -> real notification: an admin-tier user gets a
    notification when a high/critical alert is created - not just a row
    sitting in a table nothing ever populates."""
    async with db_sessionmaker() as session:
        session.add(UserRole(user_id=TEST_USER_A.id, role="admin", is_active=True))
        await session.commit()

    created = api_client.post("/api/alerts", json=_payload(severity="critical"))
    assert created.status_code == 201

    notifications = api_client.get("/api/notifications").json()
    assert notifications["total"] >= 1
    matching = [n for n in notifications["items"] if n["category"] == "alert"]
    assert matching
    assert matching[0]["severity"] == "critical"


async def test_a_low_severity_alert_does_not_notify(api_client, db_sessionmaker):
    async with db_sessionmaker() as session:
        session.add(UserRole(user_id=TEST_USER_A.id, role="admin", is_active=True))
        await session.commit()

    api_client.post("/api/alerts", json=_payload(severity="low"))

    notifications = api_client.get("/api/notifications").json()
    assert not [n for n in notifications["items"] if n["category"] == "alert"]
