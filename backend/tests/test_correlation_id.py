import re

UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE
)


def test_correlation_id_is_generated_when_absent(client):
    response = client.get("/health")
    assert "X-Correlation-ID" in response.headers
    assert UUID_RE.match(response.headers["X-Correlation-ID"])


def test_correlation_id_is_preserved_when_valid(client):
    response = client.get("/health", headers={"X-Correlation-ID": "op-chain-123"})
    assert response.headers["X-Correlation-ID"] == "op-chain-123"


def test_correlation_id_is_replaced_when_invalid(client):
    malicious = "bad\r\nX-Injected: yes"
    response = client.get("/health", headers={"X-Correlation-ID": malicious})
    assert response.headers["X-Correlation-ID"] != malicious
    assert UUID_RE.match(response.headers["X-Correlation-ID"])


def test_correlation_id_independent_from_request_id(client):
    response = client.get(
        "/health",
        headers={"X-Request-ID": "req-1", "X-Correlation-ID": "corr-1"},
    )
    assert response.headers["X-Request-ID"] == "req-1"
    assert response.headers["X-Correlation-ID"] == "corr-1"
