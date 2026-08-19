"""Task 3 (vuln-lifecycle Fingerprinting + Rescan Diff + SLA): sla_policies

Revision ID: 0027
Revises: 0026

Creates ``sla_policies`` - maps ``severity`` to how many hours a confirmed
``Finding`` of that severity gets before its ``deadline``
(``backend.services.sla.compute_deadline``). ``project_id IS NULL`` rows are
the global default; a non-NULL ``project_id`` row overrides the default for
that one project+severity pair.

Also seeds the global defaults as a data migration: critical=24h, high=72h,
medium=168h (7 days). ``low`` deliberately gets NO seeded row - a severity
with no applicable policy row means "no SLA deadline applies", which is the
correct behavior for ``low`` per the plan.

**RLS shape (read the module docstring in
``backend/database/models/sla_policy.py`` for the nullable-uniqueness
rationale first):** unlike every other table in this migration series,
``sla_policies`` has two different visibility/write rules depending on
whether ``project_id IS NULL``:

- Global-default rows (``project_id IS NULL``) must be readable by every
  authenticated user (so a project member's "effective policy" view -
  ``GET /api/projects/{id}/sla-policies`` - can merge the default in) but
  writable only by a global admin/super_admin.
- Project-override rows (``project_id IS NOT NULL``) follow the same
  project-membership visibility pattern as 0025's ``scan_runs``/0026's
  ``findings`` (read: any project member or workspace owner/admin or global
  admin; write: same set, since ``backend.core.project_authorization`` is
  the actual authorization gate for the API's write role check - RLS here
  is defense-in-depth like every other table in this series, not the
  authoritative check).

0024's project policy is a single ``FOR ALL`` policy because every row
there has a uniform visibility rule. This table does not, so it gets two
separate policies instead of one: ``sla_policies_read`` (``FOR SELECT``,
the broader of the two rules) and ``sla_policies_write`` (``FOR INSERT,
UPDATE, DELETE``, the narrower, admin-gated-for-NULL-rows rule). Not FORCEd,
for the same reason 0023-0026 document: the route-level dependencies are
the authoritative check, not RLS visibility.
"""
import sqlalchemy as sa
from alembic import op

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None

_SLA_POLICY_READ_VISIBILITY = (
    "sla_policies.project_id IS NULL "
    "OR EXISTS (SELECT 1 FROM project_members pm WHERE pm.project_id = sla_policies.project_id "
    "AND pm.user_id = auth.uid()) "
    "OR EXISTS (SELECT 1 FROM projects p JOIN workspace_members wm ON wm.workspace_id = p.workspace_id "
    "WHERE p.id = sla_policies.project_id AND wm.user_id = auth.uid() "
    "AND wm.workspace_role IN ('owner', 'admin')) "
    "OR EXISTS (SELECT 1 FROM projects p WHERE p.id = sla_policies.project_id "
    "AND p.owner_user_id = auth.uid()) "
    "OR EXISTS (SELECT 1 FROM user_roles ur WHERE ur.user_id = auth.uid() "
    "AND ur.role IN ('admin', 'super_admin') AND ur.is_active)"
)

_SLA_POLICY_WRITE_VISIBILITY = (
    "(sla_policies.project_id IS NULL "
    "AND EXISTS (SELECT 1 FROM user_roles ur WHERE ur.user_id = auth.uid() "
    "AND ur.role IN ('admin', 'super_admin') AND ur.is_active)) "
    "OR (sla_policies.project_id IS NOT NULL AND ("
    "EXISTS (SELECT 1 FROM project_members pm WHERE pm.project_id = sla_policies.project_id "
    "AND pm.user_id = auth.uid() AND pm.project_role IN ('owner', 'security')) "
    "OR EXISTS (SELECT 1 FROM projects p JOIN workspace_members wm ON wm.workspace_id = p.workspace_id "
    "WHERE p.id = sla_policies.project_id AND wm.user_id = auth.uid() "
    "AND wm.workspace_role IN ('owner', 'admin')) "
    "OR EXISTS (SELECT 1 FROM projects p WHERE p.id = sla_policies.project_id "
    "AND p.owner_user_id = auth.uid()) "
    "OR EXISTS (SELECT 1 FROM user_roles ur WHERE ur.user_id = auth.uid() "
    "AND ur.role IN ('admin', 'super_admin') AND ur.is_active)"
    "))"
)

