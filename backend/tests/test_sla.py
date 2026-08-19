"""backend.services.sla: compute_deadline (project-override-vs-global-
default fallback, no-policy-for-severity) and is_overdue (pure function,
Task 3)."""
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

import pytest

from backend.database.models.sla_policy import SlaPolicy
from backend.services import sla


async def _seed_policy(
    db_sessionmaker, *, project_id: Optional[uuid.UUID], severity: str, hours: int
) -> None:
    async with db_sessionmaker() as session:
        session.add(SlaPolicy(project_id=project_id, severity=severity, hours_to_deadline=hours))
        await session.commit()


@dataclass
class _FakeFinding:
    """A bare stand-in exercising exactly what is_overdue reads
    (``deadline``, ``status``) - sla.is_overdue takes no other dependency,
    so a full ORM Finding row is unnecessary ceremony for these tests."""

    deadline: Optional[datetime]
    status: str


# ─── compute_deadline ───────────────────────────────────────────────────────


async def test_compute_deadline_uses_global_default_when_no_project_override(db_sessionmaker):
    project_id = uuid.uuid4()
    await _seed_policy(db_sessionmaker, project_id=None, severity="high", hours=72)

    confirmed_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    async with db_sessionmaker() as session:
        deadline = await sla.compute_deadline(
            project_id=project_id, severity="high", confirmed_at=confirmed_at, session=session
        )
    assert deadline == confirmed_at + timedelta(hours=72)


async def test_compute_deadline_prefers_project_override_over_global_default(db_sessionmaker):
    project_id = uuid.uuid4()
    await _seed_policy(db_sessionmaker, project_id=None, severity="high", hours=72)
    await _seed_policy(db_sessionmaker, project_id=project_id, severity="high", hours=4)

    confirmed_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    async with db_sessionmaker() as session:
        deadline = await sla.compute_deadline(
            project_id=project_id, severity="high", confirmed_at=confirmed_at, session=session
        )
    assert deadline == confirmed_at + timedelta(hours=4)


async def test_compute_deadline_a_different_projects_override_does_not_leak(db_sessionmaker):
    project_a = uuid.uuid4()
    project_b = uuid.uuid4()
    await _seed_policy(db_sessionmaker, project_id=None, severity="high", hours=72)
    await _seed_policy(db_sessionmaker, project_id=project_a, severity="high", hours=4)

    confirmed_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    async with db_sessionmaker() as session:
        deadline = await sla.compute_deadline(
            project_id=project_b, severity="high", confirmed_at=confirmed_at, session=session
        )
    # project_b has no override of its own - falls back to the global default,
    # not project_a's override.
    assert deadline == confirmed_at + timedelta(hours=72)


async def test_compute_deadline_returns_none_when_no_policy_at_all_for_the_severity(
    db_sessionmaker,
):
    project_id = uuid.uuid4()
    # No `low` row seeded anywhere (mirrors the real migration's seed data:
    # low deliberately gets no default row).
    await _seed_policy(db_sessionmaker, project_id=None, severity="high", hours=72)

    confirmed_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    async with db_sessionmaker() as session:
        deadline = await sla.compute_deadline(
            project_id=project_id, severity="low", confirmed_at=confirmed_at, session=session
        )
    assert deadline is None


# ─── is_overdue ──────────────────────────────────────────────────────────────


def test_is_overdue_true_when_deadline_passed_and_status_non_terminal():
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    finding = _FakeFinding(deadline=past, status="confirmed")
    assert sla.is_overdue(finding) is True


@pytest.mark.parametrize("status", ["closed", "false_positive", "accepted_risk"])
def test_is_overdue_false_for_terminal_status_even_if_deadline_passed(status):
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    finding = _FakeFinding(deadline=past, status=status)
    assert sla.is_overdue(finding) is False


def test_is_overdue_false_when_no_deadline():
    finding = _FakeFinding(deadline=None, status="confirmed")
    assert sla.is_overdue(finding) is False


def test_is_overdue_false_when_deadline_in_the_future():
    future = datetime.now(timezone.utc) + timedelta(hours=1)
    finding = _FakeFinding(deadline=future, status="confirmed")
    assert sla.is_overdue(finding) is False


def test_is_overdue_handles_naive_deadline_as_utc():
    # SQLite round-trips DateTime(timezone=True) as naive - is_overdue must
    # treat a naive value as already-UTC rather than raising or misjudging.
    naive_past = (datetime.now(timezone.utc) - timedelta(hours=1)).replace(tzinfo=None)
    finding = _FakeFinding(deadline=naive_past, status="open")
    assert sla.is_overdue(finding) is True

    naive_future = (datetime.now(timezone.utc) + timedelta(hours=1)).replace(tzinfo=None)
    finding_future = _FakeFinding(deadline=naive_future, status="open")
    assert sla.is_overdue(finding_future) is False


def test_is_overdue_true_for_fixed_status_not_yet_verified():
    # `fixed` is explicitly NOT a terminal status for overdue purposes - a
    # fix awaiting verification can still be flagged overdue for someone to
    # verify it.
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    finding = _FakeFinding(deadline=past, status="fixed")
    assert sla.is_overdue(finding) is True
