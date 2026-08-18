"""unify RBAC into 4 roles: user, security_analyst, admin, super_admin

Revision ID: 0017
Revises: 0016

Widens ``user_roles.role`` from the 2-value set (``user``/``admin``) to the
unified 4-tier model the single ``/login`` flow needs: ``user`` <
``security_analyst`` < ``admin`` < ``super_admin``. Existing rows are
untouched - every existing ``admin`` stays ``admin``, every existing ``user``
stays ``user`` - this migration only widens the CHECK constraint, it never
rewrites data. ``super_admin`` is deliberately never auto-assigned to anyone
by this migration; an operator promotes an existing admin explicitly (or the
Demo Mode seed creates ``demo_superadmin``), so a hosted deployment never
silently gains a new top-tier account it didn't ask for.
"""
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None

_OLD_ROLES = "role IN ('user', 'admin')"
_NEW_ROLES = "role IN ('user', 'security_analyst', 'admin', 'super_admin')"


def upgrade() -> None:
    op.drop_constraint("ck_user_roles_role", "user_roles", type_="check")
    op.create_check_constraint("ck_user_roles_role", "user_roles", _NEW_ROLES)


def downgrade() -> None:
    # Deliberately no pre-check SELECT here (that would require a live
    # connection and breaks `alembic downgrade --sql` offline rendering,
    # which never executes anything). If any user_roles row still holds
    # 'security_analyst' or 'super_admin', ADD CONSTRAINT below fails with a
    # real Postgres CheckViolation naturally - the narrower constraint
    # cannot be applied over data that would violate it, and no row is ever
    # silently truncated or reassigned.
    op.drop_constraint("ck_user_roles_role", "user_roles", type_="check")
    op.create_check_constraint("ck_user_roles_role", "user_roles", _OLD_ROLES)
