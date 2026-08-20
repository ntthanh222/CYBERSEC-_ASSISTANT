"""Project-aware CVE risk-prioritization orchestration (Task 6).

``ProjectCveService.assess_cve`` is the one place that ties together:

1. The EXISTING, unmodified ``CveLookupService.get()`` (NVD-backed CVSS +
   description) - called into, never altered.
2. The new ``EpssProvider``/``KevProvider`` enrichment data.
3. The calling project's own risk context (``criticality``,
   ``internet_facing``).
4. The deterministic, pure ``cve_priority.assess()`` scoring engine.
5. Persistence (upsert into ``cve_assessments``) and, for the two most
   urgent labels, an auto-created/linked ``Finding``.

No network/DB call happens inside ``cve_priority.assess()`` itself - all the
I/O here is gathering its inputs and persisting its output.
"""
from __future__ import annotations

import uuid
from typing import Optional

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.audit import log_audit_event
from backend.core.authorization import AppUser
from backend.core.exceptions import NotFoundError
from backend.database.models.cve_assessment import CveAssessment
from backend.database.models.finding import Finding
from backend.database.models.project import Project
from backend.providers.enrichment.registry import get_epss_provider, get_kev_provider
from backend.repositories.cve_assessments import CveAssessmentRepository
from backend.services import cve_priority
from backend.services.cve import CveLookupService
from backend.services.finding import FindingService

#: priority labels that warrant auto-creating/linking a Finding, per the
#: brief's step 8 ("optionally auto-create/link Finding").
_AUTO_FINDING_PRIORITIES = ("patch_now", "high")

#: Finding.severity derived from the assessed priority label - only the two
#: labels in _AUTO_FINDING_PRIORITIES ever reach this mapping.
#: "patch_now" (known-exploited-worst-case/CVSS-critical) maps to Finding's
#: own "critical" severity; "high" maps 1:1 to Finding's "high". This is a
#: judgement call documented here since Finding and CVE-priority use two
#: different label vocabularies with no canonical mapping in the codebase.
_PRIORITY_TO_FINDING_SEVERITY = {
    "patch_now": "critical",
    "high": "high",
}


