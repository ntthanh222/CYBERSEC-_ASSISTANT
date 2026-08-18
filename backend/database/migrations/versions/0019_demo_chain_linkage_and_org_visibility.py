"""final demo: real FK linkage across asset->vulnerability->alert->incident->
mitre technique

Revision ID: 0019
Revises: 0018

Every one of these tables already existed (Phase 3) with real CRUD, but the
"asset" a vulnerability/alert/incident referred to was a bare free-text
``asset_name`` string, and ``incidents.source_alert_id`` was an unenforced
UUID column with no FK constraint at all. Adds real nullable FKs:
``vulnerabilities.asset_id``, ``alerts.asset_id``, ``alerts.vulnerability_id``,
a real FK constraint on the existing ``incidents.source_alert_id``, and
``mitre_technique_coverage.incident_id`` - so "asset -> vulnerability ->
alert -> incident -> MITRE technique" is an actual relational chain a query
can join across, not matching strings.

Deliberately does not touch RLS/visibility - every one of these tables stays
strictly owner-scoped (``USING (auth.uid() = user_id)``, unchanged from
migrations 0007/0009/0010/0011/0012). A single coherent demo chain visible to
every demo role is built by seeding an equivalent linked chain under each
role's own account (see ``backend/services/demo_security_data.py``), not by
widening cross-account read access - that would need touching every
repository's query layer to stop hard-filtering reads by the caller's own
``user_id`` (see docstring on ``backend/repositories/assets.py``), a much
larger and riskier change than this demo actually needs.
"""
import sqlalchemy as sa
from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "vulnerabilities", sa.Column("asset_id", sa.Uuid(as_uuid=True), nullable=True)
    )
    op.create_index("ix_vulnerabilities_asset_id", "vulnerabilities", ["asset_id"])
    op.create_foreign_key(
        "fk_vulnerabilities_asset_id",
        "vulnerabilities",
        "assets",
        ["asset_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.add_column("alerts", sa.Column("asset_id", sa.Uuid(as_uuid=True), nullable=True))
    op.add_column(
        "alerts", sa.Column("vulnerability_id", sa.Uuid(as_uuid=True), nullable=True)
    )
    op.create_index("ix_alerts_asset_id", "alerts", ["asset_id"])
    op.create_index("ix_alerts_vulnerability_id", "alerts", ["vulnerability_id"])
    op.create_foreign_key(
        "fk_alerts_asset_id", "alerts", "assets", ["asset_id"], ["id"], ondelete="SET NULL"
    )
    op.create_foreign_key(
        "fk_alerts_vulnerability_id",
        "alerts",
        "vulnerabilities",
        ["vulnerability_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_index("ix_incidents_source_alert_id", "incidents", ["source_alert_id"])
    op.create_foreign_key(
        "fk_incidents_source_alert_id",
        "incidents",
        "alerts",
        ["source_alert_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.add_column(
        "mitre_technique_coverage",
        sa.Column("incident_id", sa.Uuid(as_uuid=True), nullable=True),
    )
    op.create_index(
        "ix_mitre_coverage_incident_id", "mitre_technique_coverage", ["incident_id"]
    )
    op.create_foreign_key(
        "fk_mitre_coverage_incident_id",
        "mitre_technique_coverage",
        "incidents",
        ["incident_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_mitre_coverage_incident_id", "mitre_technique_coverage", type_="foreignkey"
    )
    op.drop_index("ix_mitre_coverage_incident_id", table_name="mitre_technique_coverage")
    op.drop_column("mitre_technique_coverage", "incident_id")

    op.drop_constraint("fk_incidents_source_alert_id", "incidents", type_="foreignkey")
    op.drop_index("ix_incidents_source_alert_id", table_name="incidents")

    op.drop_constraint("fk_alerts_vulnerability_id", "alerts", type_="foreignkey")
    op.drop_constraint("fk_alerts_asset_id", "alerts", type_="foreignkey")
    op.drop_index("ix_alerts_vulnerability_id", table_name="alerts")
    op.drop_index("ix_alerts_asset_id", table_name="alerts")
    op.drop_column("alerts", "vulnerability_id")
    op.drop_column("alerts", "asset_id")

    op.drop_constraint("fk_vulnerabilities_asset_id", "vulnerabilities", type_="foreignkey")
    op.drop_index("ix_vulnerabilities_asset_id", table_name="vulnerabilities")
    op.drop_column("vulnerabilities", "asset_id")
