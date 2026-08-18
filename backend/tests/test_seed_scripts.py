"""Unit tests for the seed/reset script production guards (no real DB needed:
these guards must reject before ever touching the database)."""
from backend.scripts import reset_demo, seed_demo


def test_seed_demo_refuses_in_production(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("JWT_SECRET", "a-real-secret-value")
    monkeypatch.setenv("SECRET_KEY", "another-real-secret")
    monkeypatch.setenv("DB_PASSWORD", "a-real-db-password")
    from backend.config import settings as settings_module

    settings_module.get_settings.cache_clear()
    try:
        assert seed_demo.run(dry_run=True) == 1
    finally:
        settings_module.get_settings.cache_clear()


def test_reset_demo_refuses_in_production(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("JWT_SECRET", "a-real-secret-value")
    monkeypatch.setenv("SECRET_KEY", "another-real-secret")
    monkeypatch.setenv("DB_PASSWORD", "a-real-db-password")
    from backend.config import settings as settings_module

    settings_module.get_settings.cache_clear()
    try:
        assert reset_demo.run(dry_run=True) == 1
    finally:
        settings_module.get_settings.cache_clear()


def test_seed_batches_registry_is_non_empty():
    assert seed_demo.SEED_BATCHES
    assert all(isinstance(key, str) and key for key in seed_demo.SEED_BATCHES)
