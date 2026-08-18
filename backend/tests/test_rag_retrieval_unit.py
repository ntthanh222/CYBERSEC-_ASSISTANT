"""Retriever selection and dedup/budget behaviour that doesn't need Postgres."""
import uuid

from backend.providers.rag.base import NullRagRetriever
from backend.services.rag_retrieval import get_rag_retriever_for_session, PgVectorRagRetriever


async def test_sqlite_session_gets_the_null_retriever_not_pgvector(db_sessionmaker):
    async with db_sessionmaker() as session:
        retriever = get_rag_retriever_for_session(session)
        assert isinstance(retriever, NullRagRetriever)
        assert retriever.is_ready is False
        assert await retriever.retrieve("anything", user_id=uuid.uuid4()) == ()


def test_pgvector_retriever_reports_ready():
    # Construction alone must not touch the network or a real DB - only
    # __init__ side effects (settings reads) are exercised here.
    class _FakeBind:
        class dialect:
            name = "postgresql"

    class _FakeSession:
        def get_bind(self):
            return _FakeBind()

    retriever = get_rag_retriever_for_session(_FakeSession())
    assert isinstance(retriever, PgVectorRagRetriever)
    assert retriever.is_ready is True
