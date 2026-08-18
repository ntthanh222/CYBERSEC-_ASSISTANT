"""KnowledgeService: ingestion pipeline, idempotency, ownership, reprocess."""
import uuid

import pytest

from backend.core.exceptions import (
    InvalidRequestError,
    NotFoundError,
    PayloadTooLargeError,
    UnsupportedMediaTypeError,
)
from backend.services.knowledge import KnowledgeService

from ._knowledge_fakes import FakeEmbeddingProvider
from .conftest import TEST_USER_A, TEST_USER_B


async def test_ingest_txt_reaches_ready_with_chunks(db_sessionmaker):
    async with db_sessionmaker() as session:
        service = KnowledgeService(session, embedding_provider=FakeEmbeddingProvider())
        outcome = await service.ingest(
            filename="notes.txt",
            content_type="text/plain",
            raw_bytes=b"Some useful security notes for the team.",
            title="Team Notes",
            user_id=TEST_USER_A.id,
            actor="tester",
        )
        assert outcome.document.processing_status == "ready"
        assert outcome.document.chunk_count == 1
        assert outcome.reused is False


async def test_duplicate_upload_is_idempotent_by_checksum(db_sessionmaker):
    async with db_sessionmaker() as session:
        service = KnowledgeService(session, embedding_provider=FakeEmbeddingProvider())
        first = await service.ingest(
            filename="notes.txt",
            content_type="text/plain",
            raw_bytes=b"Identical content.",
            title="Notes",
            user_id=TEST_USER_A.id,
            actor="tester",
        )
        second = await service.ingest(
            filename="notes-renamed.txt",
            content_type="text/plain",
            raw_bytes=b"Identical content.",
            title="Notes Again",
            user_id=TEST_USER_A.id,
            actor="tester",
        )
        assert second.reused is True
        assert second.document.id == first.document.id


async def test_different_users_uploading_identical_content_get_separate_documents(
    db_sessionmaker,
):
    async with db_sessionmaker() as session:
        service = KnowledgeService(session, embedding_provider=FakeEmbeddingProvider())
        a = await service.ingest(
            filename="notes.txt",
            content_type="text/plain",
            raw_bytes=b"Shared wording, different owners.",
            title="A's copy",
            user_id=TEST_USER_A.id,
            actor="tester",
        )
        b = await service.ingest(
            filename="notes.txt",
            content_type="text/plain",
            raw_bytes=b"Shared wording, different owners.",
            title="B's copy",
            user_id=TEST_USER_B.id,
            actor="tester",
        )
        assert a.document.id != b.document.id
        assert a.document.owner_user_id == TEST_USER_A.id
        assert b.document.owner_user_id == TEST_USER_B.id


async def test_oversized_upload_is_rejected(db_sessionmaker, monkeypatch):
    from backend.config import settings as settings_module

    monkeypatch.setenv("RAG_MAX_UPLOAD_BYTES", "10")
    settings_module.get_settings.cache_clear()
    try:
        async with db_sessionmaker() as session:
            service = KnowledgeService(session, embedding_provider=FakeEmbeddingProvider())
            with pytest.raises(PayloadTooLargeError):
                await service.ingest(
                    filename="big.txt",
                    content_type="text/plain",
                    raw_bytes=b"This is definitely more than ten bytes long.",
                    title=None,
                    user_id=TEST_USER_A.id,
                    actor="tester",
                )
    finally:
        settings_module.get_settings.cache_clear()


async def test_empty_upload_is_rejected(db_sessionmaker):
    async with db_sessionmaker() as session:
        service = KnowledgeService(session, embedding_provider=FakeEmbeddingProvider())
        with pytest.raises(InvalidRequestError):
            await service.ingest(
                filename="empty.txt",
                content_type="text/plain",
                raw_bytes=b"",
                title=None,
                user_id=TEST_USER_A.id,
                actor="tester",
            )


async def test_unsupported_file_type_is_rejected(db_sessionmaker):
    async with db_sessionmaker() as session:
        service = KnowledgeService(session, embedding_provider=FakeEmbeddingProvider())
        with pytest.raises(UnsupportedMediaTypeError):
            await service.ingest(
                filename="archive.zip",
                content_type="application/zip",
                raw_bytes=b"PK\x03\x04fake zip binary content\x01\x02\x05\x06",
                title=None,
                user_id=TEST_USER_A.id,
                actor="tester",
            )


