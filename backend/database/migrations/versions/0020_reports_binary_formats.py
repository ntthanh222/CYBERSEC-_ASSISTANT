"""allow pdf and docx report formats

Revision ID: 0020
Revises: 0019
"""

from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_report_records_format", "report_records", type_="check")
    op.create_check_constraint(
        "ck_report_records_format",
        "report_records",
        "format IN ('markdown', 'pdf', 'docx', 'csv')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_report_records_format", "report_records", type_="check")
    op.create_check_constraint(
        "ck_report_records_format",
        "report_records",
        "format IN ('markdown', 'csv')",
    )
