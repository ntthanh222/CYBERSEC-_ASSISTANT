def test_cors_allows_configured_origin(client):
    response = client.get(
        "/api/system/health", headers={"Origin": "http://localhost:3000"}
    )
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"
    exposed = response.headers.get("access-control-expose-headers", "")
    assert "X-Request-ID" in exposed
    assert "X-Correlation-ID" in exposed


def test_cors_allows_correlation_id_preflight(client):
    response = client.options(
        "/api/system/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "X-Correlation-ID",
        },
    )
    assert response.status_code == 200
    allowed_headers = response.headers.get("access-control-allow-headers", "")
    assert "X-Correlation-ID" in allowed_headers


def test_cors_rejects_unlisted_origin_preflight(client):
    response = client.options(
        "/api/system/health",
        headers={
            "Origin": "http://evil.example",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 400
    assert "access-control-allow-origin" not in {k.lower() for k in response.headers}


def test_cors_no_header_for_unlisted_origin_on_actual_request(client):
    response = client.get("/api/system/health", headers={"Origin": "http://evil.example"})
    assert "access-control-allow-origin" not in {k.lower() for k in response.headers}
