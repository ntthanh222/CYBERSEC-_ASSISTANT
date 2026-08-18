"""Regression coverage for two live-UI failures found in manual browser testing:

1. RAG follow-up context loss - after a turn is successfully grounded in an
   uploaded document ("Critical hosts -> 15 minutes"), a same-conversation
   follow-up about a different fact in the *same* document ("High hosts ->
   60 minutes", "who approves recovery") was answered "not found" instead of
   the document's actual content, because the Vietnamese follow-up shares no
   literal words with the English document text.
2. A CVE explanation is expected to still route to CVE_QUESTION (not RAG)
   when the user explicitly says to ignore the document, and a topic switch
   to an unrelated definition (JWT) must never resurrect document content.

See backend/services/rag/query_normalizer.py (expand_query_terms),
backend/services/assistant.py (retrieval_query / widen-retry intent gate),
and backend/services/rag/evidence_engine.py for the fix.
"""
import uuid

from backend.providers.llm.mock import MockProvider
from backend.providers.rag.base import RagDocument
from backend.services.assistant import AssistantService
from backend.services.intent import Intent, classify
from backend.services.rag.entity_extractor import ExtractedEntities
from backend.services.rag.evidence_engine import LocalEvidenceEngine
from backend.services.rag.query_normalizer import expand_query_terms

ACME_POLICY_TEXT = (
    "ACME INCIDENT RESPONSE POLICY Critical hosts must be isolated within 15 "
    "minutes. High hosts must be isolated within 60 minutes. System recovery "
    "must be approved by the Security Manager."
)


def _acme_doc(**overrides) -> RagDocument:
    defaults = dict(
        id=str(uuid.uuid4()),
        title="ACME Incident Response Policy",
        content=ACME_POLICY_TEXT,
        score=0.9,
        source="ACME_Incident_Response_Policy.txt",
        document_id=str(uuid.uuid4()),
        page=None,
        heading=None,
        chunk_index=0,
    )
    defaults.update(overrides)
    return RagDocument(**defaults)


class AlwaysHitRetriever:
    """Always returns the same document - isolates the test to whether the
    evidence engine's term-matching (the actual bug) can extract the right
    fact, independent of vector-similarity scoring nuances a unit test can't
    faithfully reproduce."""

    def __init__(self, doc: RagDocument):
        self._doc = doc

    @property
    def is_ready(self) -> bool:
        return True

    async def retrieve(self, query, *, user_id, limit=4):
        return (self._doc,)


# --- 1. expand_query_terms: the cross-lingual bridge itself -----------------


def test_expand_query_terms_bridges_vietnamese_policy_vocabulary():
    expanded = expand_query_terms("Ai phê duyệt việc khôi phục hệ thống?")
    lowered = expanded.lower()
    assert "approve" in lowered or "approved" in lowered
    assert "recovery" in lowered or "recover" in lowered
    assert "system" in lowered


def test_expand_query_terms_is_a_noop_when_nothing_matches():
    original = "Giải thích cách hoạt động của JWT."
    assert expand_query_terms(original) == original


# --- 2. Evidence engine: extraction actually finds the right sentence ------


def test_raw_vietnamese_query_cannot_extract_the_approver_fact():
    """Documents the exact bug: without translation, no literal overlap
    exists between the Vietnamese question and the English document."""
    engine = LocalEvidenceEngine()
    result = engine.analyze_and_compose(
        "Ai phê duyệt việc khôi phục hệ thống?",
        [_acme_doc()],
        ExtractedEntities(),
    )
    assert result.answer_type != "extractive"


def test_expanded_query_extracts_the_high_host_fact():
    engine = LocalEvidenceEngine()
    query = expand_query_terms("Host High phải được cô lập trong bao lâu?")
    result = engine.analyze_and_compose(query, [_acme_doc()], ExtractedEntities())
    assert result.answer_type == "extractive"
    assert "60 minutes" in result.content


def test_expanded_query_extracts_the_recovery_approver_fact():
    engine = LocalEvidenceEngine()
    query = expand_query_terms("Ai phê duyệt việc khôi phục hệ thống?")
    result = engine.analyze_and_compose(query, [_acme_doc()], ExtractedEntities())
    assert result.answer_type == "extractive"
    assert "Security Manager" in result.content


def test_expanded_query_does_not_invent_a_password_rotation_fact():
    """The document never mentions password rotation - expansion must not
    cause a fact to be fabricated or an unrelated sentence misrepresented
    as answering the question."""
    engine = LocalEvidenceEngine()
    query = expand_query_terms(
        "Theo tài liệu này, mật khẩu phải đổi sau bao nhiêu ngày?"
    )
    result = engine.analyze_and_compose(query, [_acme_doc()], ExtractedEntities())
    assert result.answer_type != "extractive"


# --- 3. End-to-end: same conversation, sequential follow-ups ---------------


async def test_conversation_follow_ups_reuse_the_grounded_document(db_sessionmaker):
    """The exact sequence from the live-UI regression report, run through
    AssistantService.chat() turn by turn in a single conversation."""
    async with db_sessionmaker() as session:
        service = AssistantService(
            session, provider=MockProvider(), retriever=AlwaysHitRetriever(_acme_doc())
        )
        user_id = uuid.uuid4()

        conversation, msg1 = await service.chat(
            message=(
                "Theo tài liệu tôi vừa upload, host Critical phải được cô lập "
                "trong bao lâu?"
            ),
            conversation_id=None,
            mode="fast",
            user_id=user_id,
            actor="tester",
        )
        assert msg1.meta["grounded"] is True
        assert "15 minutes" in msg1.content

        _, msg2 = await service.chat(
            message="Host High phải được cô lập trong bao lâu?",
            conversation_id=conversation.id,
            mode="fast",
            user_id=user_id,
            actor="tester",
        )
        assert "60 minutes" in msg2.content

        _, msg3 = await service.chat(
            message="Ai phê duyệt việc khôi phục hệ thống?",
            conversation_id=conversation.id,
            mode="fast",
            user_id=user_id,
            actor="tester",
        )
        assert "Security Manager" in msg3.content

        _, msg4 = await service.chat(
            message="Theo tài liệu này, mật khẩu phải đổi sau bao nhiêu ngày?",
            conversation_id=conversation.id,
            mode="fast",
            user_id=user_id,
            actor="tester",
        )
        # Must not invent a day count: no grounded claim, and the response
        # says plainly that it could not find the answer.
        assert msg4.meta["grounded"] is False
        assert "chưa tìm thấy" in msg4.content.lower()


# --- 4. Leaving RAG context: explicit override and topic switch ------------


def test_ignore_document_instruction_routes_to_cve_not_rag():
    intent = classify("Bỏ qua tài liệu vừa rồi. CVE-2021-44228 là gì?")
    assert intent is Intent.CVE_QUESTION


def test_topic_switch_to_definition_is_not_eligible_for_document_widen():
    """JWT is a plain definition question, not a document follow-up. It must
    classify outside {GENERAL, KNOWLEDGE_RAG} - the only intents the
    assistant widens a failed retrieval for - so a prior grounded document
    can never leak into an unrelated topic switch."""
    intent = classify("Bây giờ chuyển chủ đề: giải thích cách hoạt động của JWT.")
    assert intent not in (Intent.GENERAL, Intent.KNOWLEDGE_RAG)
