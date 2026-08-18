import re

UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE
)


def test_request_id_is_generated_when_absent(client):
    response = client.get("/health")
    assert "X-Request-ID" in response.headers
    assert UUID_RE.match(response.headers["X-Request-ID"])


def test_request_id_is_preserved_when_valid(client):
    response = client.get("/health", headers={"X-Request-ID": "client-supplied-id-123"})
    assert response.headers["X-Request-ID"] == "client-supplied-id-123"


def test_request_id_is_replaced_when_invalid(client):
    malicious = "not valid\r\nX-Injected: yes"
    response = client.get("/health", headers={"X-Request-ID": malicious})
    assert response.headers["X-Request-ID"] != malicious
    assert UUID_RE.match(response.headers["X-Request-ID"])


def test_system_health_response_echoes_request_id(client):
    response = client.get("/api/system/health", headers={"X-Request-ID": "trace-42"})
    assert response.headers["X-Request-ID"] == "trace-42"
    assert response.json()["request_id"] == "trace-42"
