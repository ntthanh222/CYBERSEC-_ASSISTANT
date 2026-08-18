"""Endpoint-level auth gating (Phase 2.5B).

Every data/tool route must return 401 without a bearer token (or with an
invalid one), and must never let one authenticated caller see, mutate, or
delete another caller's rows. RLS enforcement itself is verified against
live Postgres in ``test_rls_isolation.py``; these tests exercise the
service-layer ownership checks that back it up, using the SQLite test
database via ``as_user_b``.
"""
import pytest

from backend.tests.conftest import TEST_USER_A, TEST_USER_B

_PRIVATE_GET_ENDPOINTS = [
    "/api/chatbot/conversations",
    "/api/tools/scan-history",
]


@pytest.mark.parametrize("path", _PRIVATE_GET_ENDPOINTS)
def test_private_endpoint_without_token_is_401(unauthenticated_client, path):
    response = unauthenticated_client.get(path)
    assert response.status_code == 401


@pytest.mark.parametrize("path", _PRIVATE_GET_ENDPOINTS)
def test_private_endpoint_with_malformed_header_is_401(unauthenticated_client, path):
    response = unauthenticated_client.get(path, headers={"Authorization": "not-bearer-shaped"})
    assert response.status_code == 401


@pytest.mark.parametrize("path", _PRIVATE_GET_ENDPOINTS)
def test_private_endpoint_with_garbage_token_is_401(unauthenticated_client, path):
    response = unauthenticated_client.get(
        path, headers={"Authorization": "Bearer not-a-real-jwt"}
    )
    assert response.status_code == 401


def test_password_check_requires_auth(unauthenticated_client):
    response = unauthenticated_client.post(
        "/api/tools/password-check", json={"password": "irrelevant"}
    )
    assert response.status_code == 401


def test_health_endpoint_does_not_require_auth(unauthenticated_client):
    response = unauthenticated_client.get("/health")
    assert response.status_code == 200


def test_user_a_cannot_read_user_b_conversation(api_client, switch_user):
    created = api_client.post("/api/chatbot/conversations", json={"title": "A's secret"})
    assert created.status_code == 201
    conversation_id = created.json()["id"]

    switch_user(TEST_USER_B)
    response = api_client.get(f"/api/chatbot/conversations/{conversation_id}")
    assert response.status_code == 404


def test_user_a_cannot_delete_user_b_conversation(api_client, switch_user):
    created = api_client.post("/api/chatbot/conversations", json={"title": "A's secret"})
    conversation_id = created.json()["id"]

    switch_user(TEST_USER_B)
    response = api_client.delete(f"/api/chatbot/conversations/{conversation_id}")
    assert response.status_code == 404

    # Still there, from A's own point of view.
    switch_user(TEST_USER_A)
    still_there = api_client.get(f"/api/chatbot/conversations/{conversation_id}")
    assert still_there.status_code == 200


def test_user_a_conversation_list_excludes_user_b(api_client, switch_user):
    api_client.post("/api/chatbot/conversations", json={"title": "A's conversation"})

    switch_user(TEST_USER_B)
    api_client.post("/api/chatbot/conversations", json={"title": "B's conversation"})
    b_items = api_client.get("/api/chatbot/conversations").json()["items"]
    b_titles = {item["title"] for item in b_items}

    switch_user(TEST_USER_A)
    a_items = api_client.get("/api/chatbot/conversations").json()["items"]
    a_titles = {item["title"] for item in a_items}

    assert a_titles == {"A's conversation"}
    assert b_titles == {"B's conversation"}
