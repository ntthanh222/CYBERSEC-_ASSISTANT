"""Asset inventory model (Phase 3, Task #5 — Assets vertical slice).

An asset is analyst-entered inventory data — there is no external feed for
"servers/workstations this user owns", so unlike CVE metadata this is always
first-party data. Owner-scoped exactly like ``conversations`` and
``security_scan_history`` (migration 0004): a ``user_id`` column plus a
Postgres Row Level Security policy enforce that a caller only ever sees their
own assets, independent of the service-layer ownership check in
``backend.services.assets``.
"""
import uuid
from typing import List, Optional
import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column
from backend.database.base import Base, JSONVariant, TimestampMixin, UuidPrimaryKeyMixin, UuidType

ASSET_TYPES = ("server", "workstation", "cloud_resource", "database", "network_device")
BUSINESS_CRITICALITIES = ("low", "medium", "high", "critical")
PATCH_STATUSES = (
    "unknown",
    "not_started",
    "in_progress",
    "patched",
    "accepted_risk",
    "not_applicable",
)
EXPLOIT_EVIDENCE_LEVELS = (
    "none",
    "unconfirmed",
    "public_poc",
    "active_exploitation",
    "internal_confirmation",
)


class Asset(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "assets"

    user_id: Mapped[uuid.UUID] = mapped_column(UuidType, nullable=False)
    name: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    type: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    hostname: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    ip_address: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    operating_system: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    owner: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    department: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    business_criticality: Mapped[str] = mapped_column(sa.String(16), nullable=False)
    internet_exposed: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False)
    description: Mapped[str] = mapped_column(sa.Text, nullable=False, default="")
    # CVE ids the analyst has linked to this asset. Plain string array, not a
    # join table, for this first slice - Task #5's Vulnerabilities slice may
    # promote this to a real AssetCveLink table with per-link patch status;
    # kept simple here since Assets must ship independently first.
    linked_cves: Mapped[List[str]] = mapped_column(JSONVariant, nullable=False, default=list)
    patch_status: Mapped[Optional[str]] = mapped_column(sa.String(16), nullable=True)
    exploit_evidence: Mapped[Optional[str]] = mapped_column(sa.String(32), nullable=True)

    __table_args__ = (
        sa.Index("ix_assets_user_id", "user_id"),
        sa.Index("ix_assets_created_at", sa.text("created_at DESC")),
        sa.CheckConstraint(
            "type IN ('server', 'workstation', 'cloud_resource', 'database', 'network_device')",
            name="ck_assets_type",
        ),
        sa.CheckConstraint(
            "business_criticality IN ('low', 'medium', 'high', 'critical')",
            name="ck_assets_business_criticality",
        ),
        sa.CheckConstraint(
            "patch_status IS NULL OR patch_status IN "
            "('unknown', 'not_started', 'in_progress', 'patched', "
            "'accepted_risk', 'not_applicable')",
            name="ck_assets_patch_status",
        ),
        sa.CheckConstraint(
            "exploit_evidence IS NULL OR exploit_evidence IN "
            "('none', 'unconfirmed', 'public_poc', 'active_exploitation', 'internal_confirmation')",
            name="ck_assets_exploit_evidence",
        ),
    )
