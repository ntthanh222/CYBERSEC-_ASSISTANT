"""CveAssessment persistence (Task 6)."""
import uuid
from typing import Any, Optional, Sequence

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database.models.cve_assessment import CveAssessment


class CveAssessmentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, assessment_id: uuid.UUID) -> Optional[CveAssessment]:
        return await self._session.get(CveAssessment, assessment_id)

    async def get_by_project_and_cve(
        self, *, project_id: uuid.UUID, cve_id: str
    ) -> Optional[CveAssessment]:
        return await self._session.scalar(
            sa.select(CveAssessment).where(
                CveAssessment.project_id == project_id, CveAssessment.cve_id == cve_id
            )
        )

    async def list_for_project(self, *, project_id: uuid.UUID) -> Sequence[CveAssessment]:
        rows = await self._session.scalars(
            sa.select(CveAssessment)
            .where(CveAssessment.project_id == project_id)
            .order_by(CveAssessment.score.desc(), CveAssessment.updated_at.desc())
        )
        return list(rows)

    async def upsert(
        self,
        *,
        project_id: uuid.UUID,
        cve_id: str,
        cvss_score: Optional[float],
        epss_score: Optional[float],
        is_kev: bool,
        affected_version: Optional[str],
        fixed_version: Optional[str],
        technology: Optional[str],
        priority: str,
        score: float,
        rationale: dict[str, Any],
        finding_id: Optional[uuid.UUID],
    ) -> CveAssessment:
        record = await self.get_by_project_and_cve(project_id=project_id, cve_id=cve_id)
        if record is None:
            record = CveAssessment(project_id=project_id, cve_id=cve_id)
            self._session.add(record)

        record.cvss_score = cvss_score
        record.epss_score = epss_score
        record.is_kev = is_kev
        record.affected_version = affected_version
        record.fixed_version = fixed_version
        record.technology = technology
        record.priority = priority
        record.score = score
        record.rationale = rationale
        if finding_id is not None:
            record.finding_id = finding_id

        await self._session.flush()
        return record
