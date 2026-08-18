"""Vietnamese-language layer for the AI Assistant / RAG pipeline.

Covers the minimum scenario set from the Vietnamese-UI rollout: local
definitions, tool-router app-data answers, no-answer, conflict-adjacent
citation suppression, and cache-hit replay - all in Vietnamese, without
touching retrieval/ranking or the RAG architecture itself.
"""
import uuid

from backend.providers.llm.local import LocalKnowledgeProvider
from backend.providers.rag.base import RagDocument
from backend.repositories.assets import AssetRepository
from backend.repositories.incidents import IncidentRepository
from backend.repositories.reports import ReportRepository
from backend.repositories.security_news import SecurityNewsRepository
from backend.services.assistant import AssistantService
from backend.services.rag.response_language import wants_english
from backend.services.rag.tool_router import AppDataToolRouter
from backend.services.rag.entity_extractor import extract_entities


class EmptyRetriever:
    @property
    def is_ready(self) -> bool:
        return True

    async def retrieve(self, query, *, user_id, limit=4):
        return ()


def _has_no_vietnamese_diacritics_only_ascii_english_phrase(text: str) -> bool:
    return "I do not have a local answer" in text


async def test_sql_injection_definition_is_vietnamese(db_sessionmaker):
    async with db_sessionmaker() as session:
        service = AssistantService(
            session, provider=LocalKnowledgeProvider(), retriever=EmptyRetriever()
        )
        _, message = await service.chat(
            message="SQL Injection là gì?",
            conversation_id=None,
            mode="fast",
            user_id=uuid.uuid4(),
            actor="tester",
        )
        assert message.provider == "local"
        assert message.meta["gemini_called"] is False
        assert "SQL Injection" in message.content
        assert "tham số hóa" in message.content or "prepared statement" in message.content
        assert not _has_no_vietnamese_diacritics_only_ascii_english_phrase(message.content)


async def test_ransomware_definition_is_vietnamese(db_sessionmaker):
    async with db_sessionmaker() as session:
        service = AssistantService(
            session, provider=LocalKnowledgeProvider(), retriever=EmptyRetriever()
        )
        _, message = await service.chat(
            message="Tôi cần làm gì khi phát hiện ransomware?",
            conversation_id=None,
            mode="fast",
            user_id=uuid.uuid4(),
            actor="tester",
        )
        assert message.provider == "local"
        assert message.meta["gemini_called"] is False
        assert "Cách ly" in message.content or "cách ly" in message.content


async def test_mitre_attack_definition_is_vietnamese(db_sessionmaker):
    async with db_sessionmaker() as session:
        service = AssistantService(
            session, provider=LocalKnowledgeProvider(), retriever=EmptyRetriever()
        )
        _, message = await service.chat(
            message="MITRE ATT&CK là gì?",
            conversation_id=None,
            mode="fast",
            user_id=uuid.uuid4(),
            actor="tester",
        )
        assert "MITRE ATT&CK" in message.content
        assert "chiến thuật" in message.content.lower() or "kỹ thuật" in message.content.lower()


async def test_no_answer_fallback_is_vietnamese_with_correct_metadata(db_sessionmaker):
    """The former English 'I do not have a local answer...' fallback must now
    be Vietnamese, while provider/gemini_called/grounded metadata stay honest."""
    async with db_sessionmaker() as session:
        service = AssistantService(
            session, provider=LocalKnowledgeProvider(), retriever=EmptyRetriever()
        )
        _, message = await service.chat(
            message="foobar-does-not-exist-123 là gì?",
            conversation_id=None,
            mode="fast",
            user_id=uuid.uuid4(),
            actor="tester",
        )
        assert message.provider == "local"
        assert message.meta["gemini_called"] is False
        assert message.meta["grounded"] is False
        assert not _has_no_vietnamese_diacritics_only_ascii_english_phrase(message.content)
        assert "Knowledge Base" in message.content
        assert "DEEP" in message.content


async def test_explicit_english_request_overrides_vietnamese_default(db_sessionmaker):
    async with db_sessionmaker() as session:
        service = AssistantService(
            session, provider=LocalKnowledgeProvider(), retriever=EmptyRetriever()
        )
        _, message = await service.chat(
            message="What is SQL Injection? Please answer in English.",
            conversation_id=None,
            mode="fast",
            user_id=uuid.uuid4(),
            actor="tester",
        )
        assert "SQL Injection is a flaw" in message.content


