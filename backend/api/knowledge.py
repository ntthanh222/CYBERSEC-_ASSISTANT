"""Phase 2.6 knowledge base endpoints.

**Requires a valid Supabase Auth Bearer token on every route**, same as
:mod:`backend.api.chatbot`. ``owner_user_id`` always comes from the verified
JWT `sub` claim, never from the request body. The session used here
(``get_rls_db``) runs as the ``authenticated`` Postgres role, so Row Level
Security (migration 0005) enforces ownership independently of the explicit
checks in :mod:`backend.services.knowledge`.
"""
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import PageParams, page_params
from backend.config.settings import get_settings
from backend.core.actor import get_current_actor
from backend.core.auth import AuthenticatedUser, get_current_user
from backend.core.rate_limit import rate_limit
from backend.database.models.knowledge import KnowledgeDocument
from backend.database.session import get_rls_db
from backend.schemas.health import ErrorResponse
from backend.schemas.knowledge import (
    DocumentPage,
    DocumentResponse,
    DocumentUploadResponse,
    RetrievalPreviewRequest,
    RetrievalPreviewResponse,
)
from backend.services.knowledge import KnowledgeService
from backend.services.rag_retrieval import get_rag_retriever_for_session

router = APIRouter(
    prefix="/api/knowledge", tags=["knowledge"], dependencies=[Depends(get_current_user)]
)

upload_rate_limit = rate_limit(bucket="knowledge_upload", limit=10, window_seconds=60)
retrieval_rate_limit = rate_limit(bucket="knowledge_retrieval", limit=30, window_seconds=60)

_UNAUTHORIZED = {401: {"model": ErrorResponse, "description": "Missing or invalid bearer token."}}


def _document_dict(document: KnowledgeDocument) -> dict[str, Any]:
    return {
        "id": document.id,
        "owner_user_id": document.owner_user_id,
        "title": document.title,
        "source_type": document.source_type,
        "source_name": document.source_name,
        "mime_type": document.mime_type,
        "processing_status": document.processing_status,
        "error_message": document.error_message,
        "page_count": document.page_count,
        "chunk_count": document.chunk_count,
        "created_at": document.created_at,
        "updated_at": document.updated_at,
    }


@router.post(
    "/documents",
    status_code=201,
    summary="Upload a document to the knowledge base",
    description=(
        "Accepts .txt, .md/.markdown and text-layer PDFs. The upload is "
        "extracted, chunked, embedded and made retrievable synchronously; "
        "the response reports the final `processing_status`. Re-uploading "
        "identical content for the same owner is idempotent (by content "
        "checksum) and returns the existing document instead of duplicating it."
    ),
    response_model=DocumentUploadResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Unsupported type, empty, or invalid file."},
        413: {"model": ErrorResponse, "description": "File exceeds the configured size limit."},
        **_UNAUTHORIZED,
    },
    dependencies=[Depends(upload_rate_limit)],
)
async def upload_document(
    file: UploadFile = File(...),
    title: str = Form(default=""),
    session: AsyncSession = Depends(get_rls_db),
    user: AuthenticatedUser = Depends(get_current_user),
    actor: str = Depends(get_current_actor),
) -> dict:
    raw_bytes = await file.read()
    service = KnowledgeService(session)
    outcome = await service.ingest(
        filename=file.filename or "document",
        content_type=file.content_type or "",
        raw_bytes=raw_bytes,
        title=title,
        user_id=user.id,
        actor=actor,
    )
    return {
        "document": _document_dict(outcome.document),
        "reused_existing": outcome.reused,
    }


@router.get(
    "/documents",
    summary="List documents visible to the caller",
    description="The caller's own documents plus every global (system-managed) "
    "document, ordered newest first.",
    response_model=DocumentPage,
    responses={
        422: {"model": ErrorResponse, "description": "Invalid pagination."},
        **_UNAUTHORIZED,
    },
)
async def list_documents(
    pagination: PageParams = Depends(page_params),
    session: AsyncSession = Depends(get_rls_db),
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict:
    service = KnowledgeService(session)
    items, total = await service.list_documents(
        user_id=user.id, page=pagination.page, page_size=pagination.page_size
    )
    return {
        "items": [_document_dict(item) for item in items],
        "total": total,
        "page": pagination.page,
        "page_size": pagination.page_size,
    }


@router.get(
    "/documents/{document_id}",
    summary="Get one document's status",
    description="Only the owning caller or a global document can be read - "
    "anyone else gets 404, never 403.",
    response_model=DocumentResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Document does not exist."},
        **_UNAUTHORIZED,
    },
)
async def get_document(
    document_id: UUID,
    session: AsyncSession = Depends(get_rls_db),
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict:
    service = KnowledgeService(session)
    document = await service.get_document(document_id, user_id=user.id)
    return _document_dict(document)


@router.delete(
    "/documents/{document_id}",
    status_code=204,
    summary="Delete a document",
    description="Deletes the document and, by cascade, all of its chunks. Only "
    "the owning caller can delete it - a global document cannot be deleted "
    "through this endpoint.",
    responses={
        404: {"model": ErrorResponse, "description": "Document does not exist."},
        **_UNAUTHORIZED,
    },
)
async def delete_document(
    document_id: UUID,
    session: AsyncSession = Depends(get_rls_db),
    user: AuthenticatedUser = Depends(get_current_user),
    actor: str = Depends(get_current_actor),
) -> None:
    service = KnowledgeService(session)
    await service.delete_document(document_id, user_id=user.id, actor=actor)


@router.post(
    "/documents/{document_id}/reprocess",
    summary="Re-chunk and re-embed a document",
    description=(
        "Re-runs chunking and embedding from the document's already-stored "
        "content (the raw uploaded file is not retained), using the current "
        "chunk-size/overlap configuration and embedding provider. Only the "
        "owning caller can reprocess a document."
    ),
    response_model=DocumentResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Nothing to reprocess."},
        404: {"model": ErrorResponse, "description": "Document does not exist."},
        **_UNAUTHORIZED,
    },
    dependencies=[Depends(upload_rate_limit)],
)
async def reprocess_document(
    document_id: UUID,
    session: AsyncSession = Depends(get_rls_db),
    user: AuthenticatedUser = Depends(get_current_user),
    actor: str = Depends(get_current_actor),
) -> dict:
    service = KnowledgeService(session)
    document = await service.reprocess(document_id, user_id=user.id, actor=actor)
    return _document_dict(document)


@router.post(
    "/retrieval/preview",
    summary="Preview what the knowledge base would retrieve for a query",
    description="Runs the same retrieval the chatbot uses, scoped to the "
    "caller's own and global documents, without generating an answer.",
    response_model=RetrievalPreviewResponse,
    responses={**_UNAUTHORIZED},
    dependencies=[Depends(retrieval_rate_limit)],
)
async def preview_retrieval(
    payload: RetrievalPreviewRequest,
    session: AsyncSession = Depends(get_rls_db),
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict:
    settings = get_settings()
    retriever = get_rag_retriever_for_session(session)
    documents = await retriever.retrieve(payload.query, user_id=user.id, limit=payload.limit)
    return {
        "query": payload.query,
        "results": [
            {
                "document_id": document.document_id,
                "document_title": document.title,
                "chunk_id": document.id,
                "chunk_index": document.chunk_index,
                "page": document.page,
                "heading": document.heading,
                "content": document.content,
                "score": document.score,
            }
            for document in documents
        ],
        "retrieval_metadata": {
            "result_count": len(documents),
            "similarity_threshold": settings.rag_similarity_threshold,
            "rag_ready": retriever.is_ready,
        },
    }
