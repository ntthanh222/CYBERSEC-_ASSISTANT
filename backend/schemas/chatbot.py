"""Request/response models for the AI Security Assistant."""
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from backend.schemas.common import Page, UtcDatetime

MessageRole = Literal["user", "assistant", "system"]
ChatMode = Literal["fast", "deep"]
IntentName = Literal[
    "greeting",
    "definition",
    "cve_question",
    "url_question",
    "password_question",
    "incident_response",
    "knowledge_rag",
    "sqli_question",
    "ssrf_question",
    "csp_question",
    "general",
]


class ChatRequest(BaseModel):
    message: str = Field(
        min_length=1,
        max_length=4000,
        description="The user's message. Do not include real credentials.",
        examples=["What is CVE-2021-44228 and am I affected?"],
    )
    conversation_id: Optional[UUID] = Field(
        default=None,
        description="Continue an existing conversation. Omit to start a new one.",
        examples=["3f1d2c9a-6b4e-4d7a-9c1f-2b8e5a0d4c31"],
    )
    mode: ChatMode = Field(
        default="fast",
        description=(
            "`fast` answers from the built-in knowledge base without calling an "
            "external provider. `deep` uses the configured external provider "
            "when one exists, and otherwise falls back to local knowledge and "
            "says so in `metadata`."
        ),
        examples=["deep"],
    )


class CitationResponse(BaseModel):
    marker: int = Field(description="The [N] marker referenced in the answer.", examples=[1])
    document_id: Optional[UUID] = Field(
        default=None, examples=["3f1d2c9a-6b4e-4d7a-9c1f-2b8e5a0d4c31"]
    )
    chunk_id: Optional[str] = Field(default=None, examples=["8c2b1e40-5a77-4a2e-b0d1-9f6c3a5e7b12"])
    title: str = Field(examples=["Incident Response Runbook"])
    source: str = Field(examples=["incident-response-runbook.pdf"])
    page: Optional[int] = Field(default=None, examples=[3])
    heading: Optional[str] = Field(default=None, examples=["Containment steps"])
    chunk_index: Optional[int] = Field(default=None, examples=[4])
    score: float = Field(
        description="Cosine similarity in [0, 1]. Never the raw embedding vector.",
        examples=[0.82],
    )


class ChatResponse(BaseModel):
    conversation_id: UUID = Field(examples=["3f1d2c9a-6b4e-4d7a-9c1f-2b8e5a0d4c31"])
    message_id: UUID = Field(examples=["8c2b1e40-5a77-4a2e-b0d1-9f6c3a5e7b12"])
    role: MessageRole = Field(examples=["assistant"])
    content: str = Field(examples=["Log4Shell is a remote code execution flaw..."])
    provider: str = Field(
        description=(
            "The provider that actually produced this text. `local` means the "
            "built-in knowledge base answered; it never means an external model."
        ),
        examples=["local"],
    )
    intent: IntentName = Field(examples=["cve_question"])
    created_at: UtcDatetime = Field(examples=["2026-07-29T02:15:00+00:00"])
    request_id: str = Field(examples=["a1b2c3d4-e5f6-7890-abcd-ef1234567890"])
    citations: List[CitationResponse] = Field(
        default_factory=list,
        description=(
            "Sources the answer drew on, in [N] order. Empty when the answer "
            "is not grounded in the knowledge base - see `metadata.grounded`."
        ),
    )
    metadata: Dict[str, Any] = Field(
        description="Safe routing metadata. Never contains credentials or keys.",
        examples=[
            {
                "mode": "fast",
                "routing_reason": "fast_mode",
                "external_provider_configured": False,
                "fallback_used": False,
                "rag_ready": False,
                "rag_documents": 0,
                "grounded": False,
                "source": "local_knowledge",
            }
        ],
    )


class ConversationCreateRequest(BaseModel):
    title: str = Field(
        default="New conversation",
        max_length=200,
        examples=["Log4Shell triage"],
    )


class ConversationResponse(BaseModel):
    id: UUID = Field(examples=["3f1d2c9a-6b4e-4d7a-9c1f-2b8e5a0d4c31"])
    title: str = Field(examples=["Log4Shell triage"])
    actor: Optional[str] = Field(default=None, examples=["anonymous"])
    created_at: UtcDatetime = Field(examples=["2026-07-29T02:10:00+00:00"])
    updated_at: UtcDatetime = Field(examples=["2026-07-29T02:15:00+00:00"])


class MessageResponse(BaseModel):
    id: UUID = Field(examples=["8c2b1e40-5a77-4a2e-b0d1-9f6c3a5e7b12"])
    conversation_id: UUID = Field(examples=["3f1d2c9a-6b4e-4d7a-9c1f-2b8e5a0d4c31"])
    role: MessageRole = Field(examples=["user"])
    content: str = Field(
        description="Stored content, already redacted of secret-shaped text.",
        examples=["What is CVE-2021-44228?"],
    )
    provider: Optional[str] = Field(default=None, examples=["local"])
    intent: Optional[IntentName] = Field(default=None, examples=["cve_question"])
    metadata: Optional[Dict[str, Any]] = Field(default=None, examples=[{"mode": "fast"}])
    created_at: UtcDatetime = Field(examples=["2026-07-29T02:15:00+00:00"])


class ConversationPage(Page[ConversationResponse]):
    pass


class MessagePage(Page[MessageResponse]):
    pass


class AiHealthResponse(BaseModel):
    status: Literal["healthy", "degraded"] = Field(examples=["degraded"])
    provider: str = Field(examples=["local"])
    provider_configured: bool = Field(examples=[False])
    fallback_provider: str = Field(examples=["local"])
    rag_ready: bool = Field(examples=[False])
    rag_documents: int = Field(examples=[0])
    # Distinct from provider_configured: a key can be present
    # (provider_configured=true) without a real call ever having succeeded.
    # Only diverges from provider_configured when DEMO_REQUIRE_GEMINI=true -
    # see backend/services/assistant.py::describe_ai_health.
    ready: bool = Field(examples=[False])
    model: Optional[str] = Field(default=None, examples=["gemini-2.5-flash"])
    model_supported: Optional[bool] = Field(
        default=None,
        examples=[None],
        description="Whether `model` was found in a live models-list call. null = not checked.",
    )
    demo_require_gemini: bool = Field(examples=[False])
    last_error_category: Optional[
        Literal["NOT_CONFIGURED", "INVALID_KEY", "RATE_LIMITED", "UNAVAILABLE", "DEGRADED"]
    ] = Field(default=None, examples=[None])
    detail: str = Field(
        examples=[
            "No external AI provider is configured (GEMINI_API_KEY is unset). "
            "The assistant answers from its local knowledge base and reports "
            "provider=local. No external call is made."
        ]
    )
