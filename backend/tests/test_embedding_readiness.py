"""Embedding readiness state and its exposure via /api/system/health."""
from backend.core import embedding_readiness as er


def setup_function():
    er._reset_for_tests()


def teardown_function():
    er._reset_for_tests()


def test_starts_not_started():
    state = er.get_embedding_readiness()
    assert state == {"status": "not_started", "elapsed_seconds": None, "error": None}


def test_warming_then_ready_tracks_elapsed_time():
    er.mark_warming()
    warming_state = er.get_embedding_readiness()
    assert warming_state["status"] == "warming"
    assert warming_state["elapsed_seconds"] is not None
    assert warming_state["error"] is None

    er.mark_ready()
    ready_state = er.get_embedding_readiness()
    assert ready_state["status"] == "ready"
    assert ready_state["elapsed_seconds"] is not None
    assert ready_state["elapsed_seconds"] >= 0
    assert ready_state["error"] is None


def test_failed_records_a_safe_reason_not_a_raw_exception():
    er.mark_warming()
    er.mark_failed("ProviderUnavailableError")

    state = er.get_embedding_readiness()
    assert state["status"] == "failed"
    assert state["error"] == "ProviderUnavailableError"


def test_system_health_exposes_embedding_field(client, monkeypatch):
    async def _healthy(*_a, **_kw):
        return {"status": "healthy", "latency_ms": 1.0}

    monkeypatch.setattr("backend.api.system.check_database", _healthy)
    monkeypatch.setattr("backend.api.system.check_redis", _healthy)
    er.mark_warming()

    response = client.get("/api/system/health")

    assert response.status_code == 200
    body = response.json()
    assert body["embedding"]["status"] == "warming"


def test_embedding_warming_does_not_downgrade_overall_status(client, monkeypatch):
    async def _healthy(*_a, **_kw):
        return {"status": "healthy", "latency_ms": 1.0}

    monkeypatch.setattr("backend.api.system.check_database", _healthy)
    monkeypatch.setattr("backend.api.system.check_redis", _healthy)
    monkeypatch.setattr("backend.api.system.check_migration", _healthy)
    monkeypatch.setattr("backend.api.system.check_pgvector", _healthy)
    monkeypatch.setattr(
        "backend.api.system.check_local_auth_secret",
        lambda *_a, **_kw: {"status": "healthy", "latency_ms": 1.0},
    )
    er.mark_warming()

    response = client.get("/api/system/health")

    assert response.json()["status"] == "healthy"
