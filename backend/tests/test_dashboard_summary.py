"""Dashboard summary: real counts and recent activity, never fixture data."""
import io

import httpx
import pytest

from backend.api import tools as tools_module
from backend.services import ssrf_guard

from ._knowledge_fakes import FakeEmbeddingProvider
from .conftest import TEST_USER_B


@pytest.fixture(autouse=True)
def _fast_embeddings(monkeypatch):
    monkeypatch.setattr(
        "backend.services.knowledge.get_embedding_provider", lambda: FakeEmbeddingProvider()
    )


def _stub_resolve(monkeypatch, mapping: dict[str, tuple[str, ...]]) -> None:
    async def fake_resolve(hostname: str, port: int) -> tuple[str, ...]:
        return mapping[hostname]

    monkeypatch.setattr(ssrf_guard, "resolve_hostname", fake_resolve)


def _patch_scan_url(monkeypatch, handler) -> None:
    from backend.services import url_scanner

    original = url_scanner.scan_url

    async def wrapped(raw_url: str, *, transport=None):
        return await original(raw_url, transport=httpx.MockTransport(handler))

    monkeypatch.setattr(tools_module, "scan_url", wrapped)


def test_dashboard_summary_requires_bearer_token(unauthenticated_client):
    assert unauthenticated_client.get("/api/system/dashboard-summary").status_code == 401


def test_dashboard_summary_starts_at_zero_for_a_fresh_user(api_client):
    body = api_client.get("/api/system/dashboard-summary").json()
    assert body["counts"] == {
        "documents": 0,
        "conversations": 0,
        "messages": 0,
        "scans": 0,
    }
    assert body["recent_activity"] == []


def test_dashboard_summary_counts_reflect_real_rows_not_fixtures(api_client, monkeypatch):
    # One conversation with one exchange -> 1 conversation, 2 messages.
    conversation = api_client.post(
        "/api/chatbot/conversations", json={"title": "dashboard-summary-test"}
    ).json()
    api_client.post(
        "/api/chatbot/chat",
        json={"message": "hello", "conversation_id": conversation["id"]},
    )

    # One document.
    files = {"file": ("dash-doc.txt", io.BytesIO(b"Dashboard test content."), "text/plain")}
    upload = api_client.post("/api/knowledge/documents", files=files).json()
    assert upload["document"]["processing_status"] == "ready"

    # One scan.
    _stub_resolve(monkeypatch, {"example.com": ("93.184.216.34",)})

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "text/html"}, content=b"ok")

    _patch_scan_url(monkeypatch, handler)
    api_client.post("/api/tools/url-scan", json={"url": "https://example.com/"})

    body = api_client.get("/api/system/dashboard-summary").json()
    assert body["counts"] == {
        "documents": 1,
        "conversations": 1,
        # The assistant's own reply is stored as a second message alongside
        # the user's turn - see backend/services/assistant.py.
        "messages": 2,
        "scans": 1,
    }

    activity_types = {item["type"] for item in body["recent_activity"]}
    assert activity_types == {"conversation", "document", "scan"}
    # Newest first.
    timestamps = [item["created_at"] for item in body["recent_activity"]]
    assert timestamps == sorted(timestamps, reverse=True)


def test_dashboard_summary_is_scoped_to_the_caller_not_other_users(api_client, switch_user):
    api_client.post("/api/chatbot/conversations", json={"title": "mine"})

    switch_user(TEST_USER_B)
    body = api_client.get("/api/system/dashboard-summary").json()
    assert body["counts"]["conversations"] == 0
