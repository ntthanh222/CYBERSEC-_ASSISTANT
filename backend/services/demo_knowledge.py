"""Demo Mode knowledge-pack bootstrap: consistent, fabricated demo documents.

Runs once at startup (see ``backend/main.py``'s ``lifespan``), only when
``APP_ENV=local`` and ``DEMO_SEED_ENABLED=true`` - the same gate as
``backend/services/demo_accounts.py``. Ingests every ``.md`` file under
``backend/fixtures/demo_knowledge/`` as a system/global document
(``owner_user_id=None``, visible to every caller) through the real
ingestion pipeline (extraction -> chunking -> embedding), so the resulting
chunks, citations and retrieval behave identically to a real upload -
nothing about the demo pack is faked at the retrieval layer, only its
*content* is fabricated (and disclosed as such in the documents themselves).

Idempotent via the same checksum mechanism the real upload endpoint uses:
re-running on every restart is safe and never duplicates a document.
"""
from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from backend.config.settings import Settings
from backend.services.knowledge import KnowledgeService

logger = logging.getLogger("backend.demo_knowledge")

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "demo_knowledge"


async def seed_demo_knowledge(session: AsyncSession, *, settings: Settings) -> None:
    """Idempotently ensure the demo knowledge pack is ingested as system
    documents. Never raises: a partial failure (e.g. one bad file) must not
    crash app startup - same posture as seed_demo_accounts."""
    if not settings.is_local or not settings.demo_seed_enabled:
        return
    if not FIXTURES_DIR.is_dir():
        return

    service = KnowledgeService(session)
    ingested: list[str] = []
    reused: list[str] = []

    for path in sorted(FIXTURES_DIR.glob("*.md")):
        try:
            raw_bytes = path.read_bytes()
            outcome = await service.ingest(
                filename=path.name,
                content_type="text/markdown",
                raw_bytes=raw_bytes,
                title=None,
                user_id=None,
                actor="system:demo-seed",
            )
            if outcome.reused:
                reused.append(path.name)
            else:
                ingested.append(path.name)
        except Exception as exc:  # noqa: BLE001 - seeding must never crash startup
            logger.warning(
                "demo_knowledge_seed_failed",
                extra={"fields": {"file": path.name, "error": type(exc).__name__}},
            )

    logger.info(
        "demo_knowledge_seed_complete",
        extra={"fields": {"ingested": ingested, "already_present": reused}},
    )
