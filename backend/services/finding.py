"""Finding business logic: manual creation, assignee setting, and the
DB-persisted wrapper around ``finding_state_machine.validate_transition``.

``transition`` is the one place a Finding's ``status`` may change outside
the scan orchestrator's initial ``open`` insert - see the module docstring
on ``backend.services.finding_state_machine`` for the authorization rules it
enforces.
"""
from __future__ import annotations

import hashlib
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


def compute_fingerprint(*, project_id: uuid.UUID, rule_id: str, category: str, target: str) -> str:
    """Task 2's simplified fingerprint formula - see the ``Finding`` model
    docstring. Task 3 adds target normalization on top of this same shape
    without needing a schema change."""
    raw = f"{project_id}:{rule_id}:{category}:{target}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


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
    ):
        return await self._findings.list_for_project(
            project_id=project_id,
            status=status,
            severity=severity,
            assignee_user_id=assignee_user_id,
            page=page,
            page_size=page_size,
        )

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
