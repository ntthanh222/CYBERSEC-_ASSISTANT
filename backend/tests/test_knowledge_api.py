"""Knowledge base API: auth gating, upload, list/get/delete/reprocess, preview."""
import io

import pytest

from ._knowledge_fakes import FakeEmbeddingProvider
from .conftest import TEST_USER_B


@pytest.fixture(autouse=True)
def _fast_embeddings(monkeypatch):
    """Every knowledge-API test uses the deterministic fake, never the real
    (slow, network-on-first-use) local embedding model."""
    monkeypatch.setattr(
        "backend.services.knowledge.get_embedding_provider", lambda: FakeEmbeddingProvider()
    )


def _upload(client, *, filename="notes.txt", content=b"Team runbook content.", title=None):
    files = {"file": (filename, io.BytesIO(content), "text/plain")}
    data = {"title": title} if title else {}
    return client.post("/api/knowledge/documents", files=files, data=data)


def test_upload_requires_bearer_token(unauthenticated_client):
    response = _upload(unauthenticated_client)
    assert response.status_code == 401


def test_list_requires_bearer_token(unauthenticated_client):
    assert unauthenticated_client.get("/api/knowledge/documents").status_code == 401


def test_retrieval_preview_requires_bearer_token(unauthenticated_client):
    response = unauthenticated_client.post(
        "/api/knowledge/retrieval/preview", json={"query": "anything"}
    )
    assert response.status_code == 401


def test_upload_txt_reaches_ready_and_is_not_owned_by_a_client_supplied_id(api_client):
    response = _upload(api_client, title="Runbook")
    assert response.status_code == 201
    body = response.json()
    assert body["document"]["processing_status"] == "ready"
    assert body["document"]["chunk_count"] >= 1
    assert body["document"]["title"] == "Runbook"
    assert body["reused_existing"] is False
    # owner_user_id in the response reflects the verified caller, never
    # anything the client could have sent (the upload endpoint accepts no
    # such field at all - this just confirms one wasn't silently accepted).
    assert body["document"]["owner_user_id"]


def test_duplicate_upload_is_idempotent(api_client):
    first = _upload(api_client, content=b"Exact same bytes.").json()
    second = _upload(api_client, filename="renamed.txt", content=b"Exact same bytes.").json()
    assert second["reused_existing"] is True
    assert second["document"]["id"] == first["document"]["id"]


def test_upload_rejects_oversized_file(api_client, monkeypatch):
    from backend.config import settings as settings_module

    monkeypatch.setenv("RAG_MAX_UPLOAD_BYTES", "5")
    settings_module.get_settings.cache_clear()
    try:
        response = _upload(api_client, content=b"way more than five bytes")
        assert response.status_code == 413
    finally:
        monkeypatch.delenv("RAG_MAX_UPLOAD_BYTES", raising=False)
        settings_module.get_settings.cache_clear()


def test_upload_rejects_unsupported_type(api_client):
    binary = bytes(range(256)) * 4
    files = {"file": ("archive.zip", io.BytesIO(binary), "application/zip")}
    response = api_client.post("/api/knowledge/documents", files=files)
    assert response.status_code == 415


def test_list_and_get_and_delete_round_trip(api_client):
    uploaded = _upload(api_client).json()["document"]

    listed = api_client.get("/api/knowledge/documents").json()
    assert any(item["id"] == uploaded["id"] for item in listed["items"])

    detail = api_client.get(f"/api/knowledge/documents/{uploaded['id']}")
    assert detail.status_code == 200
    assert detail.json()["id"] == uploaded["id"]

    delete = api_client.delete(f"/api/knowledge/documents/{uploaded['id']}")
    assert delete.status_code == 204

    after = api_client.get(f"/api/knowledge/documents/{uploaded['id']}")
    assert after.status_code == 404


def test_other_user_cannot_read_or_delete_a_private_document(api_client, switch_user):
    uploaded = _upload(api_client).json()["document"]

    switch_user(TEST_USER_B)
    assert api_client.get(f"/api/knowledge/documents/{uploaded['id']}").status_code == 404
    assert api_client.delete(f"/api/knowledge/documents/{uploaded['id']}").status_code == 404


def test_other_user_cannot_reprocess_a_private_document(api_client, switch_user):
    uploaded = _upload(api_client).json()["document"]

    switch_user(TEST_USER_B)
    response = api_client.post(f"/api/knowledge/documents/{uploaded['id']}/reprocess")
    assert response.status_code == 404


def test_owner_can_reprocess_their_document(api_client):
    uploaded = _upload(api_client).json()["document"]
    response = api_client.post(f"/api/knowledge/documents/{uploaded['id']}/reprocess")
    assert response.status_code == 200
    assert response.json()["processing_status"] == "ready"


def test_retrieval_preview_returns_an_empty_result_on_sqlite(api_client):
    # Unit tests run on SQLite, which has no pgvector - the retriever
    # correctly degrades to NullRagRetriever there (see
    # backend.services.rag_retrieval.get_rag_retriever_for_session). Real
    # pgvector search is proven against Postgres in test_live_postgres_rag.py.
    _upload(api_client)
    response = api_client.post("/api/knowledge/retrieval/preview", json={"query": "runbook"})
    assert response.status_code == 200
    body = response.json()
    assert body["results"] == []
    assert body["retrieval_metadata"]["rag_ready"] is False


def test_chat_response_includes_citations_field_even_when_empty(api_client):
    response = api_client.post("/api/chatbot/chat", json={"message": "Hello there"})
    assert response.status_code == 200
    body = response.json()
    assert body["citations"] == []
    assert body["metadata"]["grounded"] is False
