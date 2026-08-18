"""Demo Mode account bootstrap: user/analyst/superadmin/disabled.

Runs once at startup (see ``backend/main.py``'s ``lifespan``), only when
``APP_ENV=local`` and ``DEMO_SEED_ENABLED=true`` - a hosted/staging/
production deployment must never gain accounts it didn't explicitly create.
Idempotent: safe to run on every restart, never duplicates or overwrites an
account someone has since changed by hand (an existing username's password
and role are left untouched - only creation is automatic, not resetting).

``demo_admin`` (role ``admin``) is retired: there is now exactly one
privileged demo account, ``demo_superadmin`` (role ``super_admin``), which
carries every ``admin`` capability plus the ``super_admin``-only ones - the
``admin`` role itself is untouched in the RBAC hierarchy (see migration
0017), only the *demo account* seeded with that role is gone. If a
``demo_admin`` row already exists from a previous run, ``seed_demo_accounts``
disables it in place (never deletes - avoids FK fallout on any rows already
owned by that user_id) so it can no longer sign in, rather than leaving a
second working privileged demo login around.

Reuses the same credential store as the original Local Mode admin bootstrap
(``local_admin_credentials`` / :class:`LocalAdminAuthService`) - despite its
admin-flavored name, that table has always been just "a Local Mode identity
with a username/password", never admin-specific in its actual logic (see
``backend/services/local_admin.py::login``, which never inspects role). This
repurposes it to be the single credential store every Local Mode account
(any role) can sign in through at ``POST /api/auth/local-login``, per the
unified-login requirement.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.local_auth import create_auth_user
from backend.config.settings import Settings
from backend.core.password_hash import hash_password
from backend.repositories.rbac import RbacRepository

logger = logging.getLogger("backend.demo_accounts")


@dataclass(frozen=True)
class _DemoAccountSpec:
    username: str
    role: str
    is_active: bool
    password: str


def _account_specs(settings: Settings) -> list[_DemoAccountSpec]:
    return [
        _DemoAccountSpec("demo_user", "user", True, settings.demo_user_password),
        _DemoAccountSpec("demo_analyst", "security_analyst", True, settings.demo_analyst_password),
        _DemoAccountSpec("demo_superadmin", "super_admin", True, settings.demo_superadmin_password),
        # Deliberately inactive by design - this is the fixture that lets a
        # tester actually exercise "deactivated account" behavior (login
        # correctly refused, admin UI shows it as disabled) rather than that
        # path being untested. Reuses demo_user's password: a distinct
        # password isn't part of what this account is for, and adding one
        # more required env var for it would only make setup harder for no
        # real benefit.
        _DemoAccountSpec("demo_disabled", "user", False, settings.demo_user_password),
    ]


async def _retire_demo_admin(session: AsyncSession, *, repo: RbacRepository) -> str | None:
    """Disable a pre-existing ``demo_admin`` row left over from before the
    demo-account consolidation, if one exists. Never deletes it (a hard
    delete risks FK fallout on anything already seeded under that user_id,
    e.g. ``demo_security_data.py``'s old asset->incident chain) - just flips
    it inactive, the same mechanism ``demo_disabled`` already relies on, so
    login is refused going forward. A no-op, not an error, if the account was
    never created or is already inactive.
    """
    try:
        credential = await repo.get_credential_by_username("demo_admin")
        if credential is None:
            return None
        role_row = await repo.get_role(credential.user_id)
        if role_row is not None and not role_row.is_active:
            return None  # already retired on a previous run
        await repo.set_active(credential.user_id, is_active=False)
        await repo.record_audit(
            actor_user_id=None,
            action="demo_account_retired",
            target_user_id=credential.user_id,
            metadata={"username": "demo_admin", "reason": "consolidated_into_demo_superadmin"},
        )
        await session.commit()
        return "demo_admin"
    except Exception as exc:  # noqa: BLE001 - seeding must never crash startup
        await session.rollback()
        logger.warning("demo_admin_retire_failed", extra={"fields": {"error": type(exc).__name__}})
        return None


async def seed_demo_accounts(session: AsyncSession, *, settings: Settings) -> None:
    """Idempotently ensure the four named Demo Mode accounts exist (plus
    retiring a leftover ``demo_admin`` if one is found - see
    ``_retire_demo_admin``).

    Never raises: a partial failure (e.g. one bad env var) must not crash
    app startup - this is a convenience seed, not a hard dependency (same
    posture as the embedding-model warmup in ``main.py``). Logs exactly what
    happened so a misconfiguration is visible, not silent.
    """
    if not settings.is_local or not settings.demo_seed_enabled:
        return

    repo = RbacRepository(session)
    created: list[str] = []
    skipped_existing: list[str] = []
    skipped_no_password: list[str] = []
    retired = await _retire_demo_admin(session, repo=repo)

    for spec in _account_specs(settings):
        try:
            existing = await repo.get_credential_by_username(spec.username)
            if existing is not None:
                skipped_existing.append(spec.username)
                continue
            if not spec.password:
                skipped_no_password.append(spec.username)
                continue

            user_id = await create_auth_user(session, email=f"{spec.username}@local.demo.invalid")
            await repo.set_role(user_id, role=spec.role)
            if not spec.is_active:
                await repo.set_active(user_id, is_active=False)
            await repo.create_local_admin_credential(
                user_id=user_id,
                username=spec.username,
                password_hash=hash_password(spec.password),
            )
            await repo.record_audit(
                actor_user_id=None,
                action="demo_account_seeded",
                target_user_id=user_id,
                metadata={"username": spec.username, "role": spec.role},
            )
            await session.commit()
            created.append(spec.username)
        except Exception as exc:  # noqa: BLE001 - seeding must never crash startup
            await session.rollback()
            logger.warning(
                "demo_account_seed_failed",
                extra={"fields": {"username": spec.username, "error": type(exc).__name__}},
            )

    if skipped_no_password:
        logger.warning(
            "demo_account_seed_missing_password",
            extra={
                "fields": {
                    "accounts": skipped_no_password,
                    "hint": (
                        "Set DEMO_USER_PASSWORD / DEMO_ANALYST_PASSWORD / "
                        "DEMO_SUPERADMIN_PASSWORD in .env to enable these "
                        "accounts - no weak password is ever auto-generated."
                    ),
                }
            },
        )
    logger.info(
        "demo_account_seed_complete",
        extra={
            "fields": {
                "created": created,
                "already_existed": skipped_existing,
                "missing_password": skipped_no_password,
                "retired": [retired] if retired else [],
            }
        },
    )
