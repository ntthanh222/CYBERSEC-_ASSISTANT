"""CVE API routes end to end, with the provider swapped for the fixture."""
from backend.api import cves as cves_module
from backend.providers.cve.fixture import FixtureCVEProvider
from backend.services.cve import CveLookupService


def _use_fixture_provider(monkeypatch) -> None:
    monkeypatch.setattr(
        cves_module,
        "CveLookupService",
        lambda *args, **kwargs: CveLookupService(provider=FixtureCVEProvider()),
    )
    monkeypatch.setattr("backend.services.cve.get_redis", lambda: None)


def test_get_cve_returns_a_normalized_record(api_client, monkeypatch):
    _use_fixture_provider(monkeypatch)
    response = api_client.get("/api/cves/CVE-2021-44228")
    assert response.status_code == 200
    body = response.json()
    assert body["cve_id"] == "CVE-2021-44228"
    assert body["cvss_score"] == 10.0
    assert body["severity"] == "critical"
    assert body["cached"] is False
    assert body["fetched_at"]


def test_get_cve_rejects_a_malformed_id(api_client, monkeypatch):
    _use_fixture_provider(monkeypatch)
    response = api_client.get("/api/cves/not-a-cve")
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_request"


def test_get_cve_returns_404_for_an_unknown_id(api_client, monkeypatch):
    _use_fixture_provider(monkeypatch)
    response = api_client.get("/api/cves/CVE-2099-99999")
    assert response.status_code == 404
    assert response.json()["error"] == "not_found"


def test_get_cve_records_a_scan_history_row(api_client, monkeypatch):
    _use_fixture_provider(monkeypatch)
    api_client.get("/api/cves/CVE-2021-44228")

    page = api_client.get("/api/tools/scan-history?scan_type=cve_lookup").json()
    assert page["total"] == 1
    assert page["items"][0]["target"] == "CVE-2021-44228"
    assert page["items"][0]["status"] == "completed"


def test_get_cve_not_found_still_records_history_as_failed(api_client, monkeypatch):
    _use_fixture_provider(monkeypatch)
    api_client.get("/api/cves/CVE-2099-99999")

    page = api_client.get("/api/tools/scan-history?scan_type=cve_lookup").json()
    assert page["total"] == 1
    assert page["items"][0]["status"] == "failed"


def test_search_cves_returns_matching_records(api_client, monkeypatch):
    _use_fixture_provider(monkeypatch)
    response = api_client.get("/api/cves/search?q=log4j")
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert body["results"][0]["cve_id"] == "CVE-2021-44228"


def test_search_cves_requires_a_query(api_client):
    response = api_client.get("/api/cves/search")
    assert response.status_code == 422
