def test_unhandled_exception_returns_safe_response(monkeypatch):
    from fastapi.testclient import TestClient

    from backend.main import app

    def _boom(*_args, **_kwargs):
        raise RuntimeError(
            "postgresql+psycopg://cybersec:supersecret@postgres:5432/db unreachable"
        )

    monkeypatch.setattr("backend.api.system.aggregate_status", _boom)

    # Starlette's ServerErrorMiddleware re-raises after building the response
    # so servers/tests can still log it; raise_server_exceptions=False lets
    # us inspect the sanitized response our handler actually sent the client.
    with TestClient(app, raise_server_exceptions=False) as unsafe_client:
        response = unsafe_client.get("/api/system/health")

    assert response.status_code == 500
    body = response.json()
    assert body["error"] == "internal_server_error"
    assert body["request_id"]
    assert response.headers["X-Request-ID"] == body["request_id"]
    assert "supersecret" not in response.text
    assert "Traceback" not in response.text
    assert "RuntimeError" not in response.text
    assert "postgresql" not in response.text


def test_unknown_route_returns_json_with_request_id(client):
    response = client.get("/does-not-exist")

    assert response.status_code == 404
    body = response.json()
    assert body["error"] == "http_error"
    assert body["request_id"]
