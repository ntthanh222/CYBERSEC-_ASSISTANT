"""Attack graph endpoints."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.actor import get_current_actor
from backend.core.auth import AuthenticatedUser, get_current_user
from backend.database.models.attack_graph import AttackGraphEdge, AttackGraphNode
from backend.database.session import get_rls_db
from backend.schemas.attack_graph import (
    AttackEdgeCreate,
    AttackEdgeItem,
    AttackGraph,
    AttackNodeCreate,
    AttackNodeItem,
)
from backend.schemas.health import ErrorResponse
from backend.services.attack_graph import AttackGraphService

router = APIRouter(
    prefix="/api/attack-graph", tags=["attack-graph"], dependencies=[Depends(get_current_user)]
)
_UNAUTHORIZED = {401: {"model": ErrorResponse, "description": "Missing or invalid bearer token."}}


def _node_dict(node: AttackGraphNode) -> dict[str, Any]:
    return {
        "id": node.id,
        "node_type": node.node_type,
        "label": node.label,
        "ip_address": node.ip_address,
        "status": node.status,
        "severity": node.severity,
        "description": node.description,
        "cves": node.cves,
        "position_x": node.position_x,
        "position_y": node.position_y,
        "created_at": node.created_at,
        "updated_at": node.updated_at,
    }


def _edge_dict(edge: AttackGraphEdge) -> dict[str, Any]:
    return {
        "id": edge.id,
        "source_node_id": edge.source_node_id,
        "target_node_id": edge.target_node_id,
        "label": edge.label,
        "status": edge.status,
        "created_at": edge.created_at,
        "updated_at": edge.updated_at,
    }


@router.get("", response_model=AttackGraph, responses={**_UNAUTHORIZED})
async def get_graph(
    session: AsyncSession = Depends(get_rls_db),
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    nodes, edges = await AttackGraphService(session).get_graph(user_id=user.id)
    return {
        "nodes": [_node_dict(node) for node in nodes],
        "edges": [_edge_dict(edge) for edge in edges],
    }


@router.post("/nodes", status_code=201, response_model=AttackNodeItem, responses={**_UNAUTHORIZED})
async def create_node(
    body: AttackNodeCreate,
    session: AsyncSession = Depends(get_rls_db),
    user: AuthenticatedUser = Depends(get_current_user),
    actor: str = Depends(get_current_actor),
) -> dict[str, Any]:
    node = await AttackGraphService(session).create_node(
        user_id=user.id, actor=actor, **body.model_dump()
    )
    return _node_dict(node)


@router.post(
    "/edges",
    status_code=201,
    response_model=AttackEdgeItem,
    responses={404: {"model": ErrorResponse}, **_UNAUTHORIZED},
)
async def create_edge(
    body: AttackEdgeCreate,
    session: AsyncSession = Depends(get_rls_db),
    user: AuthenticatedUser = Depends(get_current_user),
    actor: str = Depends(get_current_actor),
) -> dict[str, Any]:
    edge = await AttackGraphService(session).create_edge(
        user_id=user.id, actor=actor, **body.model_dump()
    )
    return _edge_dict(edge)


@router.post(
    "/generate-from-incident/{incident_id}",
    response_model=AttackGraph,
    responses={404: {"model": ErrorResponse}, **_UNAUTHORIZED},
)
async def generate_from_incident(
    incident_id: UUID,
    session: AsyncSession = Depends(get_rls_db),
    user: AuthenticatedUser = Depends(get_current_user),
    actor: str = Depends(get_current_actor),
) -> dict[str, Any]:
    nodes, edges = await AttackGraphService(session).generate_from_incident(
        incident_id, user_id=user.id, actor=actor
    )
    return {
        "nodes": [_node_dict(node) for node in nodes],
        "edges": [_edge_dict(edge) for edge in edges],
    }
