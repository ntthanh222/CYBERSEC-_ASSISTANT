"""Attack graph persistence."""

import uuid
from typing import Any, Optional, Sequence

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database.models.attack_graph import AttackGraphEdge, AttackGraphNode


class AttackGraphRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_node(self, *, user_id: uuid.UUID, **values: Any) -> AttackGraphNode:
        node = AttackGraphNode(user_id=user_id, **values)
        self._session.add(node)
        await self._session.flush()
        return node

    async def get_node(
        self, node_id: uuid.UUID, *, user_id: uuid.UUID
    ) -> Optional[AttackGraphNode]:
        return await self._session.scalar(
            sa.select(AttackGraphNode).where(
                AttackGraphNode.id == node_id,
                AttackGraphNode.user_id == user_id,
            )
        )

    async def list_nodes(self, *, user_id: uuid.UUID) -> Sequence[AttackGraphNode]:
        rows = await self._session.scalars(
            sa.select(AttackGraphNode)
            .where(AttackGraphNode.user_id == user_id)
            .order_by(AttackGraphNode.created_at, AttackGraphNode.id)
        )
        return list(rows)

    async def create_edge(self, *, user_id: uuid.UUID, **values: Any) -> AttackGraphEdge:
        edge = AttackGraphEdge(user_id=user_id, **values)
        self._session.add(edge)
        await self._session.flush()
        return edge

    async def list_edges(self, *, user_id: uuid.UUID) -> Sequence[AttackGraphEdge]:
        rows = await self._session.scalars(
            sa.select(AttackGraphEdge)
            .where(AttackGraphEdge.user_id == user_id)
            .order_by(AttackGraphEdge.created_at, AttackGraphEdge.id)
        )
        return list(rows)