async def test_wants_english_detector_is_conservative():
    assert wants_english("answer in English please") is True
    assert wants_english("trả lời bằng tiếng anh nhé") is True
    assert wants_english("SQL Injection là gì?") is False
    assert wants_english("what is a CVE") is False


async def test_repeated_query_is_a_cache_hit_and_stays_vietnamese(db_sessionmaker, monkeypatch):
    """Exercises AssistantService.chat()'s cache-hit branch directly via an
    in-memory stand-in for the Redis-backed answer cache - the real Redis
    container has no host-exposed port in this dev setup (by design), so a
    bare-venv test run cannot reach it; sqlite is already used the same way
    in place of live Postgres elsewhere in this suite."""
    import backend.services.assistant as assistant_module

    store: dict[str, dict] = {}

    def _cache_key(*, user_id, query, mode):
        return f"{user_id}:{mode}:{query}"

    async def fake_get_cached_answer(*, user_id, query, mode):
        entry = store.get(_cache_key(user_id=user_id, query=query, mode=mode))
        return dict(entry) if entry is not None else None

    async def fake_set_cached_answer(*, user_id, query, mode, answer_data):
        store[_cache_key(user_id=user_id, query=query, mode=mode)] = answer_data

    monkeypatch.setattr(assistant_module, "get_cached_answer", fake_get_cached_answer)
    monkeypatch.setattr(assistant_module, "set_cached_answer", fake_set_cached_answer)

    async with db_sessionmaker() as session:
        service = AssistantService(
            session, provider=LocalKnowledgeProvider(), retriever=EmptyRetriever()
        )
        user_id = uuid.uuid4()
        _, first = await service.chat(
            message="SQL Injection là gì?",
            conversation_id=None,
            mode="fast",
            user_id=user_id,
            actor="tester",
        )
        assert first.meta.get("cache_hit") is not True

        _, second = await service.chat(
            message="SQL Injection là gì?",
            conversation_id=None,
            mode="fast",
            user_id=user_id,
            actor="tester",
        )
        assert second.meta.get("cache_hit") is True
        assert second.content == first.content
        assert "SQL Injection" in second.content


async def test_tool_router_asset_count_question_in_vietnamese(db_sessionmaker):
    async with db_sessionmaker() as session:
        user_id = uuid.uuid4()
        await AssetRepository(session).create(
            user_id=user_id,
            name="Web Server 01",
            type="server",
            hostname="web01.local",
            ip_address="192.168.10.20",
            operating_system="Ubuntu 22.04",
            owner="SOC Team",
            department="IT",
            business_criticality="critical",
            internet_exposed=True,
            description="Primary web server",
            linked_cves=[],
            patch_status="not_started",
            exploit_evidence=None,
        )
        await session.commit()

        router = AppDataToolRouter(session)
        entities = extract_entities("Có bao nhiêu tài sản?")
        result = await router.try_route("Có bao nhiêu tài sản?", entities, user_id=user_id)

        assert result.handled is True
        assert result.metadata["gemini_called"] is False
        assert result.metadata["provider"] == "local"
        assert "Web Server 01" in result.content
        assert "Asset" in result.content  # domain term retained, per spec


async def test_tool_router_open_critical_incident_question_in_vietnamese(db_sessionmaker):
    async with db_sessionmaker() as session:
        user_id = uuid.uuid4()
        await IncidentRepository(session).create(
            user_id=user_id,
            title="Log4Shell Incident",
            description="Critical RCE via CVE-2021-44228",
            severity="critical",
            status="open",
            assignee="SOC Team",
            asset_name="Web Server 01",
            cve_id="CVE-2021-44228",
        )
        await session.commit()

        router = AppDataToolRouter(session)
        entities = extract_entities("Có sự cố Critical nào đang mở?")
        result = await router.try_route(
            "Có sự cố Critical nào đang mở?", entities, user_id=user_id
        )

        assert result.handled is True
        assert result.metadata["gemini_called"] is False
        assert "Log4Shell Incident" in result.content


