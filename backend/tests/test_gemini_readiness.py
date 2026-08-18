"""verify_gemini_readiness + the Demo Mode-aware branch of describe_ai_health.

Exercises the one-shot startup probe (backend/services/assistant.py) and the
process-wide cache it writes to (backend/core/gemini_readiness.py), matching
FINAL_MASTER_PROMPT_CYBERSEC_ASSISTANT.md section C: a configured key alone
must never report READY once DEMO_REQUIRE_GEMINI=true, and each real failure
mode maps to exactly one of the five allowed categories.
"""
import httpx
import pytest

from backend.core.gemini_readiness import _reset_for_tests, get_gemini_readiness
from backend.providers.llm.gemini import GeminiProvider
from backend.services.assistant import describe_ai_health, verify_gemini_readiness

MODELS_BODY = {"models": [{"name": "models/gemini-2.5-flash"}, {"name": "models/gemini-2.5-pro"}]}
SUCCESS_BODY = {"candidates": [{"content": {"parts": [{"text": "OK"}]}}]}
INVALID_KEY_BODY = {
    "error": {
        "code": 400,
        "message": "API key not valid. Please pass a valid API key.",
        "status": "INVALID_ARGUMENT",
        "details": [{"reason": "API_KEY_INVALID"}],
    }
}


@pytest.fixture(autouse=True)
def _reset_readiness_state():
    _reset_for_tests()
    yield
    _reset_for_tests()


def _provider(models_response, generate_response) -> GeminiProvider:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/models"):
            return models_response
        return generate_response

    return GeminiProvider(
        api_key="test-key", transport=httpx.MockTransport(handler), max_attempts=1
    )


async def test_verify_marks_not_configured_without_a_key():
    provider = GeminiProvider(api_key="")
    await verify_gemini_readiness(provider)
    state = get_gemini_readiness()
    assert state["status"] == "failed"
    assert state["last_error_category"] == "NOT_CONFIGURED"


async def test_verify_marks_ready_on_a_real_successful_call():
    provider = _provider(
        httpx.Response(200, json=MODELS_BODY), httpx.Response(200, json=SUCCESS_BODY)
    )
    await verify_gemini_readiness(provider)
    state = get_gemini_readiness()
    assert state["status"] == "ready"
    assert state["last_error_category"] is None
    assert state["model"] == "gemini-2.5-flash"
    assert state["model_supported"] is True


async def test_verify_marks_invalid_key_on_the_real_invalid_key_shape():
    provider = _provider(
        httpx.Response(400, json=INVALID_KEY_BODY), httpx.Response(400, json=INVALID_KEY_BODY)
    )
    await verify_gemini_readiness(provider)
    state = get_gemini_readiness()
    assert state["status"] == "failed"
    assert state["last_error_category"] == "INVALID_KEY"


async def test_verify_marks_rate_limited_on_quota_exhaustion():
    provider = _provider(
        httpx.Response(200, json=MODELS_BODY), httpx.Response(429, json={"error": "quota"})
    )
    await verify_gemini_readiness(provider)
    state = get_gemini_readiness()
    assert state["status"] == "failed"
    assert state["last_error_category"] == "RATE_LIMITED"
    # Model discovery succeeded independently of the generate call failing.
    assert state["model_supported"] is True


async def test_verify_marks_degraded_on_a_malformed_upstream_response():
    provider = _provider(
        httpx.Response(200, json=MODELS_BODY), httpx.Response(200, content=b"not json")
    )
    await verify_gemini_readiness(provider)
    state = get_gemini_readiness()
    assert state["status"] == "failed"
    assert state["last_error_category"] == "DEGRADED"


async def test_verify_marks_unavailable_on_a_persistent_5xx():
    provider = _provider(httpx.Response(200, json=MODELS_BODY), httpx.Response(503))
    await verify_gemini_readiness(provider)
    state = get_gemini_readiness()
    assert state["status"] == "failed"
    assert state["last_error_category"] == "UNAVAILABLE"


async def test_verify_flags_an_unsupported_configured_model():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json=MODELS_BODY)
        return httpx.Response(200, json=SUCCESS_BODY)

    provider = GeminiProvider(
        api_key="test-key",
        model="gemini-1.0-nonexistent",
        transport=httpx.MockTransport(handler),
        max_attempts=1,
    )
    await verify_gemini_readiness(provider)
    state = get_gemini_readiness()
    assert state["status"] == "ready"  # the generate call itself still succeeded
    assert state["model_supported"] is False


# --- describe_ai_health under DEMO_REQUIRE_GEMINI=true ----------------------


class _FakeGeminiProvider:
    name = "gemini"
    model = "gemini-2.5-flash"

    def __init__(self, configured: bool):
        self.is_configured = configured


def test_describe_ai_health_is_degraded_when_configured_but_not_yet_verified(monkeypatch):
    monkeypatch.setenv("DEMO_REQUIRE_GEMINI", "true")
    from backend.config.settings import get_settings

    get_settings.cache_clear()
    try:
        body = describe_ai_health(_FakeGeminiProvider(configured=True))
        assert body["provider_configured"] is True
        assert body["ready"] is False
        assert body["status"] == "degraded"
    finally:
        get_settings.cache_clear()


async def test_describe_ai_health_is_healthy_once_verify_gemini_readiness_succeeds(monkeypatch):
    monkeypatch.setenv("DEMO_REQUIRE_GEMINI", "true")
    from backend.config.settings import get_settings

    get_settings.cache_clear()
    try:
        provider = _provider(
            httpx.Response(200, json=MODELS_BODY), httpx.Response(200, json=SUCCESS_BODY)
        )
        await verify_gemini_readiness(provider)

        body = describe_ai_health(_FakeGeminiProvider(configured=True))
        assert body["ready"] is True
        assert body["status"] == "healthy"
        assert body["last_error_category"] is None
    finally:
        get_settings.cache_clear()


def test_describe_ai_health_without_demo_require_gemini_is_ready_on_configured_alone(monkeypatch):
    # Explicit "false", not delenv: pydantic-settings reads .env directly
    # from disk independent of os.environ (see test_embedding_providers.py's
    # test_registry_falls_back_to_local_if_gemini_opted_in_without_a_key for
    # the same pattern), and a real deployment's .env may itself set
    # DEMO_REQUIRE_GEMINI=true - this test must not depend on what's on disk.
    monkeypatch.setenv("DEMO_REQUIRE_GEMINI", "false")
    from backend.config.settings import get_settings

    get_settings.cache_clear()
    try:
        body = describe_ai_health(_FakeGeminiProvider(configured=True))
        assert body["ready"] is True
        assert body["status"] == "healthy"
    finally:
        get_settings.cache_clear()
