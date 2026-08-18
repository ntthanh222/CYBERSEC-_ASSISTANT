"""Attack graph models."""

import uuid
from typing import List

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from backend.database.base import Base, JSONVariant, TimestampMixin, UuidPrimaryKeyMixin, UuidType

ATTACK_NODE_TYPES = ("attacker", "asset", "database", "gateway", "target")
ATTACK_NODE_STATUSES = ("compromised", "vulnerable", "secure")
ATTACK_EDGE_STATUSES = ("active", "potential", "blocked")


class AttackGraphNode(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "attack_graph_nodes"

    user_id: Mapped[uuid.UUID] = mapped_column(UuidType, nullable=False)
    node_type: Mapped[str] = mapped_column(sa.String(24), nullable=False)
    label: Mapped[str] = mapped_column(sa.String(240), nullable=False)
    ip_address: Mapped[str] = mapped_column(sa.String(80), nullable=False, default="")
    status: Mapped[str] = mapped_column(sa.String(24), nullable=False)
    severity: Mapped[str] = mapped_column(sa.String(16), nullable=False)
    description: Mapped[str] = mapped_column(sa.Text, nullable=False, default="")
    cves: Mapped[List[str]] = mapped_column(JSONVariant, nullable=False, default=list)
    position_x: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=100)
    position_y: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=100)

    __table_args__ = (
        sa.Index("ix_attack_graph_nodes_user_id", "user_id"),
        sa.CheckConstraint(
            "node_type IN ('attacker', 'asset', 'database', 'gateway', 'target')",
            name="ck_attack_graph_nodes_type",
        ),
        sa.CheckConstraint(
            "status IN ('compromised', 'vulnerable', 'secure')",
            name="ck_attack_graph_nodes_status",
        ),
        sa.CheckConstraint(
            "severity IN ('low', 'medium', 'high', 'critical')",
            name="ck_attack_graph_nodes_severity",
        ),
    )


class AttackGraphEdge(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "attack_graph_edges"

    user_id: Mapped[uuid.UUID] = mapped_column(UuidType, nullable=False)
    source_node_id: Mapped[uuid.UUID] = mapped_column(UuidType, nullable=False)
    target_node_id: Mapped[uuid.UUID] = mapped_column(UuidType, nullable=False)
    label: Mapped[str] = mapped_column(sa.String(240), nullable=False)
    status: Mapped[str] = mapped_column(sa.String(24), nullable=False)

    __table_args__ = (
        sa.Index("ix_attack_graph_edges_user_id", "user_id"),
        sa.Index("ix_attack_graph_edges_source", "source_node_id"),
        sa.Index("ix_attack_graph_edges_target", "target_node_id"),
        sa.ForeignKeyConstraint(
            ["source_node_id"],
            ["attack_graph_nodes.id"],
            name="fk_attack_graph_edges_source",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["target_node_id"],
            ["attack_graph_nodes.id"],
            name="fk_attack_graph_edges_target",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'potential', 'blocked')",
            name="ck_attack_graph_edges_status",
        ),
    )
