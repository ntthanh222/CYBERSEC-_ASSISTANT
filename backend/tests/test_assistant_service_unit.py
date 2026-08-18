"""Direct unit coverage for AssistantService internals not reachable through
the HTTP layer (the schema's own length limits pre-empt the service's)."""
import uuid

import pytest

from backend.core.exceptions import InvalidRequestError, NotFoundError
from backend.providers.llm.mock import MockProvider
from backend.services.assistant import (
    MAX_MESSAGE_CHARS,
    TITLE_MAX_CHARS,
    AssistantService,
    select_provider,
    validate_message,
)
from backend.services.intent import Intent


def test_validate_message_rejects_a_message_over_the_hard_limit():
    with pytest.raises(InvalidRequestError):
        validate_message("a" * (MAX_MESSAGE_CHARS + 1))


def test_select_provider_uses_default_for_deep_mode_general_intent():
    provider = MockProvider()
    chosen, reason = select_provider(
        mode="deep", intent=Intent.GENERAL, default_provider=provider
    )
    assert chosen is provider
    assert reason == "deep_mode"


async def test_create_conversation_rejects_an_overlong_title_at_service_level(
    db_sessionmaker,
):
    async with db_sessionmaker() as session:
        service = AssistantService(session, provider=MockProvider())
        with pytest.raises(InvalidRequestError):
            await service.create_conversation(
                title="x" * (TITLE_MAX_CHARS + 1), user_id=uuid.uuid4(), actor=None
            )


async def test_get_conversation_raises_not_found_for_a_missing_id(db_sessionmaker):
    async with db_sessionmaker() as session:
        service = AssistantService(session, provider=MockProvider())
        with pytest.raises(NotFoundError):
            await service.get_conversation(uuid.uuid4(), user_id=uuid.uuid4())


async def test_delete_conversation_raises_not_found_for_a_missing_id(db_sessionmaker):
    async with db_sessionmaker() as session:
        service = AssistantService(session, provider=MockProvider())
        with pytest.raises(NotFoundError):
            await service.delete_conversation(uuid.uuid4(), user_id=uuid.uuid4(), actor=None)


async def test_list_messages_raises_not_found_for_a_missing_conversation(
    db_sessionmaker,
):
    async with db_sessionmaker() as session:
        service = AssistantService(session, provider=MockProvider())
        with pytest.raises(NotFoundError):
            await service.list_messages(
                uuid.uuid4(), user_id=uuid.uuid4(), page=1, page_size=10
            )
