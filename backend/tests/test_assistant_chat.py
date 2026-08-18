"""AI Security Assistant: chat routing, persistence and error mapping."""
import pytest

from backend.core.exceptions import (
    ProviderRateLimitedError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    UpstreamMalformedError,
)
from backend.providers.llm.mock import MockProvider


@pytest.fixture()
def mock_provider(monkeypatch) -> MockProvider:
    provider = MockProvider(reply="Injected provider reply.")
    monkeypatch.setattr(
        "backend.services.assistant.get_llm_provider", lambda: provider
    )
    return provider


def test_chat_creates_conversation_and_persists_both_turns(api_client):
    response = api_client.post("/api/chatbot/chat", json={"message": "What is SSRF?"})
    assert response.status_code == 200
    body = response.json()

    assert body["role"] == "assistant"
    assert body["content"]
    assert body["request_id"]
    conversation_id = body["conversation_id"]

    messages = api_client.get(f"/api/chatbot/conversations/{conversation_id}/messages")
    assert messages.status_code == 200
    items = messages.json()["items"]
    assert [item["role"] for item in items] == ["user", "assistant"]
    assert items[0]["content"] == "What is SSRF?"
    assert items[1]["id"] == body["message_id"]


def test_chat_continues_an_existing_conversation(api_client):
    first = api_client.post("/api/chatbot/chat", json={"message": "Hello"}).json()
    second = api_client.post(
        "/api/chatbot/chat",
        json={"message": "What is CVSS?", "conversation_id": first["conversation_id"]},
    ).json()

    assert second["conversation_id"] == first["conversation_id"]
    total = api_client.get(
        f"/api/chatbot/conversations/{first['conversation_id']}/messages"
    ).json()["total"]
    assert total == 4


def test_fast_mode_never_calls_the_external_provider(api_client, mock_provider):
    body = api_client.post(
        "/api/chatbot/chat", json={"message": "What is zero trust?", "mode": "fast"}
    ).json()

    assert body["provider"] == "local"
    assert body["metadata"]["routing_reason"] == "fast_mode"
    assert mock_provider.calls == []


def test_deep_mode_uses_the_configured_provider(api_client, mock_provider):
    body = api_client.post(
        "/api/chatbot/chat",
        json={"message": "Analyse this incident pattern for me.", "mode": "deep"},
    ).json()

    assert body["provider"] == "mock"
    assert body["content"] == "Injected provider reply."
    assert body["metadata"]["routing_reason"] == "deep_mode"
    assert body["metadata"]["external_provider_configured"] is True
    assert len(mock_provider.calls) == 1


def test_deep_mode_falls_back_to_local_when_provider_unconfigured(api_client, monkeypatch):
    monkeypatch.setattr(
        "backend.services.assistant.get_llm_provider",
        lambda: MockProvider(configured=False),
    )
    body = api_client.post(
        "/api/chatbot/chat",
        json={"message": "Explain lateral movement detection.", "mode": "deep"},
    ).json()

    # The honest-fallback rule: answer locally and say so, never claim the
    # external provider ran.
    assert body["provider"] == "local"
    assert body["metadata"]["routing_reason"] == "external_provider_not_configured"
    assert body["metadata"]["external_provider_configured"] is False


def test_metadata_always_reports_fallback_used_false(api_client, mock_provider):
    """fallback_used must be present (not omitted) on every response shape -
    fast mode, deep mode with a real provider call, and deep mode with an
    unconfigured provider (the honest-degrade path) - since this router
    never falls back mid-request (see AssistantService._build_metadata's
    docstring comment), it is always false, never simply absent."""
    fast = api_client.post(
        "/api/chatbot/chat", json={"message": "What is zero trust?", "mode": "fast"}
    ).json()
    assert fast["metadata"]["fallback_used"] is False

    deep = api_client.post(
        "/api/chatbot/chat", json={"message": "Analyse this pattern.", "mode": "deep"}
    ).json()
    assert deep["metadata"]["fallback_used"] is False


def test_password_question_is_never_forwarded_to_the_provider(api_client, mock_provider):
    body = api_client.post(
        "/api/chatbot/chat",
        json={"message": "Is my password strong enough?", "mode": "deep"},
    ).json()

    assert body["intent"] == "password_question"
    assert body["provider"] == "local"
    assert body["metadata"]["routing_reason"] == "intent_handled_locally"
    assert mock_provider.calls == []
    assert "Password Checker" in body["content"]


def test_knowledge_rag_intent_round_trips_through_the_api(api_client):
    """Regression: the intent enum grew knowledge_rag/incident_response
    values without the ChatResponse schema's IntentName Literal being
    updated to match, which made FastAPI's response serialization raise a
    500 ResponseValidationError on every such request."""
    response = api_client.post(
        "/api/chatbot/chat",
        json={"message": "Theo tai lieu toi vua upload thi noi dung la gi?"},
    )
    assert response.status_code == 200
    assert response.json()["intent"] == "knowledge_rag"


def test_incident_response_intent_round_trips_through_the_api(api_client):
    response = api_client.post(
        "/api/chatbot/chat",
        json={"message": "Website cua toi nghi bi tan cong, phai lam gi?"},
    )
    assert response.status_code == 200
    assert response.json()["intent"] == "incident_response"


def test_chat_redacts_secrets_before_storing_them(api_client):
    secret = "AKIAIOSFODNN7EXAMPLE"
    body = api_client.post(
        "/api/chatbot/chat",
        json={"message": f"Is it safe to commit api_key={secret} to git?"},
    ).json()

    stored = api_client.get(
        f"/api/chatbot/conversations/{body['conversation_id']}/messages"
    ).json()["items"]
    user_turn = stored[0]["content"]
    assert secret not in user_turn
    assert "[REDACTED]" in user_turn


@pytest.mark.parametrize(
    ("exception", "expected_status", "expected_error"),
    [
        (ProviderTimeoutError(), 504, "provider_timeout"),
        (ProviderUnavailableError(), 502, "provider_unavailable"),
        (ProviderRateLimitedError(), 429, "provider_rate_limited"),
        (UpstreamMalformedError(), 502, "upstream_malformed"),
    ],
)
def test_provider_failures_map_to_the_error_envelope(
    api_client, monkeypatch, exception, expected_status, expected_error
):
    monkeypatch.setattr(
        "backend.services.assistant.get_llm_provider",
        lambda: MockProvider(raises=exception),
    )
    response = api_client.post(
        "/api/chatbot/chat",
        json={"message": "Summarise this alert for me.", "mode": "deep"},
    )

    assert response.status_code == expected_status
    body = response.json()
    assert body["error"] == expected_error
    assert body["request_id"]
    assert "Traceback" not in body["message"]


def test_chat_rejects_an_unknown_conversation(api_client):
    response = api_client.post(
        "/api/chatbot/chat",
        json={
            "message": "Hello",
            "conversation_id": "11111111-2222-3333-4444-555555555555",
        },
    )
    assert response.status_code == 404
    assert response.json()["error"] == "not_found"


def test_chat_rejects_an_empty_message(api_client):
    response = api_client.post("/api/chatbot/chat", json={"message": "   "})
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_request"


def test_chat_rejects_a_blank_message_at_schema_level(api_client):
    response = api_client.post("/api/chatbot/chat", json={"message": ""})
    assert response.status_code == 422
    assert response.json()["error"] == "validation_error"


def test_chat_rejects_an_oversized_message(api_client):
    response = api_client.post("/api/chatbot/chat", json={"message": "a" * 4001})
    assert response.status_code == 422
