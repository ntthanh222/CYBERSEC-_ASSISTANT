"""Allow the same MITRE technique to be linked to multiple incidents.

Revision ID: 0021_mitre_incident_reuse
Revises: 0020
Create Date: 2026-08-08
"""

from alembic import op


revision = "0021_mitre_incident_reuse"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "uq_mitre_coverage_owner_technique",
        "mitre_technique_coverage",
        type_="unique",
    )
    op.create_index(
        "ix_mitre_coverage_user_technique",
        "mitre_technique_coverage",
        ["user_id", "technique_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_mitre_coverage_user_technique", table_name="mitre_technique_coverage")
    op.create_unique_constraint(
        "uq_mitre_coverage_owner_technique",
        "mitre_technique_coverage",
        ["user_id", "technique_id"],
    )
