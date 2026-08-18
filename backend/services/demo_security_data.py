"""Demo Mode security-ops chain: one real, linked asset -> vulnerability ->
alert -> incident -> MITRE technique -> attack graph, seeded for the
classroom demo.

Runs once at startup (see ``backend/main.py``'s ``lifespan``), only when
``APP_ENV=local`` and ``DEMO_SEED_ENABLED=true`` - same gate as
``seed_demo_accounts``/``seed_demo_knowledge``, and deliberately depends on
``seed_demo_accounts`` having already run so ``demo_superadmin`` exists.

Seeded under ``demo_superadmin``'s own ownership: every one of these tables
is strictly owner-scoped RLS (``auth.uid() = user_id``, FORCE ROW LEVEL
SECURITY - see migration 0007 and friends), so there is no cross-account
sharing mechanism today. Rather than widen that (a materially bigger,
riskier change - see migration 0019's docstring), the demo walks this chain
while signed in as ``demo_superadmin``, which already has full read/write
access to every entity in it. (Previously seeded under the now-retired
``demo_admin`` - a fresh chain is created under ``demo_superadmin`` on first
startup after the consolidation; the old rows under ``demo_admin`` are left
in place, orphaned but harmless, since that account can no longer sign in to
see them - see ``demo_accounts.py``'s ``_retire_demo_admin``.)

Idempotent: keyed on the seeded asset's fixed name, so a restart never
duplicates the chain.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config.settings import Settings
from backend.database.models.alert import AlertRecord
from backend.database.models.asset import Asset
from backend.database.models.attack_graph import AttackGraphEdge, AttackGraphNode
from backend.database.models.incident import IncidentRecord, IncidentTask, IncidentTimelineEvent
from backend.database.models.mitre import MitreTechniqueCoverage
from backend.database.models.vulnerability import VulnerabilityPatchTask, VulnerabilityRecord
from backend.repositories.alerts import AlertRepository
from backend.repositories.assets import AssetRepository
from backend.repositories.incidents import IncidentRepository
from backend.repositories.mitre import MitreRepository
from backend.repositories.rbac import RbacRepository
from backend.repositories.vulnerabilities import VulnerabilityRepository
from backend.services.attack_graph import AttackGraphService

logger = logging.getLogger("backend.demo_security_data")

_SEED_ASSET_NAME = "corp-web-01 (Demo Seed)"
_SEED_CVE_ID = "CVE-2024-3400"


async def seed_demo_security_chain(session: AsyncSession, *, settings: Settings) -> None:
    """Idempotently ensure the demo asset->incident->attack-graph chain
    exists under ``demo_superadmin``. Never raises - a convenience seed, not
    a hard startup dependency, same posture as the other demo seeds."""
    if not settings.is_local or not settings.demo_seed_enabled:
        return

    try:
        rbac = RbacRepository(session)
        credential = await rbac.get_credential_by_username("demo_superadmin")
        if credential is None:
            logger.info("demo_security_chain_skipped_no_demo_superadmin")
            return
        user_id = credential.user_id

        assets = AssetRepository(session)
        found = await session.scalar(
            sa.select(Asset).where(Asset.user_id == user_id, Asset.name == _SEED_ASSET_NAME)
        )
        if found is not None:
            logger.info("demo_security_chain_already_seeded")
            return

        asset = await assets.create(
            user_id=user_id,
            name=_SEED_ASSET_NAME,
            type="server",
            hostname="corp-web-01.demo.internal",
            ip_address="10.20.30.41",
            operating_system="Ubuntu 22.04 LTS",
            owner="Platform Engineering",
            department="Engineering",
            business_criticality="high",
            internet_exposed=True,
            description="Public-facing web application server used in the classroom demo chain.",
            linked_cves=[_SEED_CVE_ID],
            patch_status="not_started",
            exploit_evidence="public_poc",
        )

        vulnerabilities = VulnerabilityRepository(session)
        now = datetime.now(timezone.utc)
        vulnerability = await vulnerabilities.create(
            user_id=user_id,
            asset_id=asset.id,
            cve_id=_SEED_CVE_ID,
            title="PAN-OS GlobalProtect command injection",
            description=(
                "A command injection vulnerability in the GlobalProtect feature of "
                "PAN-OS allows an unauthenticated attacker to execute arbitrary code "
                "with root privileges on the firewall."
            ),
            cvss=10.0,
            severity="critical",
            published_date=now,
            updated_date=now,
            references=[f"https://nvd.nist.gov/vuln/detail/{_SEED_CVE_ID}"],
            affected_products=["PAN-OS 10.2", "PAN-OS 11.0", "PAN-OS 11.1"],
            remediation="Apply the vendor hotfix and rotate all device credentials.",
            watchlist=True,
        )

        alerts = AlertRepository(session)
        alert = await alerts.create(
            user_id=user_id,
            title="Suspicious command execution on corp-web-01",
            description=(
                "EDR flagged an unexpected child process spawned from the "
                "GlobalProtect service on corp-web-01, consistent with "
                f"{_SEED_CVE_ID} exploitation."
            ),
            severity="critical",
            source="EDR",
            status="investigating",
            asset_id=asset.id,
            vulnerability_id=vulnerability.id,
            asset_name=asset.name,
            ioc_value="10.20.30.41",
            evidence="process_tree: globalprotect -> /bin/sh -> curl 45.148.10.0/24",
        )

        incidents = IncidentRepository(session)
        incident = await incidents.create(
            user_id=user_id,
            title=f"Active exploitation of {_SEED_CVE_ID} on corp-web-01",
            description=(
                "Confirmed exploitation of the PAN-OS GlobalProtect command "
                "injection vulnerability on the internet-facing web server. "
                "Escalated from the EDR alert for immediate containment."
            ),
            severity="critical",
            status="in_progress",
            assignee="demo_superadmin",
            source_alert_id=alert.id,
            asset_name=asset.name,
            cve_id=vulnerability.cve_id,
        )

        mitre = MitreRepository(session)
        await mitre.create(
            user_id=user_id,
            incident_id=incident.id,
            technique_id="T1190",
            tactic="Initial Access",
            name="Exploit Public-Facing Application",
            description=(
                f"Adversaries exploited {_SEED_CVE_ID} on the internet-facing "
                "GlobalProtect portal."
            ),
            detection="EDR process-tree anomaly detection on the firewall/VPN host.",
            mitigation="Patch PAN-OS, restrict management-plane exposure, rotate credentials.",
            coverage_status="gap",
            data_sources=["EDR", "Firewall logs"],
        )
        await mitre.create(
            user_id=user_id,
            incident_id=incident.id,
            technique_id="T1059",
            tactic="Execution",
            name="Command and Scripting Interpreter",
            description=(
                "Post-exploitation shell command execution observed via the " "injected process."
            ),
            detection="Process creation events (sh/bash spawned from globalprotect).",
            mitigation="Application allow-listing; restrict outbound egress from the host.",
            coverage_status="partial",
            data_sources=["EDR"],
        )
        await session.commit()

        await AttackGraphService(session).generate_from_incident(
            incident.id, user_id=user_id, actor="demo_security_data_seed"
        )

        logger.info(
            "demo_security_chain_seeded",
            extra={
                "fields": {
                    "asset_id": str(asset.id),
                    "vulnerability_id": str(vulnerability.id),
                    "alert_id": str(alert.id),
                    "incident_id": str(incident.id),
                }
            },
        )
    except Exception:  # noqa: BLE001 - seeding must never crash startup
        await session.rollback()
        logger.exception("demo_security_chain_seed_failed")


async def reset_demo_security_chain(session: AsyncSession, *, user_id) -> dict[str, int]:
    """Remove only the fixed classroom demo chain owned by ``user_id``.

    This intentionally keys off the seed asset's exact marker plus linked
    records owned by the same user. It does not delete arbitrary records with
    the same CVE/title elsewhere, which keeps the reset suitable for repeated
    classroom rehearsals without threatening operational data.
    """
    asset = await session.scalar(
        sa.select(Asset).where(Asset.user_id == user_id, Asset.name == _SEED_ASSET_NAME)
    )
    if asset is None:
        return {
            "assets": 0,
            "vulnerabilities": 0,
            "alerts": 0,
            "incidents": 0,
            "mitre": 0,
            "attack_graph_nodes": 0,
            "attack_graph_edges": 0,
        }

    vulnerabilities = list(
        (
            await session.scalars(
                sa.select(VulnerabilityRecord).where(
                    VulnerabilityRecord.user_id == user_id,
                    VulnerabilityRecord.asset_id == asset.id,
                )
            )
        ).all()
    )
    vulnerability_ids = [item.id for item in vulnerabilities]

    alerts = list(
        (
            await session.scalars(
                sa.select(AlertRecord).where(
                    AlertRecord.user_id == user_id,
                    AlertRecord.asset_id == asset.id,
                )
            )
        ).all()
    )
    alert_ids = [item.id for item in alerts]

    incidents = list(
        (
            await session.scalars(
                sa.select(IncidentRecord).where(
                    IncidentRecord.user_id == user_id,
                    IncidentRecord.source_alert_id.in_(alert_ids) if alert_ids else sa.false(),
                )
            )
        ).all()
    )
    incident_ids = [item.id for item in incidents]

    incident_titles = {incident.title for incident in incidents}
    user_graph_nodes = list(
        (
            await session.scalars(
                sa.select(AttackGraphNode).where(AttackGraphNode.user_id == user_id)
            )
        ).all()
    )
    graph_node_ids = [
        item.id
        for item in user_graph_nodes
        if (
            item.label == _SEED_ASSET_NAME
            and _SEED_CVE_ID in (item.cves or [])
        )
        or (
            item.label in incident_titles
            and _SEED_CVE_ID in (item.cves or [])
        )
        or (
            item.label == "T1190: Exploit Public-Facing Application"
            and _SEED_CVE_ID in item.description
        )
        or (
            item.label == "T1059: Command and Scripting Interpreter"
            and "injected process" in item.description
        )
    ]

    if graph_node_ids:
        connected_edges = list(
            (
                await session.scalars(
                    sa.select(AttackGraphEdge).where(
                        AttackGraphEdge.user_id == user_id,
                        sa.or_(
                            AttackGraphEdge.source_node_id.in_(graph_node_ids),
                            AttackGraphEdge.target_node_id.in_(graph_node_ids),
                        ),
                    )
                )
            ).all()
        )
        for edge in connected_edges:
            if edge.source_node_id not in graph_node_ids:
                graph_node_ids.append(edge.source_node_id)
            if edge.target_node_id not in graph_node_ids:
                graph_node_ids.append(edge.target_node_id)

    deleted_edges = 0
    if graph_node_ids:
        result = await session.execute(
            sa.delete(AttackGraphEdge).where(
                AttackGraphEdge.user_id == user_id,
                sa.or_(
                    AttackGraphEdge.source_node_id.in_(graph_node_ids),
                    AttackGraphEdge.target_node_id.in_(graph_node_ids),
                ),
            )
        )
        deleted_edges = result.rowcount or 0

    if graph_node_ids:
        await session.execute(
            sa.delete(AttackGraphNode).where(
                AttackGraphNode.user_id == user_id,
                AttackGraphNode.id.in_(graph_node_ids),
            )
        )

    deleted_mitre = 0
    if incident_ids:
        await session.execute(
            sa.delete(IncidentTimelineEvent).where(
                IncidentTimelineEvent.user_id == user_id,
                IncidentTimelineEvent.incident_id.in_(incident_ids),
            )
        )
        await session.execute(
            sa.delete(IncidentTask).where(
                IncidentTask.user_id == user_id,
                IncidentTask.incident_id.in_(incident_ids),
            )
        )
        result = await session.execute(
            sa.delete(MitreTechniqueCoverage).where(
                MitreTechniqueCoverage.user_id == user_id,
                MitreTechniqueCoverage.incident_id.in_(incident_ids),
            )
        )
        deleted_mitre = result.rowcount or 0
        await session.execute(
            sa.delete(IncidentRecord).where(
                IncidentRecord.user_id == user_id,
                IncidentRecord.id.in_(incident_ids),
            )
        )

    if alert_ids:
        await session.execute(
            sa.delete(AlertRecord).where(
                AlertRecord.user_id == user_id,
                AlertRecord.id.in_(alert_ids),
            )
        )

    if vulnerability_ids:
        await session.execute(
            sa.delete(VulnerabilityPatchTask).where(
                VulnerabilityPatchTask.user_id == user_id,
                VulnerabilityPatchTask.vulnerability_id.in_(vulnerability_ids),
            )
        )
        await session.execute(
            sa.delete(VulnerabilityRecord).where(
                VulnerabilityRecord.user_id == user_id,
                VulnerabilityRecord.id.in_(vulnerability_ids),
            )
        )

    await session.execute(
        sa.delete(Asset).where(Asset.user_id == user_id, Asset.id == asset.id)
    )
    await session.commit()

    return {
        "assets": 1,
        "vulnerabilities": len(vulnerability_ids),
        "alerts": len(alert_ids),
        "incidents": len(incident_ids),
        "mitre": deleted_mitre,
        "attack_graph_nodes": len(graph_node_ids),
        "attack_graph_edges": deleted_edges,
    }
