import pytest
from pydantic import ValidationError

from backend.config.settings import Settings


def test_production_rejects_default_secrets(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("JWT_SECRET", "change-me")
    monkeypatch.setenv("SECRET_KEY", "a-real-secret")
    monkeypatch.setenv("DB_PASSWORD", "a-real-password")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_production_accepts_real_secrets(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("JWT_SECRET", "a-real-secret-value")
    monkeypatch.setenv("SECRET_KEY", "another-real-secret")
    monkeypatch.setenv("DB_PASSWORD", "a-real-db-password")

    settings = Settings(_env_file=None)

    assert settings.is_production


def test_development_allows_default_secrets(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.delenv("JWT_SECRET", raising=False)

    settings = Settings(_env_file=None)

    assert not settings.is_production
