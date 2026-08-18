def test_health_returns_healthy_without_touching_dependencies(client, monkeypatch):
    async def _boom(*_args, **_kwargs):
        raise AssertionError("/health must not probe dependencies")

    monkeypatch.setattr("backend.api.system.check_database", _boom)
    monkeypatch.setattr("backend.api.system.check_redis", _boom)

    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "healthy"
    assert body["service"] == "backend"
