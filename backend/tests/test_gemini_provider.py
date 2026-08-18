"""Gemini provider: request shaping, retries and error mapping, transport-mocked."""
import httpx
import pytest

from backend.core.exceptions import (
    ConfigurationMissingError,
    ProviderAuthenticationError,
    ProviderRateLimitedError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    UpstreamMalformedError,
)
from backend.providers.llm.base import LLMMessage
from backend.providers.llm.gemini import GeminiProvider

SUCCESS_BODY = {
    "candidates": [{"content": {"parts": [{"text": "Hello from Gemini."}]}}]
}

# Verified directly against the live API with a deliberately malformed key
# (see gemini.py's _is_invalid_api_key_response docstring) - this is the
# real shape, not a guess.
INVALID_KEY_BODY = {
    "error": {
        "code": 400,
        "message": "API key not valid. Please pass a valid API key.",
        "status": "INVALID_ARGUMENT",
        "details": [
            {
                "@type": "type.googleapis.com/google.rpc.ErrorInfo",
                "reason": "API_KEY_INVALID",
                "domain": "googleapis.com",
            }
        ],
    }
}


def _provider(handler, **kwargs) -> GeminiProvider:
    return GeminiProvider(
        api_key="test-key",
        transport=httpx.MockTransport(handler),
        max_attempts=kwargs.pop("max_attempts", 1),
        **kwargs,
    )


def test_is_configured_reflects_the_api_key():
    assert GeminiProvider(api_key="x").is_configured is True
    assert GeminiProvider(api_key="").is_configured is False


async def test_generate_raises_configuration_missing_without_a_key():
    provider = GeminiProvider(api_key="")
    with pytest.raises(ConfigurationMissingError):
        await provider.generate([LLMMessage(role="user", content="hi")], system_prompt="sys")


async def test_generate_returns_the_response_text_and_never_leaks_the_key():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = dict(request.headers)
        return httpx.Response(200, json=SUCCESS_BODY)

    provider = _provider(handler)
    result = await provider.generate(
        [LLMMessage(role="user", content="hi")], system_prompt="sys"
    )
    assert result.content == "Hello from Gemini."
    assert result.provider == "gemini"
    # The key travels in a header, never a query string, and never in metadata.
    assert captured["headers"]["x-goog-api-key"] == "test-key"
    assert "test-key" not in str(result.metadata)


async def test_generate_maps_assistant_role_to_model_for_gemini():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = request.content
        return httpx.Response(200, json=SUCCESS_BODY)

    provider = _provider(handler)
    await provider.generate(
        [
            LLMMessage(role="user", content="hi"),
            LLMMessage(role="assistant", content="hello"),
        ],
        system_prompt="sys",
    )
    assert b'"role":"model"' in captured["body"] or b'"role": "model"' in captured["body"]


async def test_generate_raises_rate_limited_on_429():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": "slow down"})

    provider = _provider(handler)
    with pytest.raises(ProviderRateLimitedError):
        await provider.generate([LLMMessage(role="user", content="hi")], system_prompt="sys")


async def test_generate_raises_unavailable_on_a_client_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "bad request"})

    provider = _provider(handler)
    with pytest.raises(ProviderUnavailableError):
        await provider.generate([LLMMessage(role="user", content="hi")], system_prompt="sys")


async def test_generate_retries_and_then_raises_unavailable_on_persistent_5xx():
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        return httpx.Response(503)

    provider = _provider(handler, max_attempts=3)
    with pytest.raises(ProviderUnavailableError):
        await provider.generate([LLMMessage(role="user", content="hi")], system_prompt="sys")
    assert attempts["n"] == 3


async def test_generate_succeeds_after_a_transient_5xx(monkeypatch):
    monkeypatch.setattr("backend.providers.llm.gemini.RETRY_BACKOFF_SECONDS", 0.0)
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        if attempts["n"] == 1:
            return httpx.Response(503)
        return httpx.Response(200, json=SUCCESS_BODY)

    provider = _provider(handler, max_attempts=3)
    result = await provider.generate(
        [LLMMessage(role="user", content="hi")], system_prompt="sys"
    )
    assert result.content == "Hello from Gemini."
    assert attempts["n"] == 2


async def test_generate_raises_timeout_on_a_timeout():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timed out", request=request)

    provider = _provider(handler)
    with pytest.raises(ProviderTimeoutError):
        await provider.generate([LLMMessage(role="user", content="hi")], system_prompt="sys")


async def test_generate_raises_unavailable_on_a_connection_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    provider = _provider(handler)
    with pytest.raises(ProviderUnavailableError):
        await provider.generate([LLMMessage(role="user", content="hi")], system_prompt="sys")


async def test_generate_raises_malformed_on_invalid_json():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not json")

    provider = _provider(handler)
    with pytest.raises(UpstreamMalformedError):
        await provider.generate([LLMMessage(role="user", content="hi")], system_prompt="sys")


async def test_generate_raises_malformed_on_an_unexpected_shape():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": "shape"})

    provider = _provider(handler)
    with pytest.raises(UpstreamMalformedError):
        await provider.generate([LLMMessage(role="user", content="hi")], system_prompt="sys")


async def test_generate_raises_malformed_on_empty_text():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"candidates": [{"content": {"parts": [{"text": "   "}]}}]}
        )

    provider = _provider(handler)
    with pytest.raises(UpstreamMalformedError):
        await provider.generate([LLMMessage(role="user", content="hi")], system_prompt="sys")


async def test_generate_raises_authentication_error_on_the_real_invalid_key_shape():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json=INVALID_KEY_BODY)

    provider = _provider(handler)
    with pytest.raises(ProviderAuthenticationError):
        await provider.generate([LLMMessage(role="user", content="hi")], system_prompt="sys")


async def test_generate_does_not_misclassify_an_unrelated_400_as_invalid_key():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={"error": {"code": 400, "message": "bad request", "status": "INVALID_ARGUMENT"}},
        )

    provider = _provider(handler)
    with pytest.raises(ProviderUnavailableError):
        await provider.generate([LLMMessage(role="user", content="hi")], system_prompt="sys")


# --- list_models (dynamic model discovery) ----------------------------------


async def test_list_models_returns_bare_model_ids():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "models": [
                    {"name": "models/gemini-2.0-flash"},
                    {"name": "models/gemini-2.5-pro"},
                ]
            },
        )

    provider = _provider(handler)
    models = await provider.list_models()
    assert models == ["gemini-2.0-flash", "gemini-2.5-pro"]


async def test_list_models_raises_configuration_missing_without_a_key():
    provider = GeminiProvider(api_key="")
    with pytest.raises(ConfigurationMissingError):
        await provider.list_models()


async def test_list_models_raises_authentication_error_on_invalid_key():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json=INVALID_KEY_BODY)

    provider = _provider(handler)
    with pytest.raises(ProviderAuthenticationError):
        await provider.list_models()


async def test_list_models_raises_rate_limited_on_429():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": "slow down"})

    provider = _provider(handler)
    with pytest.raises(ProviderRateLimitedError):
        await provider.list_models()
