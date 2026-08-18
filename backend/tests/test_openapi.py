def test_openapi_json_is_valid_and_documented(client):
    response = client.get("/openapi.json")
    assert response.status_code == 200
    spec = response.json()

    assert spec["info"]["title"] == "CyberSec Assistant API"
    assert spec["info"]["version"]
    assert spec["info"]["description"]

    assert "/health" in spec["paths"]
    assert "/api/system/health" in spec["paths"]

    health_get = spec["paths"]["/health"]["get"]
    system_get = spec["paths"]["/api/system/health"]["get"]
    assert health_get["summary"] != system_get["summary"]
    assert health_get["description"]
    assert system_get["description"]
    assert "responses" in health_get and "200" in health_get["responses"]
    assert "responses" in system_get and "200" in system_get["responses"]

    # /metrics is intentionally excluded from the public API schema.
    assert "/metrics" not in spec["paths"]


def test_swagger_ui_is_served(client):
    response = client.get("/docs")
    assert response.status_code == 200
    assert "swagger-ui" in response.text.lower()


def test_redoc_is_served(client):
    response = client.get("/redoc")
    assert response.status_code == 200
    assert "redoc" in response.text.lower()
