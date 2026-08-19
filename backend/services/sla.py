"""SLA / deadline computation (Task 3) - deterministic, no LLM involved.

``compute_deadline`` is the ONLY place ``Finding.deadline`` is set from (see
``backend.services.finding.FindingService.transition``, which calls it every
time a transition's ``to_status == "confirmed"``). ``is_overdue`` is a pure
function computed at query/display time - the plan is explicit that no
stored boolean column should exist for this, to avoid it drifting out of
sync with the current time and the finding's current status.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database.models.finding import Finding
from backend.database.models.sla_policy import SlaPolicy

#: A Finding in any of these statuses is done, one way or another - it can
#: never be "overdue" again regardless of how far in the past its deadline
#: is, matching the plan's ``is_overdue`` definition exactly (a fixed-but-
#: not-yet-verified finding is deliberately NOT terminal here: it is still
#: mid-lifecycle and can still be judged overdue for someone to verify it).
TERMINAL_STATUSES = frozenset({"closed", "false_positive", "accepted_risk"})


async def compute_deadline(
    *,
    project_id: uuid.UUID,
    severity: str,
    confirmed_at: datetime,
    session: AsyncSession,
) -> Optional[datetime]:
    """``confirmed_at + hours_to_deadline`` using the most specific
    applicable ``SlaPolicy`` row: a project-level override for
    ``(project_id, severity)`` if one exists, else the global default
    (``project_id IS NULL``) for that ``severity``, else ``None`` - meaning
    no SLA deadline applies to this severity at all (the plan's explicit
    design for ``low``, which is seeded with no default row)."""
    policy = await session.scalar(
        sa.select(SlaPolicy).where(
            SlaPolicy.project_id == project_id, SlaPolicy.severity == severity
        )
    )
    if policy is None:
        policy = await session.scalar(
            sa.select(SlaPolicy).where(
                SlaPolicy.project_id.is_(None), SlaPolicy.severity == severity
            )
        )
    if policy is None:
        return None
    return confirmed_at + timedelta(hours=policy.hours_to_deadline)


def is_overdue(finding: Finding) -> bool:
    """Pure function, no DB/session involved - always computed fresh, never
    stored, so it can never drift out of sync with "now" or the finding's
    current status."""
    if finding.deadline is None:
        return False
    if finding.status in TERMINAL_STATUSES:
        return False
    deadline = finding.deadline
    if deadline.tzinfo is None:
        # SQLite (test suite) round-trips DateTime(timezone=True) as naive -
        # every value this application writes is already UTC, so a naive
        # value is reinterpreted as UTC rather than local time, mirroring
        # backend.core.timeutils.ensure_utc's documented rule.
        deadline = deadline.replace(tzinfo=timezone.utc)
    return deadline < datetime.now(timezone.utc)
