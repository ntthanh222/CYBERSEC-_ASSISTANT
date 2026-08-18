"""AI Security Assistant: conversation CRUD, pagination and cascade delete."""
import pytest

from backend.providers.llm.mock import MockProvider
from backend.services.assistant import describe_ai_health


def test_create_conversation_returns_201_and_metadata(api_client):
    response = api_client.post(
        "/api/chatbot/conversations", json={"title": "Log4Shell triage"}
    )
    assert response.status_code == 201
    body = response.json()
    assert body["title"] == "Log4Shell triage"
    assert body["actor"] == "anonymous"
    assert body["created_at"].endswith("+00:00")


def test_create_conversation_records_the_actor_header(api_client):
    body = api_client.post(
        "/api/chatbot/conversations",
        json={"title": "Triage"},
        headers={"X-Actor": "lead-analyst"},
    ).json()
    assert body["actor"] == "lead-analyst"


def test_create_conversation_rejects_an_overlong_title(api_client):
    response = api_client.post("/api/chatbot/conversations", json={"title": "x" * 201})
    assert response.status_code == 422


def test_get_conversation_returns_404_for_unknown_id(api_client):
    response = api_client.get(
        "/api/chatbot/conversations/11111111-2222-3333-4444-555555555555"
    )
    assert response.status_code == 404
    assert response.json()["error"] == "not_found"


def test_get_conversation_returns_422_for_a_malformed_id(api_client):
    assert api_client.get("/api/chatbot/conversations/not-a-uuid").status_code == 422


def test_conversations_are_listed_most_recently_updated_first(api_client):
    api_client.post("/api/chatbot/conversations", json={"title": "first"})
    second = api_client.post(
        "/api/chatbot/conversations", json={"title": "second"}
    ).json()
    # Posting a message touches the parent row, moving it back to the top.
    api_client.post(
        "/api/chatbot/chat",
        json={"message": "Hello", "conversation_id": second["id"]},
    )

    listed = api_client.get("/api/chatbot/conversations").json()["items"]
    titles = [item["title"] for item in listed]
    assert titles[0] == "second"


def test_conversation_pagination_reports_total_and_slices(api_client):
    for index in range(5):
        api_client.post("/api/chatbot/conversations", json={"title": f"conv-{index}"})

    page = api_client.get("/api/chatbot/conversations?page=2&page_size=2").json()
    assert page["total"] == 5
    assert page["page"] == 2
    assert page["page_size"] == 2
    assert len(page["items"]) == 2


def test_pagination_rejects_an_out_of_range_page_size(api_client):
    assert api_client.get("/api/chatbot/conversations?page_size=101").status_code == 422
    assert api_client.get("/api/chatbot/conversations?page=0").status_code == 422


def test_delete_conversation_removes_its_messages(api_client):
    created = api_client.post("/api/chatbot/chat", json={"message": "Hello"}).json()
    conversation_id = created["conversation_id"]

    assert api_client.delete(f"/api/chatbot/conversations/{conversation_id}").status_code == 204
    assert api_client.get(f"/api/chatbot/conversations/{conversation_id}").status_code == 404
    assert (
        api_client.get(f"/api/chatbot/conversations/{conversation_id}/messages").status_code
        == 404
    )


def test_delete_conversation_returns_404_for_unknown_id(api_client):
    response = api_client.delete(
        "/api/chatbot/conversations/11111111-2222-3333-4444-555555555555"
    )
    assert response.status_code == 404


def test_delete_conversation_emits_an_audit_event(api_client, caplog):
    created = api_client.post("/api/chatbot/conversations", json={"title": "x"}).json()
    with caplog.at_level("INFO", logger="backend.audit"):
        api_client.delete(f"/api/chatbot/conversations/{created['id']}")

    actions = [getattr(record, "fields", {}).get("action") for record in caplog.records]
    assert "conversation_deleted" in actions


def test_messages_endpoint_paginates(api_client):
    created = api_client.post("/api/chatbot/chat", json={"message": "one"}).json()
    conversation_id = created["conversation_id"]
    api_client.post(
        "/api/chatbot/chat", json={"message": "two", "conversation_id": conversation_id}
    )

    page = api_client.get(
        f"/api/chatbot/conversations/{conversation_id}/messages?page=1&page_size=3"
    ).json()
    assert page["total"] == 4
    assert len(page["items"]) == 3


@pytest.mark.parametrize(
    ("configured", "expected_status", "expected_provider"),
    [(True, "healthy", "mock"), (False, "degraded", "local")],
)
def test_ai_health_reports_the_real_provider_state(
    api_client, monkeypatch, configured, expected_status, expected_provider
):
    monkeypatch.setattr(
        "backend.services.assistant.get_llm_provider",
        lambda: MockProvider(configured=configured),
    )
    body = api_client.get("/api/system/ai-health").json()
    assert body["status"] == expected_status
    assert body["provider_configured"] is configured
    if not configured:
        assert body["provider"] == expected_provider
        assert "GEMINI_API_KEY" in body["detail"]


def test_ai_health_reports_local_embedding_readiness_but_never_document_counts():
    # Phase 2.6 ships a real (local-by-default) embedding provider, so
    # rag_ready now honestly reflects that retrieval can run - but the health
    # endpoint still never queries the knowledge base itself (no session is
    # available there, and it must never touch private document content), so
    # rag_documents stays 0 regardless of what is actually ingested.
    health = describe_ai_health()
    assert health["rag_ready"] is True
    assert health["rag_documents"] == 0
