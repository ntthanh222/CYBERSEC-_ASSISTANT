"""Embedding provider selection and the Gemini cloud opt-in gate."""
import httpx
import pytest

from backend.core.exceptions import ConfigurationMissingError
from backend.providers.embeddings.gemini import GeminiEmbeddingProvider
from backend.providers.embeddings.local import LocalEmbeddingProvider
from backend.providers.embeddings.registry import get_embedding_provider, reset_embedding_provider


@pytest.fixture(autouse=True)
def _reset_registry():
    reset_embedding_provider()
    yield
    reset_embedding_provider()


def test_local_provider_is_always_configured():
    provider = LocalEmbeddingProvider()
    assert provider.is_configured is True


def test_local_provider_reports_configured_dimension():
    provider = LocalEmbeddingProvider(dimension=384)
    assert provider.dimension == 384


def test_gemini_provider_is_not_configured_without_a_key():
    provider = GeminiEmbeddingProvider(api_key="")
    assert provider.is_configured is False


async def test_gemini_provider_refuses_to_call_out_when_unconfigured():
    provider = GeminiEmbeddingProvider(api_key="")
    with pytest.raises(ConfigurationMissingError):
        await provider.embed(["hello"])


async def test_gemini_provider_embed_empty_list_short_circuits():
    provider = GeminiEmbeddingProvider(api_key="")
    assert await provider.embed([]) == []


async def test_gemini_provider_parses_a_real_looking_response():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"embedding": {"values": [0.1, 0.2, 0.3]}})

    provider = GeminiEmbeddingProvider(
        api_key="test-key", transport=httpx.MockTransport(handler)
    )
    vectors = await provider.embed(["hello world"])
    assert vectors == [[0.1, 0.2, 0.3]]


def test_registry_defaults_to_local_when_provider_is_local(monkeypatch):
    monkeypatch.setenv("EMBEDDING_PROVIDER", "local")
    monkeypatch.setenv("GEMINI_API_KEY", "some-key")
    from backend.config.settings import get_settings

    get_settings.cache_clear()
    try:
        assert get_embedding_provider().name == "local"
    finally:
        get_settings.cache_clear()


def test_registry_never_upgrades_to_cloud_on_key_alone(monkeypatch):
    # EMBEDDING_PROVIDER left at its default ("local") - a stray
    # GEMINI_API_KEY (present for the chat LLM) must never silently switch
    # embeddings to the cloud provider.
    monkeypatch.setenv("GEMINI_API_KEY", "some-key")
    from backend.config.settings import get_settings

    get_settings.cache_clear()
    try:
        assert get_embedding_provider().name == "local"
    finally:
        get_settings.cache_clear()


def test_registry_uses_gemini_only_with_explicit_opt_in_and_key(monkeypatch):
    monkeypatch.setenv("EMBEDDING_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "some-key")
    from backend.config.settings import get_settings

    get_settings.cache_clear()
    try:
        assert get_embedding_provider().name == "gemini"
    finally:
        get_settings.cache_clear()


def test_registry_falls_back_to_local_if_gemini_opted_in_without_a_key(monkeypatch):
    monkeypatch.setenv("EMBEDDING_PROVIDER", "gemini")
    # An explicit empty value, not delenv: Settings reads .env directly via
    # pydantic-settings (see backend/config/settings.py's env_file config),
    # independent of os.environ - delenv only removes the process env var,
    # so on a machine with a real GEMINI_API_KEY in .env (e.g. local dev
    # with the AI Chat feature actually configured) this test would still
    # observe the real key and wrongly assert "gemini" was picked. A real
    # env var always takes precedence over .env in pydantic-settings, so
    # setting it to "" here reliably represents "not configured" regardless
    # of what's on disk.
    monkeypatch.setenv("GEMINI_API_KEY", "")
    from backend.config.settings import get_settings

    get_settings.cache_clear()
    try:
        assert get_embedding_provider().name == "local"
    finally:
        get_settings.cache_clear()
