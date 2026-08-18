"""Request/response models for the Phase 2.6 knowledge base."""
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from backend.schemas.common import Page, UtcDatetime

ProcessingStatus = Literal["pending", "processing", "ready", "failed"]
SourceType = Literal["upload", "system"]


class DocumentResponse(BaseModel):
    id: UUID = Field(examples=["3f1d2c9a-6b4e-4d7a-9c1f-2b8e5a0d4c31"])
    owner_user_id: Optional[UUID] = Field(
        default=None,
        description="NULL means this is a global document, shared with every caller.",
        examples=["3f1d2c9a-6b4e-4d7a-9c1f-2b8e5a0d4c31"],
    )
    title: str = Field(examples=["Incident Response Runbook"])
    source_type: SourceType = Field(examples=["upload"])
    source_name: str = Field(examples=["incident-response-runbook.pdf"])
    mime_type: str = Field(examples=["application/pdf"])
    processing_status: ProcessingStatus = Field(examples=["ready"])
    error_message: Optional[str] = Field(default=None, examples=[None])
    page_count: Optional[int] = Field(default=None, examples=[12])
    chunk_count: int = Field(examples=[34])
    created_at: UtcDatetime = Field(examples=["2026-07-30T02:10:00+00:00"])
    updated_at: UtcDatetime = Field(examples=["2026-07-30T02:11:00+00:00"])


class DocumentUploadResponse(BaseModel):
    document: DocumentResponse
    reused_existing: bool = Field(
        description="True when identical content was already ingested and this "
        "upload was a no-op (idempotent by checksum).",
        examples=[False],
    )


class DocumentPage(Page[DocumentResponse]):
    pass


class RetrievalPreviewRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000, examples=["how do we contain ransomware?"])
    limit: int = Field(default=5, ge=1, le=20)


class RetrievedChunkResponse(BaseModel):
    document_id: UUID = Field(examples=["3f1d2c9a-6b4e-4d7a-9c1f-2b8e5a0d4c31"])
    document_title: str = Field(examples=["Incident Response Runbook"])
    chunk_id: str = Field(examples=["8c2b1e40-5a77-4a2e-b0d1-9f6c3a5e7b12"])
    chunk_index: Optional[int] = Field(default=None, examples=[4])
    page: Optional[int] = Field(default=None, examples=[3])
    heading: Optional[str] = Field(default=None, examples=["Containment steps"])
    content: str = Field(examples=["Isolate the affected host from the network..."])
    score: float = Field(
        description="Cosine similarity in [0, 1]. Never the raw embedding vector.",
        examples=[0.81],
    )


class RetrievalPreviewResponse(BaseModel):
    query: str = Field(examples=["how do we contain ransomware?"])
    results: List[RetrievedChunkResponse]
    retrieval_metadata: Dict[str, Any] = Field(
        description="Safe, aggregate retrieval facts. Never an embedding vector.",
        examples=[{"result_count": 3, "similarity_threshold": 0.55}],
    )