async def test_malicious_filename_is_sanitized_and_never_used_as_a_path(db_sessionmaker):
    async with db_sessionmaker() as session:
        service = KnowledgeService(session, embedding_provider=FakeEmbeddingProvider())
        outcome = await service.ingest(
            filename="../../etc/passwd\x00.txt",
            content_type="text/plain",
            raw_bytes=b"harmless content",
            title=None,
            user_id=TEST_USER_A.id,
            actor="tester",
        )
        assert "/" not in outcome.document.source_name
        assert "\\" not in outcome.document.source_name
        assert "\x00" not in outcome.document.source_name
        assert ".." not in outcome.document.source_name


async def test_embedding_failure_leaves_document_failed_with_zero_chunks(db_sessionmaker):
    async with db_sessionmaker() as session:
        service = KnowledgeService(session, embedding_provider=FakeEmbeddingProvider(fail=True))
        outcome = await service.ingest(
            filename="notes.txt",
            content_type="text/plain",
            raw_bytes=b"This will fail to embed.",
            title=None,
            user_id=TEST_USER_A.id,
            actor="tester",
        )
        assert outcome.document.processing_status == "failed"
        assert outcome.document.chunk_count == 0
        assert outcome.document.error_message


async def test_get_document_visible_to_owner_not_to_other_user(db_sessionmaker):
    async with db_sessionmaker() as session:
        service = KnowledgeService(session, embedding_provider=FakeEmbeddingProvider())
        outcome = await service.ingest(
            filename="private.txt",
            content_type="text/plain",
            raw_bytes=b"A's private content.",
            title=None,
            user_id=TEST_USER_A.id,
            actor="tester",
        )
        document = await service.get_document(outcome.document.id, user_id=TEST_USER_A.id)
        assert document.id == outcome.document.id

        with pytest.raises(NotFoundError):
            await service.get_document(outcome.document.id, user_id=TEST_USER_B.id)


async def test_delete_only_by_owner(db_sessionmaker):
    async with db_sessionmaker() as session:
        service = KnowledgeService(session, embedding_provider=FakeEmbeddingProvider())
        outcome = await service.ingest(
            filename="to-delete.txt",
            content_type="text/plain",
            raw_bytes=b"Delete me.",
            title=None,
            user_id=TEST_USER_A.id,
            actor="tester",
        )
        with pytest.raises(NotFoundError):
            await service.delete_document(outcome.document.id, user_id=TEST_USER_B.id, actor="b")

        await service.delete_document(outcome.document.id, user_id=TEST_USER_A.id, actor="a")
        with pytest.raises(NotFoundError):
            await service.get_document(outcome.document.id, user_id=TEST_USER_A.id)


async def test_reprocess_re_chunks_and_re_embeds_from_stored_content(db_sessionmaker):
    async with db_sessionmaker() as session:
        service = KnowledgeService(session, embedding_provider=FakeEmbeddingProvider())
        outcome = await service.ingest(
            filename="notes.txt",
            content_type="text/plain",
            raw_bytes=b"Content to be reprocessed later.",
            title=None,
            user_id=TEST_USER_A.id,
            actor="tester",
        )
        reprocessed = await service.reprocess(
            outcome.document.id, user_id=TEST_USER_A.id, actor="tester"
        )
        assert reprocessed.processing_status == "ready"
        assert reprocessed.chunk_count >= 1


async def test_reprocess_requires_ownership(db_sessionmaker):
    async with db_sessionmaker() as session:
        service = KnowledgeService(session, embedding_provider=FakeEmbeddingProvider())
        outcome = await service.ingest(
            filename="notes.txt",
            content_type="text/plain",
            raw_bytes=b"Owned by A only.",
            title=None,
            user_id=TEST_USER_A.id,
            actor="tester",
        )
        with pytest.raises(NotFoundError):
            await service.reprocess(outcome.document.id, user_id=TEST_USER_B.id, actor="b")


async def test_reprocess_unknown_document_raises_not_found(db_sessionmaker):
    async with db_sessionmaker() as session:
        service = KnowledgeService(session, embedding_provider=FakeEmbeddingProvider())
        with pytest.raises(NotFoundError):
            await service.reprocess(uuid.uuid4(), user_id=TEST_USER_A.id, actor="tester")


async def test_list_documents_paginates_and_scopes_to_caller(db_sessionmaker):
    async with db_sessionmaker() as session:
        service = KnowledgeService(session, embedding_provider=FakeEmbeddingProvider())
        for i in range(3):
            await service.ingest(
                filename=f"doc-{i}.txt",
                content_type="text/plain",
                raw_bytes=f"Content number {i}.".encode(),
                title=None,
                user_id=TEST_USER_A.id,
                actor="tester",
            )
        items, total = await service.list_documents(user_id=TEST_USER_A.id, page=1, page_size=2)
        assert total == 3
        assert len(items) == 2

        other_items, other_total = await service.list_documents(
            user_id=TEST_USER_B.id, page=1, page_size=10
        )
        assert other_total == 0
        assert other_items == []
