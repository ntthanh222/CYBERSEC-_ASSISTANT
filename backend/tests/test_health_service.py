"""Direct unit tests for the dependency probes (no real DB/Redis needed).

Host-run pytest can't reach the `postgres`/`redis` Docker service names, so
the always-degraded path is what integration tests exercise. These tests
use lightweight fakes to cover the "unknown" (no engine/URL configured) and
"healthy" (dependency actually answers) branches that require a reachable
dependency in Docker to hit otherwise.
"""
import pytest

from backend.services import health


class _FakeConnection:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False

    async def execute(self, _stmt):
        return None


class _FakeEngine:
    def connect(self):
        return _FakeConnection()


class _TimingOutEngine:
    def connect(self):
        raise TimeoutError("simulated")


@pytest.mark.asyncio
async def test_check_database_returns_unknown_when_engine_is_none():
    result = await health.check_database(None)
    assert result == {"status": "unknown", "latency_ms": None}


@pytest.mark.asyncio
async def test_check_database_returns_healthy_when_query_succeeds():
    result = await health.check_database(_FakeEngine())
    assert result["status"] == "healthy"
    assert result["latency_ms"] is not None


@pytest.mark.asyncio
async def test_check_database_returns_unavailable_on_timeout():
    result = await health.check_database(_TimingOutEngine())
    assert result["status"] == "unavailable"


@pytest.mark.asyncio
async def test_check_redis_returns_unknown_when_url_is_none():
    result = await health.check_redis(None)
    assert result == {"status": "unknown", "latency_ms": None}


@pytest.mark.asyncio
async def test_check_redis_returns_healthy_when_ping_succeeds(monkeypatch):
    class _FakeRedisClient:
        async def ping(self):
            return True

        async def aclose(self):
            return None

    monkeypatch.setattr(health.aioredis, "from_url", lambda *a, **k: _FakeRedisClient())
    result = await health.check_redis("redis://fake:6379/0")
    assert result["status"] == "healthy"
    assert result["latency_ms"] is not None


@pytest.mark.asyncio
async def test_check_redis_returns_unavailable_when_ping_is_falsy(monkeypatch):
    class _FakeRedisClient:
        async def ping(self):
            return False

        async def aclose(self):
            return None

    monkeypatch.setattr(health.aioredis, "from_url", lambda *a, **k: _FakeRedisClient())
    result = await health.check_redis("redis://fake:6379/0")
    assert result["status"] == "unavailable"


def test_aggregate_status_all_healthy():
    checks = {"a": {"status": "healthy"}, "b": {"status": "healthy"}}
    assert health.aggregate_status(checks) == "healthy"


def test_aggregate_status_all_unavailable():
    checks = {"a": {"status": "unavailable"}, "b": {"status": "unavailable"}}
    assert health.aggregate_status(checks) == "unavailable"


def test_aggregate_status_mixed_is_degraded():
    checks = {"a": {"status": "healthy"}, "b": {"status": "unavailable"}}
    assert health.aggregate_status(checks) == "degraded"


class _FakeRow:
    def __init__(self, value):
        self._value = value

    def __getitem__(self, index):
        return self._value


class _FakeResult:
    def __init__(self, row):
        self._row = row

    def first(self):
        return self._row


class _FakeQueryConnection:
    def __init__(self, row):
        self._row = row

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False

    async def execute(self, _stmt):
        return _FakeResult(self._row)


class _FakeQueryEngine:
    def __init__(self, row):
        self._row = row

    def connect(self):
        return _FakeQueryConnection(self._row)


@pytest.mark.asyncio
async def test_check_migration_returns_unknown_when_engine_is_none():
    result = await health.check_migration(None)
    assert result == {"status": "unknown", "latency_ms": None}


@pytest.mark.asyncio
async def test_check_migration_healthy_when_at_expected_head():
    engine = _FakeQueryEngine(_FakeRow(health._expected_migration_revision()))
    result = await health.check_migration(engine)
    assert result["status"] == "healthy"


def test_expected_migration_revision_matches_real_head():
    """Guards against the old drift bug: a hardcoded constant that fell 10
    migrations behind. This must always equal the true Alembic head."""
    from alembic.config import Config as AlembicConfig
    from alembic.script import ScriptDirectory

    config = AlembicConfig(str(health._ALEMBIC_INI_PATH))
    config.set_main_option(
        "script_location", str(health._ALEMBIC_INI_PATH.parent / "database" / "migrations")
    )
    real_head = ScriptDirectory.from_config(config).get_current_head()
    assert health._expected_migration_revision() == real_head
    assert real_head is not None


@pytest.mark.asyncio
async def test_check_migration_unavailable_when_stale():
    engine = _FakeQueryEngine(_FakeRow("0001"))
    result = await health.check_migration(engine)
    assert result["status"] == "unavailable"


@pytest.mark.asyncio
async def test_check_migration_unavailable_when_table_missing():
    engine = _FakeQueryEngine(None)
    result = await health.check_migration(engine)
    assert result["status"] == "unavailable"


@pytest.mark.asyncio
async def test_check_migration_unavailable_on_query_error():
    result = await health.check_migration(_TimingOutEngine())
    assert result["status"] == "unavailable"


@pytest.mark.asyncio
async def test_check_pgvector_returns_unknown_when_engine_is_none():
    result = await health.check_pgvector(None)
    assert result == {"status": "unknown", "latency_ms": None}


@pytest.mark.asyncio
async def test_check_pgvector_healthy_when_extension_present():
    engine = _FakeQueryEngine(_FakeRow(1))
    result = await health.check_pgvector(engine)
    assert result["status"] == "healthy"


@pytest.mark.asyncio
async def test_check_pgvector_unavailable_when_extension_missing():
    engine = _FakeQueryEngine(None)
    result = await health.check_pgvector(engine)
    assert result["status"] == "unavailable"


@pytest.mark.asyncio
async def test_check_pgvector_unavailable_on_query_error():
    result = await health.check_pgvector(_TimingOutEngine())
    assert result["status"] == "unavailable"


def test_check_local_auth_secret_unknown_outside_local_and_test():
    result = health.check_local_auth_secret("production", "/nonexistent", externally_supplied=False)
    assert result == {"status": "unknown", "latency_ms": None}


def test_check_local_auth_secret_healthy_when_generated_secret_file_present(tmp_path):
    secret_file = tmp_path / "jwt-secret"
    secret_file.write_text("some-generated-secret")
    result = health.check_local_auth_secret("local", str(secret_file), externally_supplied=False)
    assert result["status"] == "healthy"


def test_check_local_auth_secret_healthy_when_real_secret_configured_and_file_absent(tmp_path):
    """A real SUPABASE_JWT_SECRET intentionally never touches the file
    (see Settings._default_local_auth_secret) - the check must not treat
    that as unavailable just because the file doesn't exist."""
    result = health.check_local_auth_secret(
        "local", str(tmp_path / "never-written"), externally_supplied=True
    )
    assert result["status"] == "healthy"


def test_check_local_auth_secret_degraded_when_persistence_failed_despite_in_memory_fallback(
    tmp_path,
):
    """load_or_create_local_auth_secret always returns *some* usable
    secret even when writing to disk failed (an in-memory-only fallback -
    see backend/core/local_auth_secret.py), so a check that only asks "is
    there a secret" can never observe this failure. The real-time file
    check here is what actually catches it: existing Local Mode sessions
    silently stop validating on the next restart if this isn't degraded."""
    result = health.check_local_auth_secret(
        "local", str(tmp_path / "persistence-failed-so-never-written"), externally_supplied=False
    )
    assert result["status"] == "degraded"