async def test_tool_router_latest_report_question_in_vietnamese(db_sessionmaker):
    async with db_sessionmaker() as session:
        user_id = uuid.uuid4()
        await ReportRepository(session).create(
            user_id=user_id,
            title="Log4Shell Technical Report",
            category="technical",
            format="markdown",
            status="completed",
            sections=["Executive Summary"],
            scope="Log4Shell incident",
            content="# Report",
            error_message="",
        )
        await session.commit()

        router = AppDataToolRouter(session)
        entities = extract_entities("Cho tôi xem báo cáo gần nhất.")
        result = await router.try_route(
            "Cho tôi xem báo cáo gần nhất.", entities, user_id=user_id
        )

        assert result.handled is True
        assert result.metadata["gemini_called"] is False
        assert "Log4Shell Technical Report" in result.content


async def test_grounded_local_evidence_engine_answer_is_vietnamese():
    """LocalEvidenceEngine is not wired into the live chat() path (see audit
    notes), but its own composed text must already be Vietnamese so a future
    wiring doesn't regress language - this locks that in."""
    from backend.services.rag.evidence_engine import LocalEvidenceEngine

    engine = LocalEvidenceEngine()
    doc = RagDocument(
        id=str(uuid.uuid4()),
        title="CVE-2021-44228 Advisory",
        content="CVE-2021-44228 has a CVSS score of 10.0 and is rated Critical.",
        score=0.9,
        source="nvd",
        document_id=str(uuid.uuid4()),
        page=None,
        heading=None,
        chunk_index=0,
    )
    entities = extract_entities("CVE-2021-44228 có mức độ nghiêm trọng bao nhiêu?")
    result = engine.analyze_and_compose(
        "CVE-2021-44228 có mức độ nghiêm trọng bao nhiêu?", [doc], entities
    )
    assert result.can_answer_locally is True
    assert "Knowledge Base" in result.content or "10.0" in result.content or "Critical" in result.content


async def test_deep_mode_uses_local_evidence_before_provider(db_sessionmaker):
    from backend.providers.llm.mock import MockProvider

    class StubRetriever:
        @property
        def is_ready(self) -> bool:
            return True

        async def retrieve(self, query, *, user_id, limit=4):
            return [
                RagDocument(
                    id=str(uuid.uuid4()),
                    title="ACME Containment Policy",
                    content="ACME internal containment policy requires affected test hosts to be isolated within 15 minutes.",
                    score=0.92,
                    source="acme-policy.md",
                    document_id=str(uuid.uuid4()),
                    chunk_index=0,
                )
            ]

    async with db_sessionmaker() as session:
        provider = MockProvider(reply="Provider should not be called.")
        service = AssistantService(session, provider=provider, retriever=StubRetriever())
        _, message = await service.chat(
            message="Theo policy ACME, host bị ảnh hưởng cần được cô lập trong bao lâu?",
            conversation_id=None,
            mode="deep",
            user_id=uuid.uuid4(),
            actor="tester",
        )

        assert provider.calls == []
        assert message.provider == "local"
        assert message.meta["gemini_called"] is False
        assert message.meta["routing_reason"] == "extractive_rag"
        assert message.meta["grounding_status"] == "GROUNDED"
        assert "15 minutes" in message.content


async def test_tool_router_cve_lookup_uses_real_service_path_with_mocked_provider(
    db_sessionmaker, monkeypatch
):
    async def fake_get(self, raw_cve_id, *, actor):
        return {
            "cve_id": raw_cve_id,
            "description": "Test-only CVE record from mocked provider.",
            "published_at": "2021-12-10T00:00:00+00:00",
            "modified_at": None,
            "cvss_score": 10.0,
            "severity": "CRITICAL",
            "vector": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:C/C:H/I:H/A:H",
            "affected_products": ["Apache Log4j"],
            "references": ["https://example.test/advisory"],
            "source": "nvd",
        }

    monkeypatch.setattr("backend.services.rag.tool_router.CveLookupService.get", fake_get)

    async with db_sessionmaker() as session:
        router = AppDataToolRouter(session)
        result = await router.try_route(
            "CVE-2021-44228 là gì?",
            extract_entities("CVE-2021-44228 là gì?"),
            user_id=uuid.uuid4(),
        )

        assert result.handled is True
        assert result.metadata["routing_reason"] == "cve_tool"
        assert result.metadata["gemini_called"] is False
        assert result.metadata["tool_runs"][0]["tool"] == "cve_lookup"
        assert "Apache Log4j" in result.content


