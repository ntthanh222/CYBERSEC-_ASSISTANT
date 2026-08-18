"""Asset inventory API: CRUD, filters/pagination, and ownership isolation."""
from backend.tests.conftest import TEST_USER_B


def _asset_payload(**overrides) -> dict:
    payload = {
        "name": "Core Finance DB Server",
        "type": "database",
        "hostname": "fin-db-prod.internal",
        "ip_address": "10.100.20.14",
        "operating_system": "RHEL 8.6",
        "owner": "Finance Dept",
        "department": "Finance",
        "business_criticality": "critical",
        "internet_exposed": False,
        "description": "Main production database.",
        "linked_cves": ["CVE-2021-44228"],
        "patch_status": "in_progress",
    }
    payload.update(overrides)
    return payload


def test_create_asset_returns_the_created_record(api_client):
    response = api_client.post("/api/assets", json=_asset_payload())
    assert response.status_code == 201
    body = response.json()
    assert body["id"]
    assert body["name"] == "Core Finance DB Server"
    assert body["linked_cves"] == ["CVE-2021-44228"]
    assert body["created_at"]
    assert body["updated_at"]


def test_created_asset_appears_in_the_list(api_client):
    api_client.post("/api/assets", json=_asset_payload())
    page = api_client.get("/api/assets").json()
    assert page["total"] == 1
    assert page["items"][0]["name"] == "Core Finance DB Server"


def test_get_one_asset_by_id(api_client):
    created = api_client.post("/api/assets", json=_asset_payload()).json()
    detail = api_client.get(f"/api/assets/{created['id']}")
    assert detail.status_code == 200
    assert detail.json()["hostname"] == "fin-db-prod.internal"


def test_get_nonexistent_asset_is_404(api_client):
    response = api_client.get("/api/assets/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404
    assert response.json()["error"] == "not_found"


def test_create_rejects_missing_required_field(api_client):
    payload = _asset_payload()
    del payload["hostname"]
    response = api_client.post("/api/assets", json=payload)
    assert response.status_code == 422


def test_create_rejects_invalid_type(api_client):
    response = api_client.post("/api/assets", json=_asset_payload(type="not_a_real_type"))
    assert response.status_code == 422


def test_create_rejects_invalid_business_criticality(api_client):
    response = api_client.post("/api/assets", json=_asset_payload(business_criticality="extreme"))
    assert response.status_code == 422


def test_list_filters_by_type(api_client):
    api_client.post("/api/assets", json=_asset_payload(type="database", hostname="db-1"))
    api_client.post("/api/assets", json=_asset_payload(type="server", hostname="srv-1"))
    page = api_client.get("/api/assets?type=server").json()
    assert page["total"] == 1
    assert page["items"][0]["hostname"] == "srv-1"


def test_list_filters_by_business_criticality(api_client):
    api_client.post(
        "/api/assets", json=_asset_payload(business_criticality="critical", hostname="a")
    )
    api_client.post("/api/assets", json=_asset_payload(business_criticality="low", hostname="b"))
    page = api_client.get("/api/assets?business_criticality=low").json()
    assert page["total"] == 1
    assert page["items"][0]["hostname"] == "b"


def test_list_supports_pagination(api_client):
    for i in range(3):
        api_client.post("/api/assets", json=_asset_payload(hostname=f"host-{i}"))
    page = api_client.get("/api/assets?page=1&page_size=2").json()
    assert page["total"] == 3
    assert len(page["items"]) == 2


def test_no_error_response_leaks_internals(api_client):
    response = api_client.get("/api/assets/not-a-uuid")
    assert response.status_code == 422
    body = response.json()
    assert "Traceback" not in str(body)
    assert "sqlalchemy" not in str(body).lower()


# ─── Auth gating ──────────────────────────────────────────────────────────────


def test_list_requires_authentication(unauthenticated_client):
    response = unauthenticated_client.get("/api/assets")
    assert response.status_code == 401


def test_create_requires_authentication(unauthenticated_client):
    response = unauthenticated_client.post("/api/assets", json=_asset_payload())
    assert response.status_code == 401


def test_malformed_bearer_token_is_401(unauthenticated_client):
    response = unauthenticated_client.get(
        "/api/assets", headers={"Authorization": "Bearer not-a-real-jwt"}
    )
    assert response.status_code == 401


# ─── Cross-user isolation (IDOR) ────────────────────────────────────────────


def test_user_cannot_read_another_users_asset(api_client, switch_user):
    created = api_client.post("/api/assets", json=_asset_payload()).json()

    switch_user(TEST_USER_B)
    response = api_client.get(f"/api/assets/{created['id']}")
    assert response.status_code == 404


def test_user_cannot_see_another_users_asset_in_list(api_client, switch_user):
    api_client.post("/api/assets", json=_asset_payload())

    switch_user(TEST_USER_B)
    page = api_client.get("/api/assets").json()
    assert page["total"] == 0


def test_each_user_only_sees_their_own_assets(api_client, switch_user):
    api_client.post("/api/assets", json=_asset_payload(hostname="user-a-host"))

    switch_user(TEST_USER_B)
    api_client.post("/api/assets", json=_asset_payload(hostname="user-b-host"))
    b_page = api_client.get("/api/assets").json()
    assert b_page["total"] == 1
    assert b_page["items"][0]["hostname"] == "user-b-host"
