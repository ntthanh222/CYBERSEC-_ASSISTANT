"""MITRE coverage API tests."""

from backend.tests.conftest import TEST_USER_B


def _payload(**overrides):
    payload = {
        "technique_id": "T1071.001",
        "tactic": "Command and Control",
        "name": "Web Protocols",
        "description": "Application layer protocol over web channels.",
        "detection": "Review proxy and DNS logs.",
        "mitigation": "Restrict egress and inspect outbound traffic.",
        "coverage_status": "partial",
        "data_sources": ["Proxy logs"],
    }
    payload.update(overrides)
    return payload


def test_mitre_coverage_crud_matrix_and_update(api_client):
    created = api_client.post("/api/mitre/techniques", json=_payload())
    assert created.status_code == 201
    technique = created.json()
    assert technique["technique_id"] == "T1071.001"

    listed = api_client.get("/api/mitre/techniques?search=web&coverage_status=partial")
    assert listed.status_code == 200
    assert listed.json()["total"] == 1

    matrix = api_client.get("/api/mitre/matrix")
    assert matrix.status_code == 200
    assert matrix.json()["summary"]["partial"] == 1
    assert "Command and Control" in matrix.json()["tactics"]

    detail = api_client.get(f"/api/mitre/techniques/{technique['id']}")
    assert detail.status_code == 200
    assert detail.json()["detection"] == "Review proxy and DNS logs."

    updated = api_client.patch(
        f"/api/mitre/techniques/{technique['id']}",
        json={
            "detection": "Correlate proxy logs with EDR process trees.",
            "mitigation": "Block unapproved destinations.",
            "coverage_status": "covered",
            "data_sources": ["Proxy logs", "EDR"],
        },
    )
    assert updated.status_code == 200
    assert updated.json()["coverage_status"] == "covered"


def test_mitre_records_are_owner_isolated(api_client, switch_user):
    created = api_client.post("/api/mitre/techniques", json=_payload())
    assert created.status_code == 201
    record_id = created.json()["id"]

    switch_user(TEST_USER_B)
    assert api_client.get(f"/api/mitre/techniques/{record_id}").status_code == 404
    matrix = api_client.get("/api/mitre/matrix")
    assert matrix.status_code == 200
    assert matrix.json()["summary"]["total"] == 0


def test_mitre_duplicate_and_validation_are_safe(api_client):
    assert api_client.post("/api/mitre/techniques", json=_payload()).status_code == 201
    duplicate = api_client.post("/api/mitre/techniques", json=_payload(name="Duplicate"))
    assert duplicate.status_code == 409
    assert duplicate.json()["message"] == "Kỹ thuật này đã được theo dõi."

    invalid = api_client.post("/api/mitre/techniques", json=_payload(technique_id="BAD"))
    assert invalid.status_code == 422
    assert invalid.json()["message"] == "Invalid request."


def test_mitre_routes_require_authentication(unauthenticated_client):
    response = unauthenticated_client.get("/api/mitre/matrix")
    assert response.status_code == 401


_UNKNOWN_ID = "00000000-0000-4000-8000-000000000000"


def test_mitre_detail_404_for_unknown_id(api_client):
    assert api_client.get(f"/api/mitre/techniques/{_UNKNOWN_ID}").status_code == 404


def test_mitre_update_404_for_unknown_id(api_client):
    response = api_client.patch(
        f"/api/mitre/techniques/{_UNKNOWN_ID}",
        json={
            "detection": "n/a",
            "mitigation": "n/a",
            "coverage_status": "covered",
            "data_sources": [],
        },
    )
    assert response.status_code == 404
