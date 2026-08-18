"""Notification center API tests."""

from backend.tests.conftest import TEST_USER_B


def _payload(**overrides):
    payload = {
        "title": "New critical alert",
        "body": "A critical severity alert was raised.",
        "category": "alert",
        "severity": "critical",
        "source_ref": "alert:1234",
    }
    payload.update(overrides)
    return payload


def test_notification_create_list_detail_and_mark_read(api_client):
    created = api_client.post("/api/notifications", json=_payload())
    assert created.status_code == 201
    notification = created.json()
    assert notification["is_read"] is False
    assert notification["severity"] == "critical"

    listed = api_client.get("/api/notifications")
    assert listed.status_code == 200
    body = listed.json()
    assert body["total"] == 1
    assert body["unread_count"] == 1

    detail = api_client.get(f"/api/notifications/{notification['id']}")
    assert detail.status_code == 200
    assert detail.json()["title"] == "New critical alert"

    marked = api_client.patch(
        f"/api/notifications/{notification['id']}/read", json={"is_read": True}
    )
    assert marked.status_code == 200
    assert marked.json()["is_read"] is True

    listed_after = api_client.get("/api/notifications")
    assert listed_after.json()["unread_count"] == 0


def test_notifications_unread_only_filter(api_client):
    api_client.post("/api/notifications", json=_payload(title="First"))
    second = api_client.post("/api/notifications", json=_payload(title="Second")).json()
    api_client.patch(f"/api/notifications/{second['id']}/read", json={"is_read": True})

    unread = api_client.get("/api/notifications?unread_only=true")
    assert unread.status_code == 200
    body = unread.json()
    assert body["total"] == 1
    assert body["items"][0]["title"] == "First"


def test_notifications_are_owner_isolated(api_client, switch_user):
    created = api_client.post("/api/notifications", json=_payload())
    assert created.status_code == 201
    notification_id = created.json()["id"]

    switch_user(TEST_USER_B)
    assert api_client.get(f"/api/notifications/{notification_id}").status_code == 404
    listed = api_client.get("/api/notifications")
    assert listed.status_code == 200
    assert listed.json()["total"] == 0


def test_notification_validation_is_safe(api_client):
    invalid = api_client.post("/api/notifications", json=_payload(category="unknown"))
    assert invalid.status_code == 422
    assert invalid.json()["message"] == "Invalid request."


def test_notification_routes_require_authentication(unauthenticated_client):
    assert unauthenticated_client.get("/api/notifications").status_code == 401
