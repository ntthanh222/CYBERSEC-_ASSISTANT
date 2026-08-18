"""URL scan API route: SSRF enforcement and scan-history recording end to end."""
import httpx

from backend.api import tools as tools_module
from backend.services import ssrf_guard


def _stub_resolve(monkeypatch, mapping: dict[str, tuple[str, ...]]) -> None:
    async def fake_resolve(hostname: str, port: int) -> tuple[str, ...]:
        return mapping[hostname]

    monkeypatch.setattr(ssrf_guard, "resolve_hostname", fake_resolve)


def _patch_scan_url(monkeypatch, handler) -> None:
    from backend.services import url_scanner

    original = url_scanner.scan_url

    async def wrapped(raw_url: str, *, transport=None):
        return await original(raw_url, transport=httpx.MockTransport(handler))

    monkeypatch.setattr(tools_module, "scan_url", wrapped)


def test_url_scan_blocks_localhost_with_400(api_client):
    response = api_client.post("/api/tools/url-scan", json={"url": "http://127.0.0.1/"})
    assert response.status_code == 400
    assert response.json()["error"] == "blocked_target"


def test_url_scan_blocks_a_private_ip_with_400(api_client):
    response = api_client.post("/api/tools/url-scan", json={"url": "http://10.0.0.5/"})
    assert response.status_code == 400
    assert response.json()["error"] == "blocked_target"


def test_url_scan_blocks_the_metadata_endpoint(api_client):
    response = api_client.post(
        "/api/tools/url-scan", json={"url": "http://169.254.169.254/latest/meta-data/"}
    )
    assert response.status_code == 400


def test_url_scan_rejects_a_malformed_url(api_client):
    response = api_client.post("/api/tools/url-scan", json={"url": "not a url"})
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_request"


def test_url_scan_blocked_target_is_recorded_in_history(api_client):
    api_client.post("/api/tools/url-scan", json={"url": "http://127.0.0.1/admin"})
    page = api_client.get("/api/tools/scan-history?scan_type=url_scan").json()
    assert page["total"] >= 1
    assert page["items"][0]["status"] == "failed"
    assert "Bị chặn" in page["items"][0]["summary"]


def test_url_scan_success_is_recorded_and_returned(api_client, monkeypatch):
    _stub_resolve(monkeypatch, {"example.com": ("93.184.216.34",)})

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "text/html"}, content=b"ok")

    _patch_scan_url(monkeypatch, handler)

    response = api_client.post("/api/tools/url-scan", json={"url": "https://example.com/"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "safe"
    assert body["id"]
    assert body["created_at"]

    detail = api_client.get(f"/api/tools/scan-history/{body['id']}")
    assert detail.status_code == 200
    assert detail.json()["scan_type"] == "url_scan"
    assert detail.json()["details"]["findings"] == []


def test_scan_history_supports_filtering_and_pagination(api_client, monkeypatch):
    _stub_resolve(monkeypatch, {"example.com": ("93.184.216.34",)})

    def ok_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"ok")

    _patch_scan_url(monkeypatch, ok_handler)

    for _ in range(3):
        api_client.post("/api/tools/url-scan", json={"url": "https://example.com/"})
    api_client.post("/api/tools/url-scan", json={"url": "http://127.0.0.1/"})

    completed = api_client.get(
        "/api/tools/scan-history?status=completed&page_size=2"
    ).json()
    assert completed["total"] == 3
    assert len(completed["items"]) == 2

    failed = api_client.get("/api/tools/scan-history?status=failed").json()
    assert failed["total"] == 1


def test_scan_history_detail_returns_404_for_unknown_id(api_client):
    response = api_client.get(
        "/api/tools/scan-history/11111111-2222-3333-4444-555555555555"
    )
    assert response.status_code == 404


def test_scan_history_delete_removes_the_record(api_client, monkeypatch):
    _stub_resolve(monkeypatch, {"example.com": ("93.184.216.34",)})

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"ok")

    _patch_scan_url(monkeypatch, handler)
    created = api_client.post(
        "/api/tools/url-scan", json={"url": "https://example.com/"}
    ).json()

    assert api_client.delete(f"/api/tools/scan-history/{created['id']}").status_code == 204
    assert api_client.get(f"/api/tools/scan-history/{created['id']}").status_code == 404


def test_scan_history_delete_returns_404_for_unknown_id(api_client):
    response = api_client.delete(
        "/api/tools/scan-history/11111111-2222-3333-4444-555555555555"
    )
    assert response.status_code == 404


def test_scan_history_never_contains_a_password_field(api_client, monkeypatch):
    _stub_resolve(monkeypatch, {"example.com": ("93.184.216.34",)})

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"ok")

    _patch_scan_url(monkeypatch, handler)
    api_client.post("/api/tools/url-scan", json={"url": "https://example.com/"})
    api_client.post("/api/tools/password-check", json={"password": "irrelevant-secret"})

    page = api_client.get("/api/tools/scan-history").json()
    assert all(item["scan_type"] != "password_check" for item in page["items"])
    assert "irrelevant-secret" not in str(page)
