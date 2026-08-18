"""phase 3 codex: incidents and tasks

Revision ID: 0011
Revises: 0010
"""

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "incidents",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("assignee", sa.String(length=160), nullable=False, server_default=""),
        sa.Column("source_alert_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("asset_name", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("cve_id", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["auth.users.id"], name="fk_incidents_user_id", ondelete="CASCADE"
        ),
        sa.CheckConstraint(
            "severity IN ('low', 'medium', 'high', 'critical')", name="ck_incidents_severity"
        ),
        sa.CheckConstraint(
            "status IN ("
            "'open', 'triaged', 'in_progress', 'contained', 'eradicated', 'recovered', 'closed'"
            ")",
            name="ck_incidents_status",
        ),
    )
    op.create_index("ix_incidents_user_id", "incidents", ["user_id"])
    op.create_index("ix_incidents_created_at", "incidents", [sa.text("created_at DESC")])

    op.create_table(
        "incident_tasks",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("incident_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="pending"),
        sa.Column("owner", sa.String(length=160), nullable=False, server_default=""),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["auth.users.id"], name="fk_incident_tasks_user_id", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["incident_id"],
            ["incidents.id"],
            name="fk_incident_tasks_incident_id",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'in_progress', 'completed', 'blocked')",
            name="ck_incident_tasks_status",
        ),
    )
    op.create_index("ix_incident_tasks_user_id", "incident_tasks", ["user_id"])
    op.create_index("ix_incident_tasks_incident_id", "incident_tasks", ["incident_id"])

    op.create_table(
        "incident_timeline_events",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("incident_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("actor", sa.String(length=240), nullable=False, server_default=""),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["auth.users.id"], name="fk_incident_timeline_user_id", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["incident_id"],
            ["incidents.id"],
            name="fk_incident_timeline_incident_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_incident_timeline_user_id", "incident_timeline_events", ["user_id"])
    op.create_index("ix_incident_timeline_incident_id", "incident_timeline_events", ["incident_id"])
    op.create_index(
        "ix_incident_timeline_created_at", "incident_timeline_events", [sa.text("created_at DESC")]
    )

    for table in ("incidents", "incident_tasks", "incident_timeline_events"):
        op.execute(
            sa.text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text -- static schema migration string
                f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO authenticated"
            )
        )
        op.execute(
            sa.text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text -- static schema migration string
                f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"
            )
        )
        op.execute(
            sa.text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text -- static schema migration string
                f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"
            )
        )
        op.execute(
            sa.text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text -- static schema migration string
                f"CREATE POLICY {table}_owner_only ON {table} "
                "FOR ALL USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id)"
            )
        )


def downgrade() -> None:
    for table in ("incident_timeline_events", "incident_tasks", "incidents"):
        op.execute(
            sa.text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text -- static schema migration string
                f"DROP POLICY IF EXISTS {table}_owner_only ON {table}"
            )
        )
        op.execute(
            sa.text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text -- static schema migration string
                f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY"
            )
        )
        op.execute(
            sa.text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text -- static schema migration string
                f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY"
            )
        )
        op.execute(
            sa.text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text -- static schema migration string
                f"REVOKE SELECT, INSERT, UPDATE, DELETE ON {table} FROM authenticated"
            )
        )
    op.drop_index("ix_incident_timeline_created_at", table_name="incident_timeline_events")
    op.drop_index("ix_incident_timeline_incident_id", table_name="incident_timeline_events")
    op.drop_index("ix_incident_timeline_user_id", table_name="incident_timeline_events")
    op.drop_table("incident_timeline_events")
    op.drop_index("ix_incident_tasks_incident_id", table_name="incident_tasks")
    op.drop_index("ix_incident_tasks_user_id", table_name="incident_tasks")
    op.drop_table("incident_tasks")
    op.drop_index("ix_incidents_created_at", table_name="incidents")
    op.drop_index("ix_incidents_user_id", table_name="incidents")
    op.drop_table("incidents")