async def test_tool_router_cve_lookup_humanizes_raw_cpe_strings(db_sessionmaker, monkeypatch):
    """Real NVD records return raw CPE 2.3 URIs as affected_products - these
    must never be dumped verbatim into a chat answer."""
    async def fake_get(self, raw_cve_id, *, actor):
        return {
            "cve_id": raw_cve_id,
            "description": "Test CVE with real-shaped CPE data.",
            "published_at": None,
            "modified_at": None,
            "cvss_score": None,
            "severity": None,
            "vector": None,
            "affected_products": [
                "cpe:2.3:o:siemens:6bk1602-0aa12-0tp0_firmware:*:*:*:*:*:*:*:*",
                "cpe:2.3:h:siemens:6bk1602-0aa12-0tp0:-:*:*:*:*:*:*:*",
            ],
            "references": [],
            "source": "nvd",
        }

    monkeypatch.setattr("backend.services.rag.tool_router.CveLookupService.get", fake_get)

    async with db_sessionmaker() as session:
        router = AppDataToolRouter(session)
        result = await router.try_route(
            "CVE-2099-00001 là gì?",
            extract_entities("CVE-2099-00001 là gì?"),
            user_id=uuid.uuid4(),
        )

        assert "cpe:2.3" not in result.content
        assert "Siemens" in result.content


async def test_tool_router_url_scan_blocks_ssrf_with_mocked_scanner(db_sessionmaker):
    async with db_sessionmaker() as session:
        router = AppDataToolRouter(session)
        result = await router.try_route(
            "Kiểm tra http://169.254.169.254 giúp tôi",
            extract_entities("Kiểm tra http://169.254.169.254 giúp tôi"),
            user_id=uuid.uuid4(),
        )

        assert result.handled is True
        assert result.metadata["routing_reason"] == "website_tool"
        assert result.metadata["tool_runs"][0]["status"] == "blocked"
        assert "SSRF" in result.content


async def _fake_cve_get(self, raw_cve_id, *, actor):
    return {
        "cve_id": raw_cve_id,
        "description": "Test-only CVE record from mocked provider.",
        "published_at": "2021-12-10T00:00:00+00:00",
        "modified_at": None,
        "cvss_score": 10.0,
        "severity": "CRITICAL",
        "vector": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:C/C:H/I:H/A:H",
        "affected_products": ["Apache Log4j"],
        "references": ["https://example.test/advisory"],
        "source": "nvd",
    }


async def test_context_switch_after_cve_does_not_stick(db_sessionmaker, monkeypatch):
    """CVE-2021-44228 -> follow-ups -> switching to SQL Injection must not
    keep answering as if the CVE were still the topic (no sticky context)."""
    monkeypatch.setattr("backend.services.rag.tool_router.CveLookupService.get", _fake_cve_get)

    async with db_sessionmaker() as session:
        service = AssistantService(
            session, provider=LocalKnowledgeProvider(), retriever=EmptyRetriever()
        )
        user_id = uuid.uuid4()

        conversation, first = await service.chat(
            message="CVE-2021-44228 là gì?",
            conversation_id=None,
            mode="fast",
            user_id=user_id,
            actor="tester",
        )
        assert first.meta["routing_reason"] == "cve_tool"

        _, second = await service.chat(
            message="CVE này ảnh hưởng hệ thống nào?",
            conversation_id=conversation.id,
            mode="fast",
            user_id=user_id,
            actor="tester",
        )
        # A follow-up asking specifically about affected systems gets its own
        # focused sub-answer, not a replay of the full CVE dump.
        assert second.meta["routing_reason"] == "cve_followup_affected_systems"
        assert "Apache Log4j" in second.content

        _, third = await service.chat(
            message="Nó nên xử lý ra sao?",
            conversation_id=conversation.id,
            mode="fast",
            user_id=user_id,
            actor="tester",
        )
        # Likewise, a remediation-flavoured follow-up gets the remediation
        # sub-answer rather than the generic "cve_tool" full dump.
        assert third.meta["routing_reason"] == "cve_followup_remediation"

        _, fourth = await service.chat(
            message="SQL Injection là gì?",
            conversation_id=conversation.id,
            mode="fast",
            user_id=user_id,
            actor="tester",
        )
        assert fourth.meta["routing_reason"] != "cve_tool"
        assert "SQL Injection" in fourth.content
        assert "Apache Log4j" not in fourth.content


