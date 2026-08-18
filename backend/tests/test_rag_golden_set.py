"""RAG golden set retrieval accuracy - live Postgres only.

Grades the *retrieval* layer (does the right document get cited) for every
golden-set item that has an ``expect_source_contains`` field, against the
real demo knowledge pack, real local embeddings, and real pgvector/full-
text/exact-match hybrid search - the same code path production traffic
uses. Skipped unless ``LIVE_POSTGRES_DSN`` is set, same convention as
``test_live_postgres_rag.py``.

Items without ``expect_source_contains`` (no_answer, prompt_injection,
tool_calling, memory) test *answer* behavior, not retrieval, and need a
real Gemini call to grade end-to-end - not exercised here. See
backend/fixtures/demo_knowledge/golden_set.json's docstring field for which
items are ``requires_live_gemini``.
"""
import json
import os
import uuid
from pathlib import Path

import pytest

LIVE_DSN = os.environ.get("LIVE_POSTGRES_DSN")

pytestmark = pytest.mark.skipif(
    not LIVE_DSN,
    reason="LIVE_POSTGRES_DSN not set - needs a real Postgres with the demo knowledge pack seeded",
)

GOLDEN_SET_PATH = (
    Path(__file__).resolve().parents[1] / "fixtures" / "demo_knowledge" / "golden_set.json"
)


def _load_golden_set() -> list[dict]:
    data = json.loads(GOLDEN_SET_PATH.read_text(encoding="utf-8"))
    return [item for item in data["items"] if "expect_source_contains" in item]


@pytest.fixture()
async def _live_session():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    engine = create_async_engine(LIVE_DSN)
    sessionmaker = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with sessionmaker() as session:
        yield session
    await engine.dispose()


@pytest.mark.parametrize("item", _load_golden_set(), ids=lambda i: f"q{i['id']}_{i['category']}")
async def test_golden_set_item_retrieves_the_expected_source(_live_session, item):
    from backend.services.rag_retrieval import PgVectorRagRetriever

    retriever = PgVectorRagRetriever(_live_session)
    # A random user_id: every demo document is global (owner_user_id=None),
    # so any caller must see it - this also proves the visibility rule.
    results = await retriever.retrieve(item["question"], user_id=uuid.uuid4(), limit=6)

    assert results, f"No chunks retrieved for: {item['question']!r}"
    sources = [r.source for r in results]
    assert any(item["expect_source_contains"] in s for s in sources), (
        f"Expected a citation from a source containing "
        f"{item['expect_source_contains']!r}, got: {sources}"
    )
