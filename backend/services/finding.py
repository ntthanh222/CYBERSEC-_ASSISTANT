"""Finding business logic: manual creation, assignee setting, and the
DB-persisted wrapper around ``finding_state_machine.validate_transition``.

``transition`` is the one place a Finding's ``status`` may change outside
the scan orchestrator's initial ``open`` insert - see the module docstring
on ``backend.services.finding_state_machine`` for the authorization rules it
enforces.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.audit import log_audit_event
from backend.core.authorization import AppUser
from backend.core.exceptions import (
    ForbiddenTransitionError as ApiForbiddenTransitionError,
    InvalidRequestError,
    InvalidTransitionError as ApiInvalidTransitionError,
    NotFoundError,
    ReasonRequiredError as ApiReasonRequiredError,
)
from backend.database.models.finding import FINDING_SEVERITIES, Finding
from backend.database.models.rbac import ADMIN_TIER_ROLES
from backend.repositories.findings import FindingRepository
from backend.repositories.project_members import ProjectMemberRepository
from backend.repositories.rbac import RbacRepository
from backend.services import finding_state_machine as fsm
from backend.services import sla as sla_service
from backend.services.finding_fingerprint import compute_fingerprint

__all__ = ["compute_fingerprint", "FindingService"]


class FindingService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._findings = FindingRepository(session)
        self._members = ProjectMemberRepository(session)
        self._rbac = RbacRepository(session)

    async def get(self, finding_id: uuid.UUID, *, project_id: Optional[uuid.UUID] = None) -> Finding:
        record = await self._findings.get(finding_id)
        if record is None or (project_id is not None and record.project_id != project_id):
            raise NotFoundError("Finding not found.")
        return record

    async def list(
        self,
        *,
        project_id: uuid.UUID,
        status: Optional[str],
        severity: Optional[str],
        assignee_user_id: Optional[uuid.UUID],
        page: int,
        page_size: int,
        overdue: Optional[bool] = None,
    ):
        if overdue is None:
            return await self._findings.list_for_project(
                project_id=project_id,
                status=status,
                severity=severity,
                assignee_user_id=assignee_user_id,
                page=page,
                page_size=page_size,
            )

        # `overdue` has no SQL representation (see
        # FindingRepository.list_all_for_project_unpaginated's docstring) -
        # fetch every status/severity/assignee-matching row, filter by the
        # pure-Python sla.is_overdue, then paginate the filtered set here.
        candidates = await self._findings.list_all_for_project_unpaginated(
            project_id=project_id,
            status=status,
            severity=severity,
            assignee_user_id=assignee_user_id,
        )
        matched = [item for item in candidates if sla_service.is_overdue(item) == overdue]
        total = len(matched)
        start = (page - 1) * page_size
        return matched[start : start + page_size], total

    async def create_manual(
        self,
        *,
        project_id: uuid.UUID,
        rule_id: str,
        category: str,
        title: str,
        evidence: str,
        impact: str,
        remediation: str,
        severity: str,
        target: str,
        cve_id: Optional[str],
        assignee_user_id: Optional[uuid.UUID],
        actor: AppUser,
        actor_label: Optional[str],
    ) -> Finding:
        if severity not in FINDING_SEVERITIES:
            raise InvalidRequestError(f"severity must be one of {sorted(FINDING_SEVERITIES)}.")

        fingerprint = compute_fingerprint(
            project_id=project_id, rule_id=rule_id, category=category, target=target
        )
        record = await self._findings.create(
            project_id=project_id,
            scan_run_id=None,
            fingerprint=fingerprint,
            rule_id=rule_id,
            category=category,
            title=title,
            evidence=evidence,
            impact=impact,
            remediation=remediation,
            severity=severity,
            target=target,
            cve_id=cve_id,
            assignee_user_id=assignee_user_id,
            status="open",
        )
        await self._session.commit()
        log_audit_event(
            event_type="finding",
            action="finding_created_manual",
            resource=f"finding:{record.id}",
            result="success",
            actor=actor_label,
            metadata={"project_id": str(project_id), "rule_id": rule_id},
        )
        return record

    async def set_assignee(
        self,
        finding_id: uuid.UUID,
        *,
        project_id: uuid.UUID,
        assignee_user_id: Optional[uuid.UUID],
        actor: AppUser,
        actor_label: Optional[str],
    ) -> Finding:
        """Bare setter - Task 2 scope only. No validation that
        ``assignee_user_id`` is actually a project developer member; Task 4
        adds the real assign endpoint with that validation. Callable only by
        route-level owner/security-or-admin (enforced by
        ``require_project_role`` on the route, not re-checked here)."""
        finding = await self.get(finding_id, project_id=project_id)
        finding = await self._findings.set_assignee(finding, assignee_user_id=assignee_user_id)
        await self._session.commit()
        log_audit_event(
            event_type="finding",
            action="finding_assignee_set",
            resource=f"finding:{finding.id}",
            result="success",
            actor=actor_label,
            metadata={"assignee_user_id": str(assignee_user_id) if assignee_user_id else None},
        )
        return finding

    async def transition(
        self,
        finding_id: uuid.UUID,
        *,
        project_id: uuid.UUID,
        to_status: str,
        reason: Optional[str],
        actor: AppUser,
        actor_label: Optional[str],
    ) -> Finding:
        finding = await self.get(finding_id, project_id=project_id)

        member = await self._members.get(project_id=finding.project_id, user_id=actor.id)
        actor_project_role = member.project_role if member is not None else None
        is_assignee = finding.assignee_user_id is not None and finding.assignee_user_id == actor.id
        from_status = finding.status

        try:
            fsm.validate_transition(
                from_status,
                to_status,
                actor_project_role,
                actor.role,
                is_assignee,
                reason,
            )
        except fsm.ReasonRequiredError as exc:
            raise ApiReasonRequiredError(str(exc)) from exc
        except fsm.ForbiddenTransitionError as exc:
            raise ApiForbiddenTransitionError(str(exc)) from exc
        except fsm.InvalidTransitionError as exc:
            raise ApiInvalidTransitionError(str(exc)) from exc

        closed_at = datetime.now(timezone.utc) if to_status == "closed" else None
        finding = await self._findings.set_status(finding, status=to_status, closed_at=closed_at)
        if to_status in ("false_positive", "accepted_risk"):
            # The only statuses the state machine requires a reason for -
            # resolution_reason records *why* the finding was dismissed, not
            # every transition's incidental reason text.
            finding.resolution_reason = reason
        if to_status == "confirmed":
            # The ONLY place Finding.deadline is ever set (Task 3 SLA
            # service) - "deadline được set khi open->confirmed" in the
            # plan. A finding can re-enter confirmed from reopened too
            # (reopened->confirmed is a valid edge); each entry into
            # confirmed recomputes and restarts the SLA clock rather than
            # only doing so the first time.
            confirmed_at = datetime.now(timezone.utc)
            finding.deadline = await sla_service.compute_deadline(
                project_id=finding.project_id,
                severity=finding.severity,
                confirmed_at=confirmed_at,
                session=self._session,
            )
        await self._findings.add_transition(
            finding_id=finding.id,
            from_status=from_status,
            to_status=to_status,
            actor_user_id=actor.id,
            reason=reason,
        )

        if actor.role in ADMIN_TIER_ROLES:
            await self._rbac.record_audit(
                actor_user_id=actor.id,
                action="finding_transition",
                target_user_id=None,
                metadata={
                    "finding_id": str(finding.id),
                    "from_status": from_status,
                    "to_status": to_status,
                },
            )

        await self._session.commit()
        log_audit_event(
            event_type="finding",
            action="finding_transition",
            resource=f"finding:{finding.id}",
            result="success",
            actor=actor_label,
            metadata={"from_status": from_status, "to_status": to_status},
        )
        return finding

    async def auto_reopen_for_rescan(
        self,
        finding: Finding,
        *,
        scan_run_id: uuid.UUID,
        actor_user_id: uuid.UUID,
    ) -> Finding:
        """The one automatic, system-triggered transition in the whole
        Finding lifecycle: ``fixed`` -> ``reopened`` when a rescan's diff
        (``backend.services.rescan_diff``) finds a ``fixed`` Finding's
        fingerprint has reappeared. See the Task 3 brief's "System actor"
        note: there is no separate "system" identity in this codebase, so
        the scan-triggering user (``ScanRun.triggered_by_user_id``) is
        recorded as the ``FindingTransition.actor_user_id`` - the most
        honest available audit trail for an automatic transition.

        Deliberately does **not** call ``finding_state_machine.validate_transition``
        - that function's role checks answer "may THIS HUMAN perform this
        transition?", a question that does not apply here (nobody is acting,
        the rescan diff is). It still re-checks the edge itself is real via
        ``ALLOWED_TRANSITIONS`` (defense in depth against a future caller
        error) and writes the exact same ``FindingTransition`` row + audit
        log entry a human-initiated transition would, so the audit trail is
        indistinguishable in shape from any other transition - only its
        ``reason`` ("rescan_regression") and the caller-supplied ``meta``
        reveal it was automatic.

        Does not commit - the caller (``RescanDiff``, invoked from
        ``ScanOrchestrator.run_scan``) commits once at the end of the whole
        scan, same as every other write in that transaction.
        """
        from_status = finding.status
        to_status = "reopened"
        if to_status not in fsm.ALLOWED_TRANSITIONS.get(from_status, frozenset()):
            raise InvalidRequestError(
                f"auto_reopen_for_rescan called on an invalid edge "
                f"'{from_status}' -> '{to_status}'."
            )

        finding = await self._findings.set_status(finding, status=to_status)
        await self._findings.add_transition(
            finding_id=finding.id,
            from_status=from_status,
            to_status=to_status,
            actor_user_id=actor_user_id,
            reason="rescan_regression",
            meta={"scan_run_id": str(scan_run_id), "diff_label": "reopened_regression"},
        )
        log_audit_event(
            event_type="finding",
            action="finding_transition",
            resource=f"finding:{finding.id}",
            result="success",
            actor="system:rescan_diff",
            metadata={
                "from_status": from_status,
                "to_status": to_status,
                "scan_run_id": str(scan_run_id),
                "reason": "rescan_regression",
            },
        )
        return finding
