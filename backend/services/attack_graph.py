"""Attack graph service."""

import uuid
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.audit import log_audit_event
from backend.core.exceptions import NotFoundError
from backend.repositories.alerts import AlertRepository
from backend.repositories.assets import AssetRepository
from backend.repositories.attack_graph import AttackGraphRepository
from backend.repositories.incidents import IncidentRepository
from backend.repositories.mitre import MitreRepository
from backend.repositories.vulnerabilities import VulnerabilityRepository


class AttackGraphService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = AttackGraphRepository(session)

    async def get_graph(self, *, user_id: uuid.UUID):
        return await self._repo.list_nodes(user_id=user_id), await self._repo.list_edges(
            user_id=user_id
        )

    async def create_node(self, *, user_id: uuid.UUID, actor: Optional[str], **values):
        node = await self._repo.create_node(user_id=user_id, **values)
        await self._session.commit()
        log_audit_event(
            event_type="attack_graph",
            action="attack_graph_node_created",
            resource=f"attack_graph_node:{node.id}",
            result="success",
            actor=actor,
            metadata={"node_type": node.node_type, "severity": node.severity},
        )
        return node

    async def create_edge(self, *, user_id: uuid.UUID, actor: Optional[str], **values):
        source = await self._repo.get_node(values["source_node_id"], user_id=user_id)
        target = await self._repo.get_node(values["target_node_id"], user_id=user_id)
        if source is None or target is None:
            raise NotFoundError("Không tìm thấy nút trong sơ đồ tấn công.")
        edge = await self._repo.create_edge(user_id=user_id, **values)
        await self._session.commit()
        log_audit_event(
            event_type="attack_graph",
            action="attack_graph_edge_created",
            resource=f"attack_graph_edge:{edge.id}",
            result="success",
            actor=actor,
            metadata={"status": edge.status},
        )
        return edge

    async def generate_from_incident(
        self, incident_id: uuid.UUID, *, user_id: uuid.UUID, actor: Optional[str]
    ):
        """Derive a real attack-path graph from an incident's actual linked
        chain (source alert -> vulnerability -> asset -> MITRE techniques),
        instead of requiring nodes/edges to be manually authored one at a
        time. Every node/edge this creates traces back to a real row the
        caller owns - nothing here is invented."""
        incident = await IncidentRepository(self._session).get(incident_id, user_id=user_id)
        if incident is None:
            raise NotFoundError("Không tìm thấy sự cố.")

        alert = None
        if incident.source_alert_id is not None:
            alert = await AlertRepository(self._session).get(
                incident.source_alert_id, user_id=user_id
            )

        vulnerability = None
        if alert is not None and alert.vulnerability_id is not None:
            vulnerability = await VulnerabilityRepository(self._session).get(
                alert.vulnerability_id, user_id=user_id
            )

        asset = None
        asset_id = (alert.asset_id if alert else None) or (
            vulnerability.asset_id if vulnerability else None
        )
        if asset_id is not None:
            asset = await AssetRepository(self._session).get(asset_id, user_id=user_id)

        techniques, _ = await MitreRepository(self._session).list(
            user_id=user_id, page=1, page_size=50, incident_id=incident_id
        )

        step_x = 130

        attacker_node = await self._repo.create_node(
            user_id=user_id,
            node_type="attacker",
            label="External Attacker",
            status="secure",
            severity=incident.severity,
            description=f"Entry point inferred for incident: {incident.title}",
            position_x=100,
            position_y=140,
        )
        nodes = [attacker_node]
        edge_source = attacker_node
        column = 1

        if asset is not None:
            asset_node = await self._repo.create_node(
                user_id=user_id,
                node_type="asset",
                label=asset.name,
                ip_address=asset.ip_address,
                status="vulnerable" if vulnerability is not None else "compromised",
                severity=vulnerability.severity if vulnerability is not None else incident.severity,
                description=f"{asset.type} - {asset.hostname}",
                cves=[vulnerability.cve_id] if vulnerability is not None else [],
                position_x=100 + column * step_x,
                position_y=140,
            )
            column += 1
            nodes.append(asset_node)
            await self._repo.create_edge(
                user_id=user_id,
                source_node_id=edge_source.id,
                target_node_id=asset_node.id,
                label=vulnerability.cve_id if vulnerability is not None else "exploited",
                status="active",
            )
            edge_source = asset_node

        incident_node = await self._repo.create_node(
            user_id=user_id,
            node_type="target",
            label=incident.title,
            status="compromised",
            severity=incident.severity,
            description=incident.description[:4000],
            cves=[vulnerability.cve_id] if vulnerability is not None else [],
            position_x=100 + column * step_x,
            position_y=140,
        )
        column += 1
        nodes.append(incident_node)
        await self._repo.create_edge(
            user_id=user_id,
            source_node_id=edge_source.id,
            target_node_id=incident_node.id,
            label="escalated to incident",
            status="active",
        )

        for offset, technique in enumerate(techniques):
            technique_node = await self._repo.create_node(
                user_id=user_id,
                node_type="gateway",
                label=f"{technique.technique_id}: {technique.name}",
                status="vulnerable",
                severity=incident.severity,
                description=technique.description[:4000],
                position_x=100 + column * step_x,
                position_y=140 + (offset % 2) * 160,
            )
            nodes.append(technique_node)
            await self._repo.create_edge(
                user_id=user_id,
                source_node_id=incident_node.id,
                target_node_id=technique_node.id,
                label=technique.tactic,
                status="active",
            )

        await self._session.commit()
        log_audit_event(
            event_type="attack_graph",
            action="attack_graph_generated_from_incident",
            resource=f"incident:{incident.id}",
            result="success",
            actor=actor,
            metadata={"node_count": len(nodes), "technique_count": len(techniques)},
        )
        return await self.get_graph(user_id=user_id)
