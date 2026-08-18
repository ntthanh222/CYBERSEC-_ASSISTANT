async def _healthy(*_args, **_kwargs):
    return {"status": "healthy", "latency_ms": 1.23}


async def _unavailable(*_args, **_kwargs):
    return {"status": "unavailable", "latency_ms": 5.0}


def _sync_healthy(*_args, **_kwargs):
    return {"status": "healthy", "latency_ms": 1.23}


def _patch_probes(monkeypatch, db_result, redis_result):
    monkeypatch.setattr("backend.api.system.check_database", db_result)
    monkeypatch.setattr("backend.api.system.check_redis", redis_result)
    monkeypatch.setattr("backend.api.system.check_migration", _healthy)
    monkeypatch.setattr("backend.api.system.check_pgvector", _healthy)
    monkeypatch.setattr("backend.api.system.check_local_auth_secret", _sync_healthy)


def test_system_health_schema_and_all_healthy(client, monkeypatch):
    _patch_probes(monkeypatch, _healthy, _healthy)

    response = client.get("/api/system/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "healthy"
    assert set(body["checks"].keys()) == {
        "backend",
        "database",
        "redis",
        "migration",
        "pgvector",
        "local_auth_secret",
    }
    for check in body["checks"].values():
        assert check["status"] in {"healthy", "degraded", "unavailable", "unknown"}
    assert "timestamp" in body
    assert "request_id" in body and body["request_id"]


def test_system_health_stale_migration_is_unavailable_not_healthy(client, monkeypatch):
    async def _stale_migration(*_args, **_kwargs):
        return {"status": "unavailable", "latency_ms": 1.0}

    _patch_probes(monkeypatch, _healthy, _healthy)
    monkeypatch.setattr("backend.api.system.check_migration", _stale_migration)

    body = client.get("/api/system/health").json()
    assert body["checks"]["migration"]["status"] == "unavailable"
    assert body["status"] != "healthy"


def test_system_health_missing_pgvector_is_unavailable_not_healthy(client, monkeypatch):
    async def _missing_pgvector(*_args, **_kwargs):
        return {"status": "unavailable", "latency_ms": 1.0}

    _patch_probes(monkeypatch, _healthy, _healthy)
    monkeypatch.setattr("backend.api.system.check_pgvector", _missing_pgvector)

    body = client.get("/api/system/health").json()
    assert body["checks"]["pgvector"]["status"] == "unavailable"
    assert body["status"] != "healthy"


def test_system_health_local_auth_secret_unknown_outside_local_does_not_degrade(
    client, monkeypatch
):
    def _unknown(*_args, **_kwargs):
        return {"status": "unknown", "latency_ms": None}

    _patch_probes(monkeypatch, _healthy, _healthy)
    monkeypatch.setattr("backend.api.system.check_local_auth_secret", _unknown)

    body = client.get("/api/system/health").json()
    assert body["checks"]["local_auth_secret"]["status"] == "unknown"
    assert body["status"] == "healthy"


def test_system_health_database_unavailable_does_not_crash_backend(client, monkeypatch):
    _patch_probes(monkeypatch, _unavailable, _healthy)

    response = client.get("/api/system/health")

    assert response.status_code == 200
    body = response.json()
    assert body["checks"]["database"]["status"] == "unavailable"
    assert body["status"] == "degraded"


def test_system_health_redis_unavailable_does_not_crash_backend(client, monkeypatch):
    _patch_probes(monkeypatch, _healthy, _unavailable)

    response = client.get("/api/system/health")

    assert response.status_code == 200
    body = response.json()
    assert body["checks"]["redis"]["status"] == "unavailable"
    assert body["status"] == "degraded"


def test_system_health_both_dependencies_down(client, monkeypatch):
    _patch_probes(monkeypatch, _unavailable, _unavailable)
    monkeypatch.setattr("backend.api.system.check_migration", _unavailable)
    monkeypatch.setattr("backend.api.system.check_pgvector", _unavailable)
    monkeypatch.setattr(
        "backend.api.system.check_local_auth_secret",
        lambda *_a, **_kw: {"status": "unavailable", "latency_ms": None},
    )

    response = client.get("/api/system/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "unavailable"


def test_system_health_never_hardcodes_healthy(monkeypatch, client):
    """The status must come from the real probe result, not a constant."""
    _patch_probes(monkeypatch, _unavailable, _unavailable)
    body = client.get("/api/system/health").json()
    assert body["checks"]["database"]["status"] != "healthy"
    assert body["checks"]["redis"]["status"] != "healthy"
