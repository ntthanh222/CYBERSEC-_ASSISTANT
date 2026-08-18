"""Actor resolution: caller-supplied header, validated and defaulted."""
import uuid

import pytest
from starlette.requests import Request

from backend.core import actor as actor_module
from backend.core.actor import ANONYMOUS_ACTOR, get_current_actor, resolve_actor
from backend.core.auth import AuthenticatedUser
from backend.core.exceptions import AuthenticationError


def _request(headers: dict[str, str] | None = None) -> Request:
    raw_headers = [
        (k.lower().encode(), v.encode()) for k, v in (headers or {}).items()
    ]
    scope = {"type": "http", "headers": raw_headers, "method": "GET", "path": "/"}
    return Request(scope)


@pytest.mark.parametrize(
    "value", ["lead-analyst", "user_42", "alice@example.com", "a" * 128]
)
def test_resolve_actor_accepts_well_formed_values(value):
    assert resolve_actor(value) == value


@pytest.mark.parametrize(
    "value",
    [None, "", "has space", "line\nbreak", "semi;colon", "a" * 129, "emoji😀"],
)
def test_resolve_actor_falls_back_to_anonymous_for_bad_input(value):
    assert resolve_actor(value) == ANONYMOUS_ACTOR


def test_get_current_actor_reads_the_header(api_client):
    # Exercised indirectly: the assistant conversation-create route depends on
    # get_current_actor and echoes it back in the response.
    response = api_client.post(
        "/api/chatbot/conversations",
        json={"title": "x"},
        headers={"X-Actor": "lead-analyst"},
    )
    assert response.json()["actor"] == "lead-analyst"


def test_get_current_actor_defaults_to_anonymous(api_client):
    response = api_client.post("/api/chatbot/conversations", json={"title": "x"})
    assert response.json()["actor"] == "anonymous"


@pytest.mark.asyncio
async def test_get_current_actor_prefers_the_real_authenticated_user(monkeypatch):
    # Regression test for a real bug: get_current_actor previously only ever
    # read the trivially-forged X-Actor header, defaulting every caller with
    # no header to the single shared "anonymous" bucket - even on routes
    # that already require a verified login. That meant every authenticated
    # user's rate-limit quota (see backend/core/rate_limit.py) and audit
    # trail collapsed into one bucket for the whole application, not one
    # per user, discovered when e2e uploads from many distinct test users
    # exhausted a single 10-per-60s bucket after only 10 total uploads.
    user_id = uuid.uuid4()

    async def fake_verify(token, **kwargs):
        assert token == "a-real-token"
        return AuthenticatedUser(id=user_id, role="authenticated")

    monkeypatch.setattr(actor_module, "verify_access_token", fake_verify)

    request = _request({"Authorization": "Bearer a-real-token", "X-Actor": "lead-analyst"})
    actor = await get_current_actor(request)

    # The real verified identity wins even when a (forgeable) X-Actor header
    # is also present.
    assert actor == str(user_id)


@pytest.mark.asyncio
async def test_get_current_actor_falls_back_when_the_token_does_not_verify(monkeypatch):
    async def fake_verify(token, **kwargs):
        raise AuthenticationError()

    monkeypatch.setattr(actor_module, "verify_access_token", fake_verify)

    request = _request({"Authorization": "Bearer not-a-real-token", "X-Actor": "lead-analyst"})
    assert await get_current_actor(request) == "lead-analyst"

    request_no_header = _request({"Authorization": "Bearer not-a-real-token"})
    assert await get_current_actor(request_no_header) == ANONYMOUS_ACTOR


@pytest.mark.asyncio
async def test_get_current_actor_falls_back_with_no_authorization_header_at_all():
    request = _request({"X-Actor": "lead-analyst"})
    assert await get_current_actor(request) == "lead-analyst"

    assert await get_current_actor(_request()) == ANONYMOUS_ACTOR
