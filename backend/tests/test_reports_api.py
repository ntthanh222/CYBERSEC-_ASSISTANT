"""Reports center API tests."""

from backend.tests.conftest import TEST_USER_B


def _payload(**overrides):
    payload = {
        "title": "Weekly SOC Summary",
        "category": "executive",
        "format": "markdown",
        "sections": ["Executive Summary", "Open Actions"],
        "scope": "Week 31 SOC review.",
    }
    payload.update(overrides)
    return payload


def test_report_templates_create_list_detail_and_download(api_client):
    templates = api_client.get("/api/reports/templates")
    assert templates.status_code == 200
    assert any(item["id"] == "executive-overview" for item in templates.json())

    created = api_client.post("/api/reports", json=_payload())
    assert created.status_code == 201
    report = created.json()
    assert report["status"] == "completed"
    assert "# Weekly SOC Summary" in report["content"]

    listed = api_client.get("/api/reports?category=executive")
    assert listed.status_code == 200
    assert listed.json()["total"] == 1

    detail = api_client.get(f"/api/reports/{report['id']}")
    assert detail.status_code == 200
    assert detail.json()["sections"] == ["Executive Summary", "Open Actions"]

    download = api_client.get(f"/api/reports/{report['id']}/download")
    assert download.status_code == 200
    assert "Weekly SOC Summary" in download.text
    assert download.headers["content-type"].startswith("text/markdown")


def test_csv_report_downloads_real_csv_content(api_client):
    created = api_client.post("/api/reports", json=_payload(format="csv", category="technical"))
    assert created.status_code == 201
    report = created.json()
    assert report["format"] == "csv"

    download = api_client.get(f"/api/reports/{report['id']}/download")
    assert download.status_code == 200
    assert download.headers["content-type"].startswith("text/csv")
    assert "title,category,section,line" in download.text


def test_reports_are_owner_isolated(api_client, switch_user):
    created = api_client.post("/api/reports", json=_payload())
    assert created.status_code == 201
    report_id = created.json()["id"]

    switch_user(TEST_USER_B)
    assert api_client.get(f"/api/reports/{report_id}").status_code == 404
    listed = api_client.get("/api/reports")
    assert listed.status_code == 200
    assert listed.json()["total"] == 0


def test_report_validation_is_safe(api_client):
    invalid = api_client.post("/api/reports", json=_payload(category="unknown"))
    assert invalid.status_code == 422
    assert invalid.json()["message"] == "Invalid request."


def test_report_routes_require_authentication(unauthenticated_client):
    assert unauthenticated_client.get("/api/reports").status_code == 401
