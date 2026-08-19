"""Scan orchestrator: runs a scan against a project's target and turns the
result into Finding rows.

Task 2 scope only: synchronous, single scanner (``url_scan``), no
fingerprint-based rescan diffing (Task 3 adds FIXED/STILL_OPEN/
NEW_REGRESSION classification on top of the ``previous_scan_run_id`` column
this task merely stores).

Category derivation: ``url_scanner.scan_url``'s findings only carry a flat
``code`` (e.g. ``"no_https"``, ``"credentials_in_url"``) with no separate
category field of their own. Rather than inventing an unfounded taxonomy,
this task reuses ``code`` as both ``rule_id`` and ``category`` - the
fingerprint formula (``project_id:rule_id:category:target``) still holds,
it just means category and rule_id currently carry the same value for
scanner-sourced findings. A manually-created Finding (``FindingService.
create_manual``) can set a distinct, meaningful category. Task 3 or a real
second scanner can refine this without a schema change.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.authorization import AppUser
from backend.database.models.finding import FINDING_SEVERITIES
from backend.database.models.scan import ScanRun
from backend.repositories.findings import FindingRepository
from backend.repositories.scan_runs import ScanRunRepository
from backend.services.finding import compute_fingerprint
from backend.services.url_scanner import scan_url

#: url_scanner findings use severities outside FINDING_SEVERITIES (see
#: url_scanner._severity_for's four buckets: low/medium/high/critical - the
#: same four values used here, so no mapping is actually needed today, but
#: this guards against a scanner-side change silently producing an invalid
#: Finding.severity).
_FALLBACK_SEVERITY = "low"


class ScanOrchestrator:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._scan_runs = ScanRunRepository(session)
        self._findings = FindingRepository(session)

    async def run_scan(
        self,
        *,
        project_id: uuid.UUID,
        target: str,
        actor: AppUser,
        previous_scan_run_id: Optional[uuid.UUID] = None,
    ) -> ScanRun:
        scan_run = await self._scan_runs.create(
            project_id=project_id,
            triggered_by_user_id=actor.id,
            scan_type="url_scan",
            target=target,
            status="running",
            started_at=datetime.now(timezone.utc),
            previous_scan_run_id=previous_scan_run_id,
        )
        # Committed on its own (step 1 of the brief) so the "running" row is
        # durable even if the process crashes mid-scan. Steps 2-3 below then
        # form their own atomic unit: either every Finding write from this
        # run commits together with the "completed" status, or none of them
        # do and the run is marked "failed" instead.
        await self._session.commit()

        try:
            result = await scan_url(target)
        except Exception as exc:  # noqa: BLE001 - any scan failure marks the run failed
            # Discards every partial Finding write from this run (they were
            # never committed) without touching the already-committed
            # "running" ScanRun row from step 1.
            await self._session.rollback()
            scan_run = await self._scan_runs.get(scan_run.id)
            if scan_run is None:
                # Cannot happen (step 1 committed it), but re-raise rather
                # than silently swallowing a missing row.
                raise
            await self._scan_runs.mark_failed(
                scan_run,
                completed_at=datetime.now(timezone.utc),
                summary={"error": str(exc)},
            )
            await self._session.commit()
            return scan_run

        severity_counts: dict[str, int] = {severity: 0 for severity in FINDING_SEVERITIES}
        for item in result.get("findings", []):
            code = item["code"]
            severity = item["severity"] if item["severity"] in FINDING_SEVERITIES else _FALLBACK_SEVERITY
            rule_id = code
            category = code
            fingerprint = compute_fingerprint(
                project_id=project_id, rule_id=rule_id, category=category, target=target
            )
            existing = await self._findings.get_by_fingerprint(
                project_id=project_id, fingerprint=fingerprint
            )
            if existing is None:
                await self._findings.create(
                    project_id=project_id,
                    scan_run_id=scan_run.id,
                    fingerprint=fingerprint,
                    rule_id=rule_id,
                    category=category,
                    title=item["message"],
                    evidence=item["message"],
                    impact="",
                    remediation="",
                    severity=severity,
                    target=target,
                    status="open",
                    first_seen_scan_run_id=scan_run.id,
                    last_seen_scan_run_id=scan_run.id,
                )
            else:
                await self._findings.touch_last_seen(existing, scan_run_id=scan_run.id)
            severity_counts[severity] += 1

        scan_run = await self._scan_runs.mark_completed(
            scan_run, completed_at=datetime.now(timezone.utc), summary=severity_counts
        )
        await self._session.commit()
        return scan_run
