"""Retrieval-augmented generation seam.

Phase 2 does **not** implement RAG: there is no vector store, no embedding
model and no document ingestion. What exists here is the interface the
orchestrator already calls, plus a null implementation that honestly returns
nothing, so adding a real retriever later is a substitution rather than a
rewrite of the assistant service.
"""
from backend.providers.rag.base import (
    NullRagRetriever,
    RagDocument,
    RagRetriever,
    get_rag_retriever,
)

__all__ = ["NullRagRetriever", "RagDocument", "RagRetriever", "get_rag_retriever"]
