"""AI Security Assistant endpoints.

Routes validate and delegate; all behaviour lives in
:mod:`backend.services.assistant`.

**Requires a valid Supabase Auth Bearer token on every route** (Phase 2.5B).
``user_id`` always comes from the verified JWT `sub` claim
(:mod:`backend.core.auth`), never from the request. The session used here
(``get_rls_db``) runs as the ``authenticated`` Postgres role with that
identity set, so Row Level Security enforces ownership independently of the
explicit checks in :mod:`backend.services.assistant`.
"""
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import PageParams, page_params
from backend.core.actor import get_current_actor
from backend.core.auth import AuthenticatedUser, get_current_user
from backend.core.rate_limit import rate_limit
from backend.database.models.conversation import Conversation, Message
from backend.database.session import get_rls_db
from backend.schemas.chatbot import (
    ChatRequest,
    ChatResponse,
    ConversationCreateRequest,
    ConversationPage,
    ConversationResponse,
    MessagePage,
)
from backend.schemas.health import ErrorResponse
from backend.services.assistant import AssistantService

router = APIRouter(
    prefix="/api/chatbot", tags=["chatbot"], dependencies=[Depends(get_current_user)]
)

chat_rate_limit = rate_limit(bucket="assistant_chat", limit=30, window_seconds=60)

_PROVIDER_ERRORS = {
    429: {"model": ErrorResponse, "description": "Rate limited (local or upstream)."},
    502: {"model": ErrorResponse, "description": "Upstream AI provider failed."},
    503: {"model": ErrorResponse, "description": "AI provider is not configured."},
    504: {"model": ErrorResponse, "description": "Upstream AI provider timed out."},
}
_UNAUTHORIZED = {401: {"model": ErrorResponse, "description": "Missing or invalid bearer token."}}


def _conversation_dict(conversation: Conversation) -> dict[str, Any]:
    return {
        "id": conversation.id,
        "title": conversation.title,
        "actor": conversation.actor,
        "created_at": conversation.created_at,
        "updated_at": conversation.updated_at,
    }


def _message_dict(message: Message) -> dict[str, Any]:
    return {
        "id": message.id,
        "conversation_id": message.conversation_id,
        "role": message.role,
        "content": message.content,
        "provider": message.provider,
        "intent": message.intent,
        "metadata": message.meta,
        "created_at": message.created_at,
    }


@router.post(
    "/chat",
    summary="Send a message to the assistant",
    description=(
        "Classifies the message, routes it to the appropriate provider and "
        "stores both turns. `provider` in the response always names what "
        "actually produced the answer: `local` means the built-in knowledge "
        "base replied and no external call was made. Messages classified as "
        "password questions are always answered locally and redirected to the "
        "Password Checker, so a pasted credential is never forwarded upstream. "
        "Message content is redacted of secret-shaped text before storage."
    ),
    response_description="The assistant's reply plus honest routing metadata.",
    response_model=ChatResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Empty or oversized message."},
        404: {"model": ErrorResponse, "description": "Conversation does not exist."},
        422: {"model": ErrorResponse, "description": "Request body failed validation."},
        **_UNAUTHORIZED,
        **_PROVIDER_ERRORS,
    },
    dependencies=[Depends(chat_rate_limit)],
)
async def chat(
    request: Request,
    payload: ChatRequest,
    session: AsyncSession = Depends(get_rls_db),
    user: AuthenticatedUser = Depends(get_current_user),
    actor: str = Depends(get_current_actor),
) -> dict:
    service = AssistantService(session)
    conversation, message = await service.chat(
        message=payload.message,
        conversation_id=payload.conversation_id,
        mode=payload.mode,
        user_id=user.id,
        actor=actor,
    )
    meta = message.meta or {}
    return {
        "conversation_id": conversation.id,
        "message_id": message.id,
        "role": message.role,
        "content": message.content,
        "provider": message.provider,
        "intent": message.intent,
        "created_at": message.created_at,
        "request_id": getattr(request.state, "request_id", None),
        "citations": meta.get("citations", []),
        "metadata": meta,
    }