class ProjectCveService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._assessments = CveAssessmentRepository(session)
        self._cve_lookup = CveLookupService()
        self._epss = get_epss_provider()
        self._kev = get_kev_provider()

    async def _get_project(self, project_id: uuid.UUID) -> Project:
        project = await self._session.get(Project, project_id)
        if project is None:
            raise NotFoundError("Project not found.")
        return project

    @staticmethod
    def _affected_version_matches(
        affected_version: Optional[str], affected_products: list[str]
    ) -> Optional[bool]:
        """Best-effort "is the project's installed version actually in the
        vulnerable range?" check.

        Deliberately conservative: this does **not** parse CPE version
        ranges (NVD's ``configurations``/``cpeMatch`` data is complex -
        version ranges, "vulnerable" vs "running on" applicability,
        exact-vs-range matches - and the existing extraction in
        ``backend/providers/cve/nvd.py::_extract_products`` already caps
        what it returns at 20 raw CPE strings with no range metadata at
        all). Building a fragile parser against that reduced data would be
        worse than admitting uncertainty, per the brief's explicit
        instruction to fall back to "unknown" rather than that.

        So this only ever returns ``True`` (the supplied version string
        appears verbatim in at least one of the CVE's known affected-product
        CPE strings - a real, if narrow, positive signal) or ``None``
        (either no ``affected_version`` was supplied, there is no affected-
        product data to check against, or the version string simply was not
        found in the - possibly incomplete/capped - list). It never returns
        ``False``: the absence of a version string from a capped, range-free
        CPE list is not evidence the project is NOT affected, only that this
        simple check could not confirm that it IS.
        """
        if not affected_version:
            return None
        if not affected_products:
            return None
        needle = affected_version.strip().lower()
        if not needle:
            return None
        for product in affected_products:
            if needle in product.lower():
                return True
        return None

    async def assess_cve(
        self,
        *,
        project_id: uuid.UUID,
        cve_id: str,
        affected_version: Optional[str],
        actor: AppUser,
        actor_label: Optional[str],
    ) -> CveAssessment:
        project = await self._get_project(project_id)

        cve_record = await self._cve_lookup.get(cve_id, actor=actor_label)
        normalized_cve_id = cve_record["cve_id"]
        cvss_score = cve_record.get("cvss_score")
        affected_products = list(cve_record.get("affected_products") or [])

        epss_result = await self._epss.get(normalized_cve_id)
        epss_score = epss_result.score if epss_result is not None else None

        is_kev = await self._kev.is_kev(normalized_cve_id)

        affected_version_matches = self._affected_version_matches(
            affected_version, affected_products
        )

        # Best-effort "fixed_version"/"technology" enrichment: match the
        # supplied affected_version's technology entry against the
        # project's declared technologies list (if any), purely for display
        # - this is not part of the scoring inputs.
        technology_name: Optional[str] = None
        for tech in project.technologies or []:
            if isinstance(tech, dict) and tech.get("version") == affected_version:
                technology_name = tech.get("name")
                break

        priority, score, rationale = cve_priority.assess(
            cvss_score,
            epss_score,
            is_kev,
            project.internet_facing,
            project.criticality,
            affected_version_matches,
        )

        finding_id: Optional[uuid.UUID] = None
        if priority in _AUTO_FINDING_PRIORITIES:
            finding_id = await self._auto_link_or_create_finding(
                project_id=project_id,
                cve_id=normalized_cve_id,
                priority=priority,
                cve_record=cve_record,
                rationale=rationale,
                actor=actor,
                actor_label=actor_label,
            )

        assessment = await self._assessments.upsert(
            project_id=project_id,
            cve_id=normalized_cve_id,
            cvss_score=cvss_score,
            epss_score=epss_score,
            is_kev=is_kev,
            affected_version=affected_version,
            fixed_version=None,
            technology=technology_name,
            priority=priority,
            score=score,
            rationale=rationale,
            finding_id=finding_id,
        )
        await self._session.commit()

        log_audit_event(
            event_type="cve_priority",
            action="cve_assessed",
            resource=f"cve_assessment:{assessment.id}",
            result="success",
            actor=actor_label,
            metadata={
                "project_id": str(project_id),
                "cve_id": normalized_cve_id,
                "priority": priority,
                "score": score,
            },
        )
        return assessment

    async def _auto_link_or_create_finding(
        self,
        *,
        project_id: uuid.UUID,
        cve_id: str,
        priority: str,
        cve_record: dict,
        rationale: dict,
        actor: AppUser,
        actor_label: Optional[str],
    ) -> uuid.UUID:
        """Links to an already-existing Finding referencing this CVE in this
        project if one exists, else creates one via
        ``FindingService.create_manual`` (the same manual-creation path a
        human uses, so this Finding is indistinguishable in shape from a
        human-created one - it just has no ``scan_run_id``, same as any
        other manually-created Finding)."""
        existing = await self._session.scalar(
            sa.select(Finding).where(
                Finding.project_id == project_id, Finding.cve_id == cve_id
            )
        )
        if existing is not None:
            return existing.id

        severity = _PRIORITY_TO_FINDING_SEVERITY[priority]
        description = cve_record.get("description") or ""
        finding = await FindingService(self._session).create_manual(
            project_id=project_id,
            rule_id=f"cve:{cve_id}",
            category="cve",
            title=f"CVE {cve_id} — {priority}",
            evidence=description[:2000],
            impact=rationale.get("reasoning", ""),
            remediation=(
                "Review the CVE assessment rationale and apply the vendor patch/upgrade "
                f"for the affected component (see {cve_id} advisory)."
            ),
            severity=severity,
            target=cve_id,
            cve_id=cve_id,
            assignee_user_id=None,
            actor=actor,
            actor_label=actor_label,
        )
        return finding.id

    async def list_for_project(self, project_id: uuid.UUID) -> list[CveAssessment]:
        return list(await self._assessments.list_for_project(project_id=project_id))

    async def get_for_project(self, project_id: uuid.UUID, cve_id: str) -> CveAssessment:
        record = await self._assessments.get_by_project_and_cve(
            project_id=project_id, cve_id=cve_id.strip().upper()
        )
        if record is None:
            raise NotFoundError("No CVE assessment found for this project/CVE.")
        return record
