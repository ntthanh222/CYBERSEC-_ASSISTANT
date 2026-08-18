"""Demo Mode security-chain seed/reset behavior."""

import uuid

import sqlalchemy as sa
import pytest

from backend.config.settings import get_settings
from backend.database.models.alert import AlertRecord
from backend.database.models.asset import Asset
from backend.database.models.attack_graph import AttackGraphNode
from backend.database.models.incident import IncidentRecord
from backend.database.models.mitre import MitreTechniqueCoverage
from backend.database.models.vulnerability import VulnerabilityRecord
from backend.repositories.assets import AssetRepository
from backend.repositories.rbac import RbacRepository
from backend.services.demo_accounts import seed_demo_accounts
from backend.services.demo_security_data import (
    reset_demo_security_chain,
    seed_demo_security_chain,
)


@pytest.fixture(autouse=True)
def _fake_auth_user_creation(monkeypatch):
    async def _fake_create_auth_user(session, *, email):
        return uuid.uuid4()

    monkeypatch.setattr("backend.services.demo_accounts.create_auth_user", _fake_create_auth_user)


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _demo_settings(monkeypatch):
    env = {
        "APP_ENV": "local",
        "DEMO_SEED_ENABLED": "true",
        "DEMO_USER_PASSWORD": "user-pass-123",
        "DEMO_ANALYST_PASSWORD": "analyst-pass-123",
        "DEMO_SUPERADMIN_PASSWORD": "superadmin-pass-123",
    }
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()
    return get_settings()


async def _seed_accounts_and_chain(db_sessionmaker, monkeypatch):
    settings = _demo_settings(monkeypatch)
    async with db_sessionmaker() as session:
        await seed_demo_accounts(session, settings=settings)
        await seed_demo_security_chain(session, settings=settings)

    async with db_sessionmaker() as session:
        credential = await RbacRepository(session).get_credential_by_username("demo_superadmin")
        assert credential is not None
        return credential.user_id


async def test_reset_demo_security_chain_removes_only_seeded_demo_rows(
    db_sessionmaker, monkeypatch
):
    user_id = await _seed_accounts_and_chain(db_sessionmaker, monkeypatch)

    async with db_sessionmaker() as session:
        await AssetRepository(session).create(
            user_id=user_id,
            name="Operational Web Server",
            type="server",
            hostname="web01.internal",
            ip_address="10.20.30.99",
            operating_system="Ubuntu 22.04 LTS",
            owner="Operations",
            department="IT",
            business_criticality="high",
            internet_exposed=True,
            description="Non-demo asset that must survive Demo Mode reset.",
            linked_cves=["CVE-2024-3400"],
            patch_status="in_progress",
            exploit_evidence="none",
        )
        await session.commit()

    async with db_sessionmaker() as session:
        deleted = await reset_demo_security_chain(session, user_id=user_id)
        assert deleted["assets"] == 1
        assert deleted["vulnerabilities"] == 1
        assert deleted["alerts"] == 1
        assert deleted["incidents"] == 1
        assert deleted["mitre"] == 2
        assert deleted["attack_graph_nodes"] >= 3
        assert deleted["attack_graph_edges"] >= 2

    async with db_sessionmaker() as session:
        assert await session.scalar(
            sa.select(Asset).where(
                Asset.user_id == user_id,
                Asset.name == "corp-web-01 (Demo Seed)",
            )
        ) is None
        assert await session.scalar(
            sa.select(Asset).where(Asset.user_id == user_id, Asset.name == "Operational Web Server")
        ) is not None
        assert await session.scalar(
            sa.select(VulnerabilityRecord).where(VulnerabilityRecord.user_id == user_id)
        ) is None
        assert await session.scalar(
            sa.select(AlertRecord).where(AlertRecord.user_id == user_id)
        ) is None
        assert await session.scalar(
            sa.select(IncidentRecord).where(IncidentRecord.user_id == user_id)
        ) is None
        assert await session.scalar(
            sa.select(MitreTechniqueCoverage).where(MitreTechniqueCoverage.user_id == user_id)
        ) is None
        assert await session.scalar(
            sa.select(AttackGraphNode).where(AttackGraphNode.user_id == user_id)
        ) is None


async def test_reset_demo_security_chain_is_idempotent(db_sessionmaker, monkeypatch):
    user_id = await _seed_accounts_and_chain(db_sessionmaker, monkeypatch)

    async with db_sessionmaker() as session:
        first = await reset_demo_security_chain(session, user_id=user_id)
    async with db_sessionmaker() as session:
        second = await reset_demo_security_chain(session, user_id=user_id)

    assert first["assets"] == 1
    assert second == {
        "assets": 0,
        "vulnerabilities": 0,
        "alerts": 0,
        "incidents": 0,
        "mitre": 0,
        "attack_graph_nodes": 0,
        "attack_graph_edges": 0,
    }