_SEED_HOURS = {"critical": 24, "high": 72, "medium": 168}


def upgrade() -> None:
    op.create_table(
        "sla_policies",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("project_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("hours_to_deadline", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name="fk_sla_policies_project_id", ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "project_id", "severity", name="uq_sla_policies_project_severity"
        ),
        sa.CheckConstraint(
            "severity IN ('low', 'medium', 'high', 'critical')", name="ck_sla_policies_severity"
        ),
        sa.CheckConstraint("hours_to_deadline > 0", name="ck_sla_policies_hours_positive"),
    )
    # Plain UniqueConstraint(project_id, severity) alone does not stop two
    # (NULL, 'high') rows from both existing - NULLs never compare equal for
    # uniqueness on either Postgres or SQLite - so a second, partial unique
    # index covers just the global-default rows. See
    # backend/database/models/sla_policy.py's docstring for the full
    # rationale.
    op.create_index(
        "uq_sla_policies_global_severity",
        "sla_policies",
        ["severity"],
        unique=True,
        postgresql_where=sa.text("project_id IS NULL"),
        sqlite_where=sa.text("project_id IS NULL"),
    )

    # Data migration: seed the global defaults. `low` intentionally gets no
    # row - see the module docstring.
    for severity, hours in _SEED_HOURS.items():
        op.execute(
            sa.text(
                "INSERT INTO sla_policies (id, project_id, severity, hours_to_deadline) "
                "VALUES (gen_random_uuid(), NULL, :severity, :hours)"
            ).bindparams(severity=severity, hours=hours)
        )

    op.execute(sa.text("GRANT SELECT, INSERT, UPDATE, DELETE ON sla_policies TO authenticated"))
    op.execute(sa.text("ALTER TABLE sla_policies ENABLE ROW LEVEL SECURITY"))
    op.execute(
        sa.text(
            f"CREATE POLICY sla_policies_read ON sla_policies "
            f"FOR SELECT USING ({_SLA_POLICY_READ_VISIBILITY})"
        )
    )
    op.execute(
        sa.text(
            f"CREATE POLICY sla_policies_write ON sla_policies "
            f"FOR INSERT WITH CHECK ({_SLA_POLICY_WRITE_VISIBILITY})"
        )
    )
    op.execute(
        sa.text(
            f"CREATE POLICY sla_policies_update ON sla_policies "
            f"FOR UPDATE USING ({_SLA_POLICY_WRITE_VISIBILITY}) "
            f"WITH CHECK ({_SLA_POLICY_WRITE_VISIBILITY})"
        )
    )
    op.execute(
        sa.text(
            f"CREATE POLICY sla_policies_delete ON sla_policies "
            f"FOR DELETE USING ({_SLA_POLICY_WRITE_VISIBILITY})"
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DROP POLICY IF EXISTS sla_policies_delete ON sla_policies"))
    op.execute(sa.text("DROP POLICY IF EXISTS sla_policies_update ON sla_policies"))
    op.execute(sa.text("DROP POLICY IF EXISTS sla_policies_write ON sla_policies"))
    op.execute(sa.text("DROP POLICY IF EXISTS sla_policies_read ON sla_policies"))

    op.execute(sa.text("ALTER TABLE sla_policies DISABLE ROW LEVEL SECURITY"))
    op.execute(sa.text("REVOKE SELECT, INSERT, UPDATE, DELETE ON sla_policies FROM authenticated"))

    op.drop_index("uq_sla_policies_global_severity", table_name="sla_policies")
    op.drop_table("sla_policies")
