"""Project-scoped Security Dashboard (Task 5) - pure read/aggregation over
``Finding``/``ScanRun``. No new domain model, no LLM, no mocked numbers:
every field returned by ``get_security_dashboard`` is the direct result of
an aggregate query or a documented, deterministic arithmetic formula applied
to real stored data.

**Security Score formula** (0-100, higher is better):

    security_score = 100 - min(100, critical_open*15 + high_open*8
                                     + medium_open*3 + low_open*1)

There is no existing scoring convention anywhere else in this codebase, so
this is a made-up business rule designed for this task. Rationale for the
specific weights:

* Purely a function of *currently open* findings by severity (the same
  ``TERMINAL_STATUSES``-excluded set the "Open Findings" metric uses) - a
  resolved finding cannot depress the score forever, and the score always
  reflects the project's live risk exposure, not its history.
* Weights are a simple linear penalty, steeply decreasing by severity
  (15/8/3/1) so that a single critical finding visibly costs far more than
  a single low one, without letting a large pile of low-severity findings
  alone crater the score to 0 as fast as a small handful of criticals would
  (e.g. 7 criticals already zeroes the score; it takes 100 lows to do the
  same).
* Clamped to ``[0, 100]`` via ``min(100, ...)`` before subtracting from 100
  (so the penalty can never push the score negative) - a project can never
  score below 0 no matter how many open findings it has, and a project with
  zero open findings always scores exactly 100.
* Deterministic arithmetic only, no LLM or other non-deterministic input,
  per the plan's explicit "no LLM in analytics" constraint - the same input
  counts always produce the same score.

The identical formula is reused for each ``SecurityTrendPoint`` (applied to
that scan run's own severity counts) so the trend and the current score are
directly comparable on the same 0-100 scale.

**"Fixed This Week" choice**: counts ``FindingTransition`` rows with
``to_status == "closed"`` in the last 7 days, not ``"verified"``. ``closed``
is the terminal, fully-confirmed-done state (see ``sla.TERMINAL_STATUSES``);
``verified`` is still mid-lifecycle (a verified finding can still be
reopened, and does not yet count as "resolved" the way a dashboard headline
metric implies). ``closed`` is what "fixed" means to someone scanning this
dashboard for a weekly summary.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.authorization import AppUser
from backend.core.exceptions import NotFoundError
from backend.repositories.findings import FindingRepository
from backend.repositories.project import ProjectRepository
from backend.repositories.scan_runs import ScanRunRepository
from backend.services import sla as sla_service

#: Severity -> penalty-per-open-finding weight used by both the current
#: score and every trend point - see the module docstring for rationale.
_SEVERITY_WEIGHTS = {"critical": 15, "high": 8, "medium": 3, "low": 1}
#: How many findings each metric-card list ("Top Risks", "Latest Findings")
#: shows - a fixed, documented small number per the brief, not paginated.
_LIST_LIMIT = 5
#: How many past completed scan runs the trend series covers.
_TREND_LIMIT = 10
#: "Fixed This Week" is a literal rolling 7-day window from now.
_FIXED_THIS_WEEK_WINDOW = timedelta(days=7)
#: See the module docstring's "Fixed This Week" rationale.
_FIXED_THIS_WEEK_TO_STATUS = "closed"


def _score_from_counts(counts: dict[str, int]) -> int:
    penalty = sum(_SEVERITY_WEIGHTS[severity] * counts.get(severity, 0) for severity in _SEVERITY_WEIGHTS)
    return 100 - min(100, penalty)


def _finding_dict(record) -> dict[str, Any]:
    # Mirrors backend.api.findings._finding_dict exactly - duplicated rather
    # than imported to avoid an api -> service import (services must not
    # depend on the API layer).
    return {
        "id": record.id,
        "project_id": record.project_id,
        "scan_run_id": record.scan_run_id,
        "fingerprint": record.fingerprint,
        "rule_id": record.rule_id,
        "category": record.category,
        "title": record.title,
        "evidence": record.evidence,
        "impact": record.impact,
        "remediation": record.remediation,
        "severity": record.severity,
        "status": record.status,
        "target": record.target,
        "cve_id": record.cve_id,
        "assignee_user_id": record.assignee_user_id,
        "deadline": record.deadline,
        "is_overdue": sla_service.is_overdue(record),
        "verification_notes": record.verification_notes,
        "resolution_reason": record.resolution_reason,
        "first_seen_scan_run_id": record.first_seen_scan_run_id,
        "last_seen_scan_run_id": record.last_seen_scan_run_id,
        "closed_at": record.closed_at,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }


class ProjectDashboardService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._projects = ProjectRepository(session)
        self._findings = FindingRepository(session)
        self._scan_runs = ScanRunRepository(session)

    def _trend_point(self, scan_run) -> dict[str, Any]:
        summary = scan_run.summary or {}
        counts = {severity: int(summary.get(severity, 0) or 0) for severity in _SEVERITY_WEIGHTS}
        return {
            "scan_run_id": scan_run.id,
            "completed_at": scan_run.completed_at,
            "open_count": sum(counts.values()),
            "score": _score_from_counts(counts),
        }

    async def get_security_dashboard(
        self, project_id: uuid.UUID, actor: Optional[AppUser] = None
    ) -> dict[str, Any]:
        """Computes every dashboard field from real aggregate queries.
        ``actor`` is accepted for symmetry with other service methods and
        potential future audit logging; authorization itself already
        happened at the route layer (``Depends(get_project_member)`` - any
        project member, including viewer, may read this)."""
        project = await self._projects.get(project_id)
        if project is None:
            raise NotFoundError("Project not found.")

        open_by_severity = await self._findings.count_open_by_severity(project_id=project_id)
        open_findings = sum(open_by_severity.values())
        waiting_verify = await self._findings.count_by_status(project_id=project_id, status="fixed")
        overdue = await self._findings.count_overdue(project_id=project_id)
        since = datetime.now(timezone.utc) - _FIXED_THIS_WEEK_WINDOW
        fixed_this_week = await self._findings.count_transitions_to_status_since(
            project_id=project_id, to_status=_FIXED_THIS_WEEK_TO_STATUS, since=since
        )

        latest_scan = await self._scan_runs.get_latest_for_project(project_id=project_id)
        recent_completed = await self._scan_runs.list_recent_completed(
            project_id=project_id, limit=_TREND_LIMIT
        )

        top_risks = await self._findings.list_top_risks(project_id=project_id, limit=_LIST_LIMIT)
        latest_findings = await self._findings.list_latest(project_id=project_id, limit=_LIST_LIMIT)

        assigned_open = await self._findings.count_assigned_open(project_id=project_id)
        assigned_open_by_assignee = await self._findings.count_assigned_open_by_assignee(
            project_id=project_id
        )

        return {
            "project_id": project_id,
            "security_score": _score_from_counts(open_by_severity),
            "open_findings": open_findings,
            "open_by_severity": open_by_severity,
            "waiting_verify": waiting_verify,
            "overdue": overdue,
            "fixed_this_week": fixed_this_week,
            "latest_scan": (
                {
                    "id": latest_scan.id,
                    "status": latest_scan.status,
                    "target": latest_scan.target,
                    "completed_at": latest_scan.completed_at,
                    "summary": latest_scan.summary,
                }
                if latest_scan is not None
                else None
            ),
            "security_trend": [self._trend_point(run) for run in recent_completed],
            "top_risks": [_finding_dict(item) for item in top_risks],
            "latest_findings": [_finding_dict(item) for item in latest_findings],
            "assigned_open": assigned_open,
            "assigned_open_by_assignee": [
                {"assignee_user_id": assignee_id, "open_count": count}
                for assignee_id, count in assigned_open_by_assignee.items()
            ],
        }
