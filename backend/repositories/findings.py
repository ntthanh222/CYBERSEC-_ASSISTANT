"""Finding and FindingTransition persistence."""
import uuid
from datetime import datetime, timezone
from typing import Any, Optional, Sequence

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database.models.finding import Finding, FindingTransition
from backend.database.models.project import Project
# TERMINAL_STATUSES is a plain data constant (no repository/session
# dependency in backend.services.sla), so importing it here to build the
# SQL overdue predicate for list_by_assignee (Task 4 review fix) does not
# create a circular import - it is the single source of truth for "which
# statuses can never be overdue", shared with sla.is_overdue's own
# definition, and must be kept in sync with it.
from backend.services.sla import TERMINAL_STATUSES


class FindingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        project_id: uuid.UUID,
        scan_run_id: Optional[uuid.UUID],
        fingerprint: str,
        rule_id: str,
        category: str,
        title: str,
        evidence: str,
        impact: str,
        remediation: str,
        severity: str,
        target: str,
        cve_id: Optional[str] = None,
        assignee_user_id: Optional[uuid.UUID] = None,
        status: str = "open",
        first_seen_scan_run_id: Optional[uuid.UUID] = None,
        last_seen_scan_run_id: Optional[uuid.UUID] = None,
    ) -> Finding:
        record = Finding(
            project_id=project_id,
            scan_run_id=scan_run_id,
            fingerprint=fingerprint,
            rule_id=rule_id,
            category=category,
            title=title,
            evidence=evidence,
            impact=impact,
            remediation=remediation,
            severity=severity,
            status=status,
            target=target,
            cve_id=cve_id,
            assignee_user_id=assignee_user_id,
            first_seen_scan_run_id=first_seen_scan_run_id,
            last_seen_scan_run_id=last_seen_scan_run_id,
        )
        self._session.add(record)
        await self._session.flush()
        return record

    async def get(self, finding_id: uuid.UUID) -> Optional[Finding]:
        return await self._session.scalar(sa.select(Finding).where(Finding.id == finding_id))

    async def get_by_fingerprint(
        self, *, project_id: uuid.UUID, fingerprint: str
    ) -> Optional[Finding]:
        return await self._session.scalar(
            sa.select(Finding).where(
                Finding.project_id == project_id, Finding.fingerprint == fingerprint
            )
        )

    async def get_live_as_of(
        self, *, project_id: uuid.UUID, scan_run_id: uuid.UUID
    ) -> Sequence[Finding]:
        """Findings this project's rescan diff (``backend.services.rescan_diff``)
        treats as "live" as of ``scan_run_id``: their fingerprint was last
        confirmed present by that exact scan run, AND their status isn't one
        that means "this fingerprint isn't actually a live issue any more"
        (``closed`` or ``false_positive`` - see the Task 3 brief's decision
        table for why ``accepted_risk`` is deliberately NOT excluded here:
        an accepted-risk finding that reappears in the very next scan is
        still "live" in the sense that touching its ``last_seen_scan_run_id``
        is harmless and expected, it just must never auto-transition)."""
        rows = await self._session.scalars(
            sa.select(Finding).where(
                Finding.project_id == project_id,
                Finding.last_seen_scan_run_id == scan_run_id,
                Finding.status.notin_(("closed", "false_positive")),
            )
        )
        return list(rows)

    async def list_for_project(
        self,
        *,
        project_id: uuid.UUID,
        status: Optional[str],
        severity: Optional[str],
        assignee_user_id: Optional[uuid.UUID],
        page: int,
        page_size: int,
    ) -> tuple[Sequence[Finding], int]:
        filters: list[Any] = [Finding.project_id == project_id]
        if status is not None:
            filters.append(Finding.status == status)
        if severity is not None:
            filters.append(Finding.severity == severity)
        if assignee_user_id is not None:
            filters.append(Finding.assignee_user_id == assignee_user_id)

        total = await self._session.scalar(
            sa.select(sa.func.count()).select_from(Finding).where(*filters)
        )
        rows = await self._session.scalars(
            sa.select(Finding)
            .where(*filters)
            .order_by(Finding.created_at.desc(), Finding.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(rows), int(total or 0)

    async def list_all_for_project_unpaginated(
        self,
        *,
        project_id: uuid.UUID,
        status: Optional[str],
        severity: Optional[str],
        assignee_user_id: Optional[uuid.UUID],
    ) -> Sequence[Finding]:
        """Every matching row, no pagination - used only by
        ``FindingService.list`` when an ``overdue`` filter is requested.

        ``is_overdue`` is a deliberately pure, no-DB Python function (see
        ``backend.services.sla``) rather than a stored/queryable column, so
        an ``overdue`` filter cannot be expressed as SQL WHERE clause here -
        it is applied by the caller after fetching the (status/severity/
        assignee-filtered) candidate set, which then re-paginates in Python.
        This is fine at this application's scale (no async job/queue,
        synchronous MVP scans per the plan) but would need a materialized/
        indexed approach if Finding volume ever grew large enough for this
        full-scan-then-filter approach to matter."""
        filters: list[Any] = [Finding.project_id == project_id]
        if status is not None:
            filters.append(Finding.status == status)
        if severity is not None:
            filters.append(Finding.severity == severity)
        if assignee_user_id is not None:
            filters.append(Finding.assignee_user_id == assignee_user_id)

        rows = await self._session.scalars(
            sa.select(Finding).where(*filters).order_by(Finding.created_at.desc(), Finding.id)
        )
        return list(rows)

    async def list_by_assignee(
        self,
        *,
        user_id: uuid.UUID,
        status: Optional[str],
        severity: Optional[str],
        overdue: Optional[bool],
        page: int,
        page_size: int,
    ) -> tuple[Sequence[tuple[Finding, str]], int]:
        """Findings assigned to ``user_id``, across every project, joined
        with their parent ``Project.name`` for the cross-project "My Tasks"
        view (Task 4) - authorization-safe by construction: the
        ``assignee_user_id == user_id`` filter means a caller can only ever
        see their own assignments regardless of their current project
        membership state, see the Task 4 brief.

        SQL-level filtered and paginated (Task 4 review fix - the original
        version fetched every assigned row across every project, unbounded,
        then filtered/paginated in Python; unlike
        ``list_all_for_project_unpaginated``, which is at least scoped to a
        single project, this query is scoped only to one user across the
        *entire app*, which does not scale for a long-tenured developer).
        ``deadline`` is a real stored column, so unlike
        ``list_all_for_project_unpaginated``'s ``overdue`` handling, this one
        expresses "overdue" as a genuine SQL predicate mirroring
        ``sla.is_overdue``'s exact definition: a non-null ``deadline`` in the
        past, on a Finding whose status isn't one of ``TERMINAL_STATUSES``.
        """
        filters: list[Any] = [Finding.assignee_user_id == user_id]
        if status is not None:
            filters.append(Finding.status == status)
        if severity is not None:
            filters.append(Finding.severity == severity)
        if overdue is not None:
            is_overdue_predicate = sa.and_(
                Finding.deadline.is_not(None),
                Finding.status.notin_(TERMINAL_STATUSES),
                Finding.deadline < datetime.now(timezone.utc),
            )
            filters.append(is_overdue_predicate if overdue else sa.not_(is_overdue_predicate))

        total = await self._session.scalar(
            sa.select(sa.func.count()).select_from(Finding).where(*filters)
        )
        rows = await self._session.execute(
            sa.select(Finding, Project.name)
            .join(Project, Project.id == Finding.project_id)
            .where(*filters)
            .order_by(Finding.created_at.desc(), Finding.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return [(row[0], row[1]) for row in rows.all()], int(total or 0)

    async def touch_last_seen(self, finding: Finding, *, scan_run_id: uuid.UUID) -> Finding:
        finding.last_seen_scan_run_id = scan_run_id
        await self._session.flush()
        return finding

    async def set_status(
        self,
        finding: Finding,
        *,
        status: str,
        closed_at: Optional[datetime] = None,
    ) -> Finding:
        finding.status = status
        if closed_at is not None:
            finding.closed_at = closed_at
        await self._session.flush()
        return finding

    async def set_assignee(self, finding: Finding, *, assignee_user_id: Optional[uuid.UUID]) -> Finding:
        finding.assignee_user_id = assignee_user_id
        await self._session.flush()
        return finding

    async def add_transition(
        self,
        *,
        finding_id: uuid.UUID,
        from_status: str,
        to_status: str,
        actor_user_id: uuid.UUID,
        reason: Optional[str],
        meta: Optional[dict[str, Any]] = None,
    ) -> FindingTransition:
        record = FindingTransition(
            finding_id=finding_id,
            from_status=from_status,
            to_status=to_status,
            actor_user_id=actor_user_id,
            reason=reason,
            meta=meta or {},
        )
        self._session.add(record)
        await self._session.flush()
        return record

    async def list_transitions(self, finding_id: uuid.UUID) -> Sequence[FindingTransition]:
        rows = await self._session.scalars(
            sa.select(FindingTransition)
            .where(FindingTransition.finding_id == finding_id)
            .order_by(FindingTransition.created_at.asc())
        )
        return list(rows)

    # -- Task 5: project security dashboard aggregations ------------------
    # Every method below is a real aggregate query over Finding/
    # FindingTransition for one project - no field on the dashboard is
    # computed from anything but these queries (see
    # backend.services.project_dashboard.ProjectDashboardService).

    async def count_open_by_severity(
        self, *, project_id: Optional[uuid.UUID] = None
    ) -> dict[str, int]:
        """Open-finding counts (status not in ``TERMINAL_STATUSES``, mirroring
        ``sla.TERMINAL_STATUSES``/the dashboard's "Open Findings" definition)
        grouped by severity in one query, rather than one query per severity.
        Always returns all four severities (0 for any with no open findings).

        ``project_id=None`` means "every project" (Task 7's admin summary
        aggregates across the whole app, not one project) - the caller is
        responsible for authorization; this repository has none of its own."""
        filters: list[Any] = [Finding.status.notin_(TERMINAL_STATUSES)]
        if project_id is not None:
            filters.append(Finding.project_id == project_id)
        rows = await self._session.execute(
            sa.select(Finding.severity, sa.func.count()).where(*filters).group_by(Finding.severity)
        )
        counts = {severity: 0 for severity in ("low", "medium", "high", "critical")}
        for severity, count in rows.all():
            counts[severity] = int(count)
        return counts

    async def count_open(self, *, project_id: Optional[uuid.UUID] = None) -> int:
        """Total open-finding count (status not in ``TERMINAL_STATUSES``) -
        a single-query convenience over ``count_open_by_severity`` for
        callers (e.g. the admin projects list) that only need the total, not
        the per-severity breakdown. ``project_id=None`` means every project."""
        filters: list[Any] = [Finding.status.notin_(TERMINAL_STATUSES)]
        if project_id is not None:
            filters.append(Finding.project_id == project_id)
        total = await self._session.scalar(
            sa.select(sa.func.count()).select_from(Finding).where(*filters)
        )
        return int(total or 0)

    async def count_by_status(self, *, project_id: Optional[uuid.UUID] = None, status: str) -> int:
        filters: list[Any] = [Finding.status == status]
        if project_id is not None:
            filters.append(Finding.project_id == project_id)
        total = await self._session.scalar(
            sa.select(sa.func.count()).select_from(Finding).where(*filters)
        )
        return int(total or 0)

    async def count_overdue(self, *, project_id: Optional[uuid.UUID] = None) -> int:
        """Mirrors the exact SQL overdue predicate ``list_by_assignee`` uses
        (Task 4 review fix) and ``sla.is_overdue``'s definition: a non-null
        ``deadline`` in the past, on a Finding whose status isn't terminal.
        ``project_id=None`` means every project (Task 7 admin summary)."""
        filters: list[Any] = [
            Finding.deadline.is_not(None),
            Finding.status.notin_(TERMINAL_STATUSES),
            Finding.deadline < datetime.now(timezone.utc),
        ]
        if project_id is not None:
            filters.append(Finding.project_id == project_id)
        total = await self._session.scalar(
            sa.select(sa.func.count()).select_from(Finding).where(*filters)
        )
        return int(total or 0)

    async def count_assigned_open(self, *, project_id: uuid.UUID) -> int:
        total = await self._session.scalar(
            sa.select(sa.func.count())
            .select_from(Finding)
            .where(
                Finding.project_id == project_id,
                Finding.assignee_user_id.is_not(None),
                Finding.status.notin_(TERMINAL_STATUSES),
            )
        )
        return int(total or 0)

    async def count_assigned_open_by_assignee(
        self, *, project_id: uuid.UUID
    ) -> dict[uuid.UUID, int]:
        rows = await self._session.execute(
            sa.select(Finding.assignee_user_id, sa.func.count())
            .where(
                Finding.project_id == project_id,
                Finding.assignee_user_id.is_not(None),
                Finding.status.notin_(TERMINAL_STATUSES),
            )
            .group_by(Finding.assignee_user_id)
        )
        return {assignee_id: int(count) for assignee_id, count in rows.all()}

    #: Severity rank used to order "top risks" critical-first - lower is
    #: more severe, matching FINDING_SEVERITIES' worst-to-best ordering.
    _SEVERITY_RANK = sa.case(
        (Finding.severity == "critical", 0),
        (Finding.severity == "high", 1),
        (Finding.severity == "medium", 2),
        (Finding.severity == "low", 3),
        else_=4,
    )

    async def list_top_risks(self, *, project_id: uuid.UUID, limit: int) -> Sequence[Finding]:
        """The ``limit`` open findings ordered critical-first, then
        most-overdue-first as a tiebreak within the same severity - an
        earlier (more overdue, or simply sooner) ``deadline`` sorts first,
        and findings with no deadline at all (never overdue) sort last, via
        ``NULLS LAST`` semantics on ascending deadline order."""
        rows = await self._session.scalars(
            sa.select(Finding)
            .where(
                Finding.project_id == project_id,
                Finding.status.notin_(TERMINAL_STATUSES),
            )
            .order_by(
                self._SEVERITY_RANK,
                sa.case((Finding.deadline.is_(None), 1), else_=0),
                Finding.deadline.asc(),
                Finding.created_at.desc(),
            )
            .limit(limit)
        )
        return list(rows)

    async def list_latest(self, *, project_id: uuid.UUID, limit: int) -> Sequence[Finding]:
        rows = await self._session.scalars(
            sa.select(Finding)
            .where(Finding.project_id == project_id)
            .order_by(Finding.created_at.desc(), Finding.id.desc())
            .limit(limit)
        )
        return list(rows)

    async def count_transitions_to_status_since(
        self, *, project_id: Optional[uuid.UUID] = None, to_status: str, since: datetime
    ) -> int:
        """Count of ``FindingTransition`` rows with ``to_status`` reached
        at/after ``since`` - drives the dashboard's "Fixed This Week" metric
        (see ``ProjectDashboardService`` for which ``to_status`` is used and
        why). ``project_id=None`` scopes across every project (Task 7 admin
        summary) instead of one."""
        filters: list[Any] = [
            FindingTransition.to_status == to_status,
            FindingTransition.created_at >= since,
        ]
        if project_id is not None:
            filters.append(Finding.project_id == project_id)
        total = await self._session.scalar(
            sa.select(sa.func.count())
            .select_from(FindingTransition)
            .join(Finding, Finding.id == FindingTransition.finding_id)
            .where(*filters)
        )
        return int(total or 0)

    # -- Task 8: AI Project Security Copilot tool-router support ----------
    # Both methods below are plain filtered selects over already-computed
    # Finding/status data - neither reimplements Task 3's fingerprint/diff
    # logic or Task 5's dashboard aggregation, per the Task 8 brief.

    async def list_by_cve_or_rule(
        self,
        *,
        project_id: uuid.UUID,
        cve_id: Optional[str] = None,
        rule_id: Optional[str] = None,
    ) -> Sequence[Finding]:
        """Findings in one project matching a given CVE id or rule_id, most
        recent first - the AI copilot's rescan-history handler (Task 8)
        reads this to answer "was this fixed?" / "did the previous scan
        have this?" purely from already-stored Finding state."""
        if not cve_id and not rule_id:
            return []
        filters: list[Any] = [Finding.project_id == project_id]
        if cve_id:
            filters.append(Finding.cve_id == cve_id)
        else:
            filters.append(Finding.rule_id == rule_id)
        rows = await self._session.scalars(
            sa.select(Finding).where(*filters).order_by(Finding.created_at.desc())
        )
        return list(rows)

    async def list_assigned_open(
        self, *, project_id: uuid.UUID, limit: int = 20
    ) -> Sequence[Finding]:
        """Open findings in a project that currently have an assignee,
        severity-first - the AI copilot's assignment handler (Task 8) needs
        actual rows, not just the per-assignee counts
        ``count_assigned_open_by_assignee`` returns."""
        rows = await self._session.scalars(
            sa.select(Finding)
            .where(
                Finding.project_id == project_id,
                Finding.assignee_user_id.is_not(None),
                Finding.status.notin_(TERMINAL_STATUSES),
            )
            .order_by(self._SEVERITY_RANK, Finding.created_at.desc())
            .limit(limit)
        )
        return list(rows)

    # -- Task 7: admin cross-project findings view -------------------------

    async def list_for_admin(
        self,
        *,
        project_id: Optional[uuid.UUID],
        status: Optional[str],
        severity: Optional[str],
        assignee_user_id: Optional[uuid.UUID],
        overdue: Optional[bool],
        fixed_since: Optional[datetime],
        page: int,
        page_size: int,
    ) -> tuple[Sequence[tuple[Finding, str]], int]:
        """Findings across every project (or one, if ``project_id`` is
        given), joined with their parent ``Project.name`` - the admin
        counterpart of ``list_by_assignee`` (Task 4), same SQL-level
        filtering/pagination/overdue-predicate approach, just scoped by
        project rather than by assignee. Admin-only: no membership filter,
        the caller (``backend.api.admin_lifecycle``, gated by
        ``require_admin``) is responsible for authorization.

        ``fixed_since`` filters on ``Finding.closed_at`` (the stored column
        set the moment a finding's status becomes ``closed`` - see
        ``FindingService.transition``) - the same status Task 5's dashboard
        "Fixed This Week" metric counts, so a caller combining
        ``status="closed"`` with ``fixed_since=<7 days ago>`` sees exactly
        the findings that metric counts, not just filters on it.
        """
        filters: list[Any] = []
        if project_id is not None:
            filters.append(Finding.project_id == project_id)
        if status is not None:
            filters.append(Finding.status == status)
        if severity is not None:
            filters.append(Finding.severity == severity)
        if assignee_user_id is not None:
            filters.append(Finding.assignee_user_id == assignee_user_id)
        if fixed_since is not None:
            filters.append(Finding.closed_at.is_not(None))
            filters.append(Finding.closed_at >= fixed_since)
        if overdue is not None:
            is_overdue_predicate = sa.and_(
                Finding.deadline.is_not(None),
                Finding.status.notin_(TERMINAL_STATUSES),
                Finding.deadline < datetime.now(timezone.utc),
            )
            filters.append(is_overdue_predicate if overdue else sa.not_(is_overdue_predicate))

        total = await self._session.scalar(
            sa.select(sa.func.count()).select_from(Finding).where(*filters)
        )
        rows = await self._session.execute(
            sa.select(Finding, Project.name)
            .join(Project, Project.id == Finding.project_id)
            .where(*filters)
            .order_by(Finding.created_at.desc(), Finding.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return [(row[0], row[1]) for row in rows.all()], int(total or 0)
