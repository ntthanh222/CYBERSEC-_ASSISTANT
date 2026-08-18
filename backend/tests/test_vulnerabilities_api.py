"""Vulnerability management API tests."""
from datetime import UTC, datetime

from backend.tests.conftest import TEST_USER_B


def _payload(**overrides):
    now = datetime(2026, 8, 4, 3, 0, tzinfo=UTC).isoformat()
    payload = {
        "cve_id": "CVE-2026-10001",
        "title": "Example tracked vulnerability",
        "description": "Analyst-tracked vulnerability for remediation workflow.",
        "cvss": 8.8,
        "severity": "high",
        "published_date": now,
        "updated_date": now,
        "references": ["https://nvd.nist.gov/vuln/detail/CVE-2026-10001"],
        "affected_products": ["Example Product"],
        "remediation": "Apply vendor patch.",
        "watchlist": False,
    }
    payload.update(overrides)
    return payload


def test_vulnerability_crud_watchlist_and_patch_tasks(api_client):
    created = api_client.post("/api/vulnerabilities", json=_payload())
    assert created.status_code == 201
    vuln = created.json()
    assert vuln["cve_id"] == "CVE-2026-10001"

    listed = api_client.get("/api/vulnerabilities?search=10001&severity=high")
    assert listed.status_code == 200
    assert listed.json()["total"] == 1

    detail = api_client.get(f"/api/vulnerabilities/items/{vuln['id']}")
    assert detail.status_code == 200
    assert detail.json()["title"] == "Example tracked vulnerability"

    watched = api_client.patch(
        f"/api/vulnerabilities/items/{vuln['id']}/watchlist",
        json={"watchlist": True},
    )
    assert watched.status_code == 200
    assert watched.json()["watchlist"] is True

    watchlist = api_client.get("/api/vulnerabilities?watchlist=true")
    assert watchlist.status_code == 200
    assert watchlist.json()["total"] == 1

    auto_tasks = api_client.get("/api/vulnerabilities/patch-tasks/list")
    assert auto_tasks.status_code == 200
    assert auto_tasks.json()["total"] == 1
    auto_task = auto_tasks.json()["items"][0]
    assert auto_task["cve_id"] == "CVE-2026-10001"
    assert auto_task["status"] == "not_started"

    task = api_client.post(
        "/api/vulnerabilities/patch-tasks",
        json={
            "vulnerability_id": vuln["id"],
            "asset_name": "Finance Gateway",
            "status": "not_started",
        },
    )
    assert task.status_code == 201
    task_body = task.json()
    assert task_body["cve_id"] == "CVE-2026-10001"
    assert task_body["asset_name"] == "Finance Gateway"

    tasks = api_client.get("/api/vulnerabilities/patch-tasks/list")
    assert tasks.status_code == 200
    assert tasks.json()["total"] == 2

    moved = api_client.patch(
        f"/api/vulnerabilities/patch-tasks/{task_body['id']}",
        json={"status": "patched"},
    )
    assert moved.status_code == 200
    assert moved.json()["status"] == "updated"


def test_vulnerabilities_are_owner_isolated(api_client, switch_user):
    created = api_client.post("/api/vulnerabilities", json=_payload(cve_id="CVE-2026-10002"))
    assert created.status_code == 201
    vuln_id = created.json()["id"]

    switch_user(TEST_USER_B)
    assert api_client.get(f"/api/vulnerabilities/items/{vuln_id}").status_code == 404
    listed = api_client.get("/api/vulnerabilities")
    assert listed.status_code == 200
    assert listed.json()["total"] == 0


def test_vulnerability_validation_and_duplicate_errors_are_safe(api_client):
    invalid = api_client.post(
        "/api/vulnerabilities",
        json=_payload(updated_date="2026-08-03T03:00:00Z"),
    )
    assert invalid.status_code == 400
    assert invalid.json()["message"] == "Ngày cập nhật không thể trước ngày công bố."

    assert api_client.post("/api/vulnerabilities", json=_payload()).status_code == 201
    duplicate = api_client.post("/api/vulnerabilities", json=_payload())
    assert duplicate.status_code == 409
    assert duplicate.json()["message"] == "Lỗ hổng này đã được theo dõi."


def test_vulnerability_routes_require_authentication(unauthenticated_client):
    response = unauthenticated_client.get("/api/vulnerabilities")
    assert response.status_code == 401


def test_vulnerability_watchlist_404_for_unknown_id(api_client):
    response = api_client.patch(
        "/api/vulnerabilities/items/00000000-0000-4000-8000-000000000000/watchlist",
        json={"watchlist": True},
    )
    assert response.status_code == 404


def test_patch_task_create_404_for_unknown_vulnerability(api_client):
    response = api_client.post(
        "/api/vulnerabilities/patch-tasks",
        json={
            "vulnerability_id": "00000000-0000-4000-8000-000000000000",
            "asset_name": "Finance Gateway",
            "status": "not_started",
        },
    )
    assert response.status_code == 404


def test_patch_task_status_404_for_unknown_task(api_client):
    response = api_client.patch(
        "/api/vulnerabilities/patch-tasks/00000000-0000-4000-8000-000000000000",
        json={"status": "patched"},
    )
    assert response.status_code == 404


def test_vulnerability_detail_404_for_unknown_id(api_client):
    response = api_client.get("/api/vulnerabilities/items/00000000-0000-4000-8000-000000000000")
    assert response.status_code == 404