@router.get(
    "/conversations",
    summary="List conversations",
    description="The caller's own conversations, ordered by most recently updated first.",
    response_description="A page of conversations.",
    response_model=ConversationPage,
    responses={
        422: {"model": ErrorResponse, "description": "Invalid pagination."},
        **_UNAUTHORIZED,
    },
)
async def list_conversations(
    pagination: PageParams = Depends(page_params),
    session: AsyncSession = Depends(get_rls_db),
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict:
    service = AssistantService(session)
    items, total = await service.list_conversations(
        user_id=user.id, page=pagination.page, page_size=pagination.page_size
    )
    return {
        "items": [_conversation_dict(item) for item in items],
        "total": total,
        "page": pagination.page,
        "page_size": pagination.page_size,
    }


@router.post(
    "/conversations",
    status_code=201,
    summary="Create an empty conversation",
    description="Creates a conversation with no messages, for a client that wants "
    "an id before the first turn.",
    response_description="The created conversation.",
    response_model=ConversationResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Title too long."},
        422: {"model": ErrorResponse, "description": "Request body failed validation."},
        **_UNAUTHORIZED,
    },
)
async def create_conversation(
    payload: ConversationCreateRequest,
    session: AsyncSession = Depends(get_rls_db),
    user: AuthenticatedUser = Depends(get_current_user),
    actor: str = Depends(get_current_actor),
) -> dict:
    service = AssistantService(session)
    conversation = await service.create_conversation(
        title=payload.title, user_id=user.id, actor=actor
    )
    return _conversation_dict(conversation)


@router.get(
    "/conversations/{conversation_id}",
    summary="Get one conversation",
    description="Metadata only; use the messages endpoint for its turns. Only the "
    "owning caller can see it - anyone else gets 404, never 403, so the id "
    "space cannot be probed.",
    response_description="The conversation.",
    response_model=ConversationResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Conversation does not exist."},
        **_UNAUTHORIZED,
    },
)
async def get_conversation(
    conversation_id: UUID,
    session: AsyncSession = Depends(get_rls_db),
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict:
    service = AssistantService(session)
    conversation = await service.get_conversation(conversation_id, user_id=user.id)
    return _conversation_dict(conversation)


@router.delete(
    "/conversations/{conversation_id}",
    status_code=204,
    summary="Delete a conversation",
    description="Deletes the conversation and, by cascade, all of its messages. "
    "Emits an audit event. Only the owning caller can delete it.",
    response_description="Deleted; no content.",
    responses={
        404: {"model": ErrorResponse, "description": "Conversation does not exist."},
        **_UNAUTHORIZED,
    },
)
async def delete_conversation(
    conversation_id: UUID,
    session: AsyncSession = Depends(get_rls_db),
    user: AuthenticatedUser = Depends(get_current_user),
    actor: str = Depends(get_current_actor),
) -> None:
    service = AssistantService(session)
    await service.delete_conversation(conversation_id, user_id=user.id, actor=actor)


@router.get(
    "/conversations/{conversation_id}/messages",
    summary="List messages in a conversation",
    description="Messages in chronological order, oldest first. Only the owning "
    "caller can list them.",
    response_description="A page of messages.",
    response_model=MessagePage,
    responses={
        404: {"model": ErrorResponse, "description": "Conversation does not exist."},
        422: {"model": ErrorResponse, "description": "Invalid pagination."},
        **_UNAUTHORIZED,
    },
)
async def list_messages(
    conversation_id: UUID,
    pagination: PageParams = Depends(page_params),
    session: AsyncSession = Depends(get_rls_db),
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict:
    service = AssistantService(session)
    items, total = await service.list_messages(
        conversation_id, user_id=user.id, page=pagination.page, page_size=pagination.page_size
    )
    return {
        "items": [_message_dict(item) for item in items],
        "total": total,
        "page": pagination.page,
        "page_size": pagination.page_size,
    }
