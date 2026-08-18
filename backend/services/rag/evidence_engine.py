"""Local Evidence Engine for RAG Local-First.

Handles local evidence scoring, extractive answering, local multi-doc synthesis,
conflict detection, and no-answer determination without calling external AI models.
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from backend.providers.rag.base import RagDocument
from backend.services.rag.entity_extractor import ExtractedEntities

logger = logging.getLogger("backend.services.rag.evidence_engine")

EXTRACTIVE_CONFIDENCE_THRESHOLD = 0.65
SYNTHESIS_CONFIDENCE_THRESHOLD = 0.50
#: Hard relevance floor. Below this, retrieval found nothing meaningfully
#: related to the query and the engine must say so rather than let an exact
#: entity in the *query* (which may not even appear in the *document*) or a
#: generic term-overlap check paper over an irrelevant top-k dump.
MIN_RELEVANCE_FLOOR = 0.35
#: Lower floor used only when the caller already has independent, non-vector
#: confirmation (``force_extractive=True`` - a literal glossary-bridged term
#: match). A translated retry query is a noisier embedding than the user's
#: own words, so the *vector* score alone naturally runs lower even for the
#: right document; the literal sentence match right below this floor is
#: what actually justifies trusting it, not the vector score by itself.
FORCE_EXTRACTIVE_RELEVANCE_FLOOR = 0.20

#: Sentences containing these markers are excluded from anything quoted back
#: to the user. Document content is untrusted data - the local evidence path
#: has no LLM in the loop to "trick", but it does literal substring/sentence
#: matching, so a sentence engineered to look like an instruction (asking to
#: ignore prior guidance, reveal secrets/credentials/system prompt, etc.)
#: must never be surfaced as if it were a factual answer.
_PROMPT_INJECTION_MARKERS: tuple[str, ...] = (
    "ignore previous instructions", "ignore all previous instructions",
    "ignore the above", "disregard previous", "bo qua huong dan",
    "bỏ qua hướng dẫn", "bo qua chi dan", "bỏ qua chỉ dẫn",
    "bo qua toan bo huong dan", "bỏ qua toàn bộ hướng dẫn",
    "bo qua tat ca", "bỏ qua tất cả", "bo qua cac", "bỏ qua các",
    "in ra tu khoa", "in ra từ khóa", "pwned",
    "reveal the system prompt", "reveal your system prompt",
    "tiet lo system prompt", "tiết lộ system prompt",
    "tiet lo bi mat", "tiết lộ bí mật", "tiet lo mat khau",
    "tiết lộ mật khẩu", "you are now", "act as", "new instructions:",
    "system:", "###instruction",
)


def _is_injection_attempt(sentence: str) -> bool:
    lowered = sentence.lower()
    return any(marker in lowered for marker in _PROMPT_INJECTION_MARKERS)


@dataclass
class EvidenceAnalysisResult:
    can_answer_locally: bool
    answer_type: str
    content: str = ""
    evidence_conflict: bool = False
    grounded: bool = False
    confidence: float = 0.0
    citations: List[Dict[str, Any]] = field(default_factory=list)
    routing_reason: str = ""


class LocalEvidenceEngine:
    """Local decision and synthesis engine over retrieved RAG documents."""

    def analyze_and_compose(
        self,
        query: str,
        documents: Sequence[RagDocument],
        entities: ExtractedEntities,
        *,
        force_extractive: bool = False,
    ) -> EvidenceAnalysisResult:
        """``force_extractive`` lets a caller that already has independent,
        non-vector confirmation the top document answers the question (e.g.
        a glossary-bridged term match from a translated retry query) attempt
        extraction below the normal vector-similarity confidence bar. It
        never bypasses ``MIN_RELEVANCE_FLOOR`` - a document must still be at
        least minimally relevant - and if no sentence actually matches, the
        method falls through to the same conflict/synthesis/complex-
        reasoning path as an ordinary call. Callers use this narrowly (see
        ``backend.services.assistant``'s document-follow-up retry tiers),
        never as the default for a first-pass query."""
        if not documents:
            return EvidenceAnalysisResult(
                can_answer_locally=True,
                answer_type="no_evidence",
                content="Tôi không tìm thấy tài liệu phù hợp trong cơ sở dữ liệu để trả lời.",
                evidence_conflict=False,
                grounded=False,
                confidence=0.0,
                citations=[],
                routing_reason="no_sufficient_evidence",
            )

        top_score = documents[0].score if documents else 0.0

        # Below the hard relevance floor, retrieval didn't actually find
        # anything related to the query - say so instead of letting an exact
        # entity in the query or generic term overlap justify dumping
        # unrelated top-k chunks. force_extractive uses a lower floor (see
        # its constant) because the literal-term match it goes on to require
        # is itself the confidence signal.
        floor = FORCE_EXTRACTIVE_RELEVANCE_FLOOR if force_extractive else MIN_RELEVANCE_FLOOR
        if top_score < floor:
            return EvidenceAnalysisResult(
                can_answer_locally=True,
                answer_type="no_evidence",
                content="Tôi không tìm thấy tài liệu phù hợp trong cơ sở dữ liệu để trả lời.",
                evidence_conflict=False,
                grounded=False,
                confidence=top_score,
                citations=[],
                routing_reason="no_sufficient_evidence",
            )

        # 1. Exact entity / Direct KB fact (Extractive RAG) - tried first, so a
        # clearly relevant, precise answer wins over a conflict banner just
        # because some other lower-relevance retrieved chunk mentions an
        # unrelated severity word.
        if (
            entities.has_exact_entity
            or top_score >= EXTRACTIVE_CONFIDENCE_THRESHOLD
            or force_extractive
        ):
            extractive_answer = self._compose_extractive_answer(query, documents, entities)
            if extractive_answer:
                return EvidenceAnalysisResult(
                    can_answer_locally=True,
                    answer_type="extractive",
                    content=extractive_answer,
                    evidence_conflict=False,
                    grounded=True,
                    confidence=top_score,
                    citations=self._build_citations(documents),
                    routing_reason="extractive_rag",
                )

        # Check for conflicts across documents, scoped to sentences that are
        # actually topically relevant to the query - a severity word showing
        # up in an unrelated table/playbook elsewhere in the retrieved set
        # must not be reported as contradicting the query's own topic.
        has_conflict, conflict_details = self._detect_conflicts(query, documents, entities)
        if has_conflict:
            header = (
                "**Phát hiện dữ liệu không đồng nhất (Conflict Detected):**\n\n"
                f"{conflict_details}\n\n"
                "Dưới đây là thông tin trích xuất từ các nguồn tài liệu khác nhau:"
            )
            return EvidenceAnalysisResult(
                can_answer_locally=True,
                answer_type="conflict",
                content=f"{header}\n\n" + self._compose_multi_doc_summary(documents),
                evidence_conflict=True,
                grounded=True,
                confidence=top_score,
                citations=self._build_citations(documents),
                routing_reason="evidence_conflict_local",
            )

        # 2. Simple Multi-Document Factual Synthesis
        if (
            len(documents) >= 1
            and top_score >= SYNTHESIS_CONFIDENCE_THRESHOLD
            and self._has_query_overlap(query, documents, entities)
        ):
            if not self._requires_complex_reasoning(query):
                synthesis_answer = self._compose_multi_doc_summary(documents)
                return EvidenceAnalysisResult(
                    can_answer_locally=True,
                    answer_type="local_synthesis",
                    content=synthesis_answer,
                    evidence_conflict=False,
                    grounded=True,
                    confidence=top_score,
                    citations=self._build_citations(documents),
                    routing_reason="local_synthesis",
                )

        # Require Gemini for complex reasoning
        return EvidenceAnalysisResult(
            can_answer_locally=False,
            answer_type="complex_reasoning",
            routing_reason="complex_reasoning_required",
            confidence=top_score,
            grounded=True,
            citations=self._build_citations(documents),
        )

    def _detect_conflicts(
        self, query: str, documents: Sequence[RagDocument], entities: ExtractedEntities
    ) -> Tuple[bool, str]:
        topical_terms = self._topical_terms(query, entities)

        # A single document that itself lists multiple severity tiers (e.g.
        # "Severity High -> 15 min, Severity Medium -> 60 min") is presenting
        # a taxonomy, not contradicting itself - only count a document's
        # severity mentions toward conflict detection when it names exactly
        # one severity level in topically-relevant sentences, so cross-
        # document disagreement is what actually gets flagged.
        severity_map: Dict[str, Set[str]] = {}
        for doc in documents:
            doc_severities: Set[str] = set()
            for sentence in re.split(r"(?<=[.!?\n])\s+", doc.content):
                if topical_terms and not any(term in sentence.lower() for term in topical_terms):
                    continue
                for sev in re.findall(r"\b(critical|high|medium|low)\b", sentence, re.IGNORECASE):
                    doc_severities.add(sev.lower())
            if len(doc_severities) == 1:
                severity_map.setdefault(next(iter(doc_severities)), set()).add(doc.title)

        if len(severity_map) > 1 and len(documents) > 1:
            details = [
                f"- **Mức độ {s.upper()}**: trong {', '.join(src)}"
                for s, src in severity_map.items()
            ]
            return True, "\n".join(details)

        return False, ""

    def _compose_extractive_answer(
        self, query: str, documents: Sequence[RagDocument], entities: ExtractedEntities
    ) -> Optional[str]:
        relevant_sentences: List[str] = []
        seen_sentences: Set[str] = set()

        search_terms = entities.all_exact_terms()
        if not search_terms:
            search_terms = [t for t in query.lower().split() if len(t) > 3]

        for idx, doc in enumerate(documents, start=1):
            sentences = re.split(r"[\r\n]+|(?<=[.!?])\s+", doc.content)
            for s in sentences:
                clean_s = s.strip()
                if len(clean_s) < 15:
                    continue
                if _is_injection_attempt(clean_s):
                    continue
                clean_lower = clean_s.lower()
                if any(term.lower() in clean_lower for term in search_terms):
                    if clean_lower not in seen_sentences:
                        seen_sentences.add(clean_lower)
                        relevant_sentences.append(f"- {clean_s} [{idx}]")

        if not relevant_sentences:
            return None

        header = f"Theo thông tin trong Knowledge Base ({documents[0].title}):\n\n"
        return header + "\n".join(relevant_sentences[:5])

    def _compose_multi_doc_summary(self, documents: Sequence[RagDocument]) -> str:
        lines = ["**Tổng hợp thông tin từ Knowledge Base:**\n"]
        for idx, doc in enumerate(documents, start=1):
            source_info = f" ({doc.heading})" if doc.heading else ""
            lines.append(f"### [{idx}] {doc.title}{source_info}")
            sentences = re.split(r"[\r\n]+|(?<=[.!?])\s+", doc.content.strip())
            clean_sentences = [s.strip() for s in sentences if s.strip() and not _is_injection_attempt(s.strip())]
            snippet = "\n".join(clean_sentences).strip()
            if len(snippet) > 400:
                snippet = snippet[:397] + "..."
            lines.append(snippet + "\n")

        return "\n".join(lines)

    def _requires_complex_reasoning(self, query: str) -> bool:
        q = query.lower()
        complex_keywords = (
            "phân tích chuyên sâu",
            "threat model",
            "kịch bản tấn công",
            "attack scenario",
            "executive summary",
            "so sánh chi tiết",
            "chiến lược khắc phục",
            "mitigation strategy",
            "recommendation report",
        )
        return any(k in q for k in complex_keywords)

    def _topical_terms(self, query: str, entities: ExtractedEntities) -> Set[str]:
        exact_terms = {term.lower() for term in entities.all_exact_terms()}
        query_terms = {
            term
            for term in re.findall(r"[\w-]{4,}", query.lower())
            if term not in {"what", "when", "where", "which", "that", "this"}
        }
        return exact_terms | query_terms

    def _has_query_overlap(
        self, query: str, documents: Sequence[RagDocument], entities: ExtractedEntities
    ) -> bool:
        terms = self._topical_terms(query, entities)
        if not terms:
            return False
        combined = "\n".join(doc.content.lower() for doc in documents[:3])
        return any(term in combined for term in terms)

    def _build_citations(self, documents: Sequence[RagDocument]) -> List[Dict[str, Any]]:
        citations = []
        for idx, doc in enumerate(documents, start=1):
            citations.append(
                {
                    "marker": idx,
                    "document_id": doc.document_id,
                    "chunk_id": doc.id,
                    "title": doc.title,
                    "source": doc.source,
                    "page": doc.page,
                    "heading": doc.heading,
                    "chunk_index": doc.chunk_index,
                    "score": doc.score,
                }
            )
        return citations