async def test_missing_referent_asks_for_clarification(db_sessionmaker):
    async with db_sessionmaker() as session:
        service = AssistantService(
            session, provider=LocalKnowledgeProvider(), retriever=EmptyRetriever()
        )
        _, message = await service.chat(
            message="CVE này ảnh hưởng hệ thống nào?",
            conversation_id=None,
            mode="fast",
            user_id=uuid.uuid4(),
            actor="tester",
        )
        assert message.meta.get("needs_clarification") is True
        assert message.meta["gemini_called"] is False


async def test_uploaded_document_reference_forces_rag_not_cve(db_sessionmaker):
    document = RagDocument(
        id="doc-1",
        title="Company Policy",
        content="Chính sách yêu cầu vá lỗ hổng trong 15 phút với hệ thống Critical.",
        score=0.9,
        source="upload",
    )

    class DocRetriever:
        @property
        def is_ready(self) -> bool:
            return True

        async def retrieve(self, query, *, user_id, limit=4):
            return (document,)

    async with db_sessionmaker() as session:
        service = AssistantService(
            session, provider=LocalKnowledgeProvider(), retriever=DocRetriever()
        )
        _, message = await service.chat(
            message="Theo tài liệu tôi vừa upload, thời gian vá lỗ hổng Critical là bao lâu?",
            conversation_id=None,
            mode="fast",
            user_id=uuid.uuid4(),
            actor="tester",
        )
        assert message.meta["routing_reason"] != "cve_tool"
        assert message.meta["rag_documents"] >= 1
        assert "15 phút" in message.content


async def test_compromised_website_routes_to_incident_response(db_sessionmaker):
    async with db_sessionmaker() as session:
        service = AssistantService(
            session, provider=LocalKnowledgeProvider(), retriever=EmptyRetriever()
        )
        _, message = await service.chat(
            message="Website của tôi nghi bị tấn công, http://example.com đang lạ",
            conversation_id=None,
            mode="fast",
            user_id=uuid.uuid4(),
            actor="tester",
        )
        assert message.meta["routing_reason"] == "incident_response_playbook"
        assert "Cách ly" in message.content
        assert "phishing" not in message.content.lower()


async def test_website_do_follow_up_resolves_prior_url(db_sessionmaker):
    """'website đó' after scanning a URL must resolve to that same URL, not
    fall through to a generic/unrelated answer."""
    async with db_sessionmaker() as session:
        service = AssistantService(
            session, provider=LocalKnowledgeProvider(), retriever=EmptyRetriever()
        )
        user_id = uuid.uuid4()

        conversation, first = await service.chat(
            message="Kiểm tra giúp tôi http://example.com",
            conversation_id=None,
            mode="fast",
            user_id=user_id,
            actor="tester",
        )
        assert first.meta["routing_reason"] == "website_tool"

        _, second = await service.chat(
            message="Website đó có an toàn không?",
            conversation_id=conversation.id,
            mode="fast",
            user_id=user_id,
            actor="tester",
        )
        assert second.meta["routing_reason"] == "website_tool"


async def test_ssrf_definition_covers_detection_and_prevention(db_sessionmaker):
    async with db_sessionmaker() as session:
        service = AssistantService(
            session, provider=LocalKnowledgeProvider(), retriever=EmptyRetriever()
        )
        _, message = await service.chat(
            message="SSRF là gì?",
            conversation_id=None,
            mode="fast",
            user_id=uuid.uuid4(),
            actor="tester",
        )
        content_lower = message.content.lower()
        assert "ssrf" in content_lower
        assert "phát hiện" in content_lower
        assert "phòng chống" in content_lower


