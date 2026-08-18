"""Demo Mode endpoints for the classroom demo chain."""

from typing import Any

import sqlalchemy as sa
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config.settings import get_settings
from backend.core.actor import get_current_actor
from backend.core.auth import AuthenticatedUser, get_current_user
from backend.database.models.alert import AlertRecord
from backend.database.models.asset import Asset
from backend.database.models.incident import IncidentRecord
from backend.database.models.mitre import MitreTechniqueCoverage
from backend.database.models.vulnerability import VulnerabilityRecord
from backend.database.session import get_db
from backend.schemas.health import ErrorResponse
from backend.services.demo_security_data import reset_demo_security_chain, seed_demo_security_chain

router = APIRouter(prefix="/api/demo", tags=["demo"], dependencies=[Depends(get_current_user)])
_UNAUTHORIZED = {401: {"model": ErrorResponse, "description": "Missing or invalid bearer token."}}


async def _chain(session: AsyncSession, user_id) -> dict[str, Any]:
    asset = await session.scalar(
        sa.select(Asset).where(Asset.user_id == user_id, Asset.name == "corp-web-01 (Demo Seed)")
    )
    vulnerability = None
    alert = None
    incident = None
    techniques: list[MitreTechniqueCoverage] = []
    if asset is not None:
        vulnerability = await session.scalar(
            sa.select(VulnerabilityRecord).where(
                VulnerabilityRecord.user_id == user_id,
                VulnerabilityRecord.asset_id == asset.id,
            )
        )
        alert = await session.scalar(
            sa.select(AlertRecord).where(
                AlertRecord.user_id == user_id,
                AlertRecord.asset_id == asset.id,
            )
        )
    if alert is not None:
        incident = await session.scalar(
            sa.select(IncidentRecord).where(
                IncidentRecord.user_id == user_id,
                IncidentRecord.source_alert_id == alert.id,
            )
        )
    if incident is not None:
        techniques = list(
            (
                await session.scalars(
                    sa.select(MitreTechniqueCoverage).where(
                        MitreTechniqueCoverage.user_id == user_id,
                        MitreTechniqueCoverage.incident_id == incident.id,
                    )
                )
            ).all()
        )
    return {
        "active": asset is not None,
        "isolation": "demo_seeded_under_demo_superadmin_owner_scope",
        "asset": (
            {"id": str(asset.id), "name": asset.name, "hostname": asset.hostname}
            if asset
            else None
        ),
        "vulnerability": (
            {
                "id": str(vulnerability.id),
                "cve_id": vulnerability.cve_id,
                "title": vulnerability.title,
            }
            if vulnerability
            else None
        ),
        "alert": (
            {"id": str(alert.id), "title": alert.title, "severity": alert.severity}
            if alert
            else None
        ),
        "incident": (
            {"id": str(incident.id), "title": incident.title, "severity": incident.severity}
            if incident
            else None
        ),
        "mitre": [
            {"id": str(item.id), "technique_id": item.technique_id, "name": item.name}
            for item in techniques
        ],
        "routes": {
            "asset": f"/assets/{asset.id}" if asset else "/assets",
            "vulnerabilities": "/vulnerabilities",
            "alerts": f"/alerts/{alert.id}" if alert else "/alerts",
            "incident": f"/incidents/{incident.id}" if incident else "/incidents",
            "attack_graph": "/attack-graph",
            "report_builder": "/reports/builder",
        },
    }


@router.get("/status", responses={**_UNAUTHORIZED})
async def demo_status(
    session: AsyncSession = Depends(get_db),
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    return await _chain(session, user.id)


@router.post("/start", responses={**_UNAUTHORIZED})
async def start_demo(
    session: AsyncSession = Depends(get_db),
    user: AuthenticatedUser = Depends(get_current_user),
    actor: str = Depends(get_current_actor),
) -> dict[str, Any]:
    await seed_demo_security_chain(session, settings=get_settings())
    return {**(await _chain(session, user.id)), "started_by": actor}


@router.post("/reset", responses={**_UNAUTHORIZED})
async def reset_demo(
    session: AsyncSession = Depends(get_db),
    user: AuthenticatedUser = Depends(get_current_user),
    actor: str = Depends(get_current_actor),
) -> dict[str, Any]:
    deleted = await reset_demo_security_chain(session, user_id=user.id)
    return {**(await _chain(session, user.id)), "reset_by": actor, "deleted": deleted}
