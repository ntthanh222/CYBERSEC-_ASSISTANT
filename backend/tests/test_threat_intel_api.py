"""Threat intelligence IOC API: real persistence, owner isolation, no fixtures."""
from datetime import UTC, datetime

from backend.tests.conftest import TEST_USER_B


def _payload(**overrides):
    now = datetime(2026, 8, 4, 2, 0, tzinfo=UTC).isoformat()
    payload = {
        "type": "domain",
        "value": "malware.example",
        "severity": "critical",
        "confidence": "high",
        "description": "Command and control domain observed by analyst.",
        "source": "manual analyst entry",
        "first_seen": now,
        "last_seen": now,
        "watchlist": False,
        "tags": ["c2"],
        "mitre_techniques": ["T1071.001"],
        "risk_timeline": [{"time": "now", "score": 95}],
    }
    payload.update(overrides)
    return payload


def test_ioc_crud_summary_filters_and_watchlist(api_client):
    created = api_client.post("/api/threat-intel/iocs", json=_payload())
    assert created.status_code == 201
    ioc = created.json()
    assert ioc["value"] == "malware.example"
    assert ioc["watchlist"] is False

    listed = api_client.get("/api/threat-intel/iocs?search=malware&type=domain&severity=critical")
    assert listed.status_code == 200
    assert listed.json()["total"] == 1

    detail = api_client.get(f"/api/threat-intel/iocs/{ioc['id']}")
    assert detail.status_code == 200
    assert detail.json()["mitre_techniques"] == ["T1071.001"]

    updated = api_client.patch(
        f"/api/threat-intel/iocs/{ioc['id']}/watchlist",
        json={"watchlist": True},
    )
    assert updated.status_code == 200
    assert updated.json()["watchlist"] is True

    watchlist = api_client.get("/api/threat-intel/iocs?watchlist=true")
    assert watchlist.status_code == 200
    assert watchlist.json()["total"] == 1

    summary = api_client.get("/api/threat-intel/summary")
    assert summary.status_code == 200
    body = summary.json()
    assert body["total"] == 1
    assert body["critical"] == 1
    assert body["watchlist"] == 1
    assert body["items"][0]["id"] == ioc["id"]


def test_iocs_are_owner_isolated(api_client, switch_user):
    created = api_client.post("/api/threat-intel/iocs", json=_payload(value="owned.example"))
    assert created.status_code == 201
    ioc_id = created.json()["id"]

    switch_user(TEST_USER_B)
    assert api_client.get(f"/api/threat-intel/iocs/{ioc_id}").status_code == 404
    listed = api_client.get("/api/threat-intel/iocs")
    assert listed.status_code == 200
    assert listed.json()["total"] == 0


def test_ioc_validation_and_duplicate_errors_are_safe(api_client):
    invalid = api_client.post(
        "/api/threat-intel/iocs",
        json=_payload(last_seen="2026-08-03T02:00:00Z"),
    )
    assert invalid.status_code == 400
    assert invalid.json()["message"] == "Thời điểm phát hiện cuối không thể trước thời điểm phát hiện đầu."

    assert api_client.post("/api/threat-intel/iocs", json=_payload()).status_code == 201
    duplicate = api_client.post("/api/threat-intel/iocs", json=_payload())
    assert duplicate.status_code == 409
    assert duplicate.json()["message"] == "Chỉ báo này đã tồn tại."


def test_ioc_routes_require_authentication(unauthenticated_client):
    response = unauthenticated_client.get("/api/threat-intel/iocs")
    assert response.status_code == 401


def test_ioc_detail_and_watchlist_404_for_unknown_id(api_client):
    unknown_id = "00000000-0000-4000-8000-000000000000"
    assert api_client.get(f"/api/threat-intel/iocs/{unknown_id}").status_code == 404
    response = api_client.patch(
        f"/api/threat-intel/iocs/{unknown_id}/watchlist", json={"watchlist": True}
    )
    assert response.status_code == 404
