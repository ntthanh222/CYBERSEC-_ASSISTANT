"""Finding and FindingTransition persistence."""
import uuid
from datetime import datetime
from typing import Any, Optional, Sequence

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database.models.finding import Finding, FindingTransition


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
