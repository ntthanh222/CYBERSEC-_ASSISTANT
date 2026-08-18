"""Demo Mode knowledge-pack bootstrap: idempotent, opt-in, real ingestion pipeline."""
import uuid

import pytest

from backend.config.settings import get_settings
from backend.repositories.knowledge import KnowledgeRepository
from backend.services.demo_knowledge import seed_demo_knowledge

from ._knowledge_fakes import FakeEmbeddingProvider


@pytest.fixture(autouse=True)
def _fake_embeddings(monkeypatch):
    monkeypatch.setattr(
        "backend.services.knowledge.get_embedding_provider", lambda: FakeEmbeddingProvider()
    )


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _demo_settings(monkeypatch, **env_overrides):
    env = {"APP_ENV": "local", "DEMO_SEED_ENABLED": "true"}
    env.update(env_overrides)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()
    return get_settings()


async def test_seed_ingests_every_fixture_as_a_global_document(db_sessionmaker, monkeypatch):
    async with db_sessionmaker() as session:
        await seed_demo_knowledge(session, settings=_demo_settings(monkeypatch))

    async with db_sessionmaker() as session:
        repo = KnowledgeRepository(session)
        documents, total = await repo.list_documents(user_id=uuid.uuid4(), page=1, page_size=50)
        # Every doc is global (owner_user_id=None) - visible to any user_id.
        assert total >= 7
        assert all(doc.owner_user_id is None for doc in documents)
        assert all(doc.processing_status == "ready" for doc in documents)


async def test_seed_is_idempotent_on_second_run(db_sessionmaker, monkeypatch):
    settings = _demo_settings(monkeypatch)
    async with db_sessionmaker() as session:
        await seed_demo_knowledge(session, settings=settings)
    async with db_sessionmaker() as session:
        await seed_demo_knowledge(session, settings=settings)

    async with db_sessionmaker() as session:
        repo = KnowledgeRepository(session)
        _, total_first = await repo.list_documents(user_id=uuid.uuid4(), page=1, page_size=1)
        await seed_demo_knowledge(session, settings=settings)
        _, total_second = await repo.list_documents(user_id=uuid.uuid4(), page=1, page_size=1)
        assert total_first == total_second


async def test_seed_is_a_no_op_outside_local(db_sessionmaker, monkeypatch):
    settings = _demo_settings(monkeypatch, APP_ENV="test")
    async with db_sessionmaker() as session:
        await seed_demo_knowledge(session, settings=settings)

    async with db_sessionmaker() as session:
        repo = KnowledgeRepository(session)
        _, total = await repo.list_documents(user_id=uuid.uuid4(), page=1, page_size=1)
        assert total == 0


async def test_seed_is_a_no_op_when_disabled(db_sessionmaker, monkeypatch):
    settings = _demo_settings(monkeypatch, DEMO_SEED_ENABLED="false")
    async with db_sessionmaker() as session:
        await seed_demo_knowledge(session, settings=settings)

    async with db_sessionmaker() as session:
        repo = KnowledgeRepository(session)
        _, total = await repo.list_documents(user_id=uuid.uuid4(), page=1, page_size=1)
        assert total == 0
