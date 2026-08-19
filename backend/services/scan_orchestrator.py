"""Scan orchestrator: runs a scan against a project's target and turns the
result into Finding rows.

Task 3 adds fingerprint-based rescan diffing on top of Task 2's simple
"does a Finding with this fingerprint exist? touch it if so, create it if
not" logic: ``previous_scan_run_id`` is now auto-detected (the most recent
``completed`` scan of the same project+target - see
``backend.repositories.scan_runs.ScanRunRepository.get_latest_completed``)
and every finding this scan produces is classified (STILL_OPEN/NEW/
NEW_REGRESSION/REOPENED_REGRESSION/...) by
``backend.services.rescan_diff.RescanDiff``, which also performs the one
legitimate automatic state transition (``fixed`` -> ``reopened``).

Category derivation: ``url_scanner.scan_url``'s findings only carry a flat
``code`` (e.g. ``"no_https"``, ``"credentials_in_url"``) with no separate
category field of their own. Rather than inventing an unfounded taxonomy,
this task reuses ``code`` as both ``rule_id`` and ``category`` - the
fingerprint formula (``project_id:rule_id:category:target``) still holds,
it just means category and rule_id currently carry the same value for
scanner-sourced findings. A manually-created Finding (``FindingService.
create_manual``) can set a distinct, meaningful category.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.authorization import AppUser
from backend.database.models.finding import FINDING_SEVERITIES
from backend.database.models.scan import ScanRun
from backend.repositories.scan_runs import ScanRunRepository
from backend.services.finding_fingerprint import compute_fingerprint
from backend.services.rescan_diff import NewFindingInput, RescanDiff
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

    async def run_scan(
        self,
        *,
        project_id: uuid.UUID,
        target: str,
        actor: AppUser,
        previous_scan_run_id: Optional[uuid.UUID] = None,
    ) -> ScanRun:
        # Auto-chaining (Task 3 brief §2): a caller-supplied
        # previous_scan_run_id always wins (explicit override), but the
        # default - and the only thing the frontend needs to do to trigger
        # a rescan - is to just POST the same target again. Chosen over
        # requiring the caller to track scan IDs because that is strictly
        # more work for zero benefit in the only flow this API actually
        # supports today (one target, rescanned over time).
        if previous_scan_run_id is None:
            latest = await self._scan_runs.get_latest_completed(
                project_id=project_id, target=target
            )
            if latest is not None:
                previous_scan_run_id = latest.id

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
        new_items: list[NewFindingInput] = []
        for item in result.get("findings", []):
            code = item["code"]
            severity = item["severity"] if item["severity"] in FINDING_SEVERITIES else _FALLBACK_SEVERITY
            rule_id = code
            category = code
            fingerprint = compute_fingerprint(
                project_id=project_id, rule_id=rule_id, category=category, target=target
            )
            new_items.append(
                {
                    "fingerprint": fingerprint,
                    "rule_id": rule_id,
                    "category": category,
                    "title": item["message"],
                    "evidence": item["message"],
                    "impact": "",
                    "remediation": "",
                    "severity": severity,
                    "target": target,
                }
            )
            severity_counts[severity] += 1

        diff = await RescanDiff(self._session).apply(
            project_id=project_id,
            this_run_id=scan_run.id,
            previous_scan_run_id=previous_scan_run_id,
            actor_user_id=actor.id,
            new_items=new_items,
        )

        summary: dict = {
            **severity_counts,
            "diff": diff,
            "diff_counts": {label: len(ids) for label, ids in diff.items()},
        }
        scan_run = await self._scan_runs.mark_completed(
            scan_run, completed_at=datetime.now(timezone.utc), summary=summary
        )
        await self._session.commit()
        return scan_run