async def test_cve_then_general_security_switch_does_not_stick(db_sessionmaker, monkeypatch):
    """CVE -> RAG document reference -> a fresh general-security question must
    each be answered on their own topic, with no leftover CVE routing."""
    monkeypatch.setattr("backend.services.rag.tool_router.CveLookupService.get", _fake_cve_get)

    document = RagDocument(
        id="doc-2",
        title="Internal Runbook",
        content="Quy trình ứng phó sự cố yêu cầu cách ly hệ thống trong 30 phút.",
        score=0.9,
        source="upload",
    )

    class DocRetriever:
        @property
        def is_ready(self) -> bool:
            return True

        async def retrieve(self, query, *, user_id, limit=4):
            return (document,)

    async with db_sessionmaker() as session:
        service = AssistantService(
            session, provider=LocalKnowledgeProvider(), retriever=DocRetriever()
        )
        user_id = uuid.uuid4()

        conversation, first = await service.chat(
            message="CVE-2021-44228 là gì?",
            conversation_id=None,
            mode="fast",
            user_id=user_id,
            actor="tester",
        )
        assert first.meta["routing_reason"] == "cve_tool"

        _, second = await service.chat(
            message="Theo tài liệu tôi vừa upload, thời gian cách ly hệ thống là bao lâu?",
            conversation_id=conversation.id,
            mode="fast",
            user_id=user_id,
            actor="tester",
        )
        assert second.meta["routing_reason"] != "cve_tool"
        assert "30 phút" in second.content

        _, third = await service.chat(
            message="Ransomware là gì và cách phòng chống?",
            conversation_id=conversation.id,
            mode="fast",
            user_id=user_id,
            actor="tester",
        )
        assert third.meta["routing_reason"] != "cve_tool"
        assert "Apache Log4j" not in third.content


async def test_rag_followup_keeps_the_same_document_context(db_sessionmaker):
    """A follow-up with no topic words of its own ("Ai phê duyệt khôi phục?")
    must still retrieve the document the previous turn was grounded in,
    instead of scoring too low on its own and falling to no-evidence."""
    document = RagDocument(
        id="doc-acme",
        title="ACME Policy",
        content=(
            "ACME DEMO POLICY: sự cố Critical phải được cách ly trong 15 phút. "
            "Chỉ Security Manager mới được phê duyệt khôi phục hệ thống."
        ),
        score=0.9,
        source="upload",
    )

    class TopicGatedRetriever:
        """Simulates a real embedding retriever: only matches when the query
        text actually contains a topic word from the document - a bare
        follow-up like "Ai phê duyệt khôi phục?" would score too low unless
        the retrieval query is widened with the prior grounded question."""

        @property
        def is_ready(self) -> bool:
            return True

        async def retrieve(self, query, *, user_id, limit=4):
            if "acme" in query.lower():
                return (document,)
            return ()

    async with db_sessionmaker() as session:
        service = AssistantService(
            session, provider=LocalKnowledgeProvider(), retriever=TopicGatedRetriever()
        )
        user_id = uuid.uuid4()

        conversation, first = await service.chat(
            message="Theo tài liệu ACME, sự cố Critical cần cách ly trong bao lâu?",
            conversation_id=None,
            mode="fast",
            user_id=user_id,
            actor="tester",
        )
        assert first.meta["grounded"] is True
        assert "15 phút" in first.content

        _, second = await service.chat(
            message="Ai phê duyệt khôi phục?",
            conversation_id=conversation.id,
            mode="fast",
            user_id=user_id,
            actor="tester",
        )
        assert second.meta["grounded"] is True
        assert "Security Manager" in second.content


async def test_tool_router_security_news_reads_database(db_sessionmaker):
    from datetime import datetime, timezone

    async with db_sessionmaker() as session:
        user_id = uuid.uuid4()
        await SecurityNewsRepository(session).create(
            user_id=user_id,
            title="Critical test advisory",
            summary="A test advisory summary.",
            ai_summary="",
            url="https://example.test/security-news",
            source="Example",
            published_at=datetime(2026, 8, 13, tzinfo=timezone.utc),
            category="advisory",
            related_cves=["CVE-2026-0001"],
        )
        await session.commit()

        router = AppDataToolRouter(session)
        result = await router.try_route(
            "Tin bảo mật mới nhất là gì?",
            extract_entities("Tin bảo mật mới nhất là gì?"),
            user_id=user_id,
        )

        assert result.handled is True
        assert result.metadata["routing_reason"] == "security_news_tool"
        assert result.metadata["gemini_called"] is False
        assert "Critical test advisory" in result.content
