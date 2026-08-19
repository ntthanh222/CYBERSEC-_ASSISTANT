"""Rescan diff: classifies every finding produced by a scan against the
project's previous completed scan of the same target (Task 3).

Called from ``backend.services.scan_orchestrator.ScanOrchestrator.run_scan``
after it has computed this scan's raw findings and normalized-fingerprint
set, but before the scan run is marked ``completed`` - every write this
module makes joins the same not-yet-committed transaction as the rest of
that scan, so a diff and the Finding rows it touches always land together or
not at all (mirrors Task 2's existing all-or-nothing scan-write behavior).

Decision table (see ``backend/tests/test_rescan_diff.py`` for one scenario
test per row, and the Task 3 report for the full derivation against
``C:\\Users\\MSI\\.claude\\plans\\b-n-ang-l-m-vi-c-goofy-volcano.md`` section 3):

| Fingerprint in new scan? | In previous-live set? | Existing Finding status | Action | Diff label |
|---|---|---|---|---|
| yes | yes | any ("live" = not closed/false_positive) | update last_seen only | still_open |
| yes | no | (no Finding row exists at all) | create Finding(open) | new / new_regression |
| yes | no | fixed | auto-transition fixed->reopened | reopened_regression |
| yes | no | false_positive / accepted_risk | no change | regressed_but_dismissed |
| yes | no | closed | no change | regressed_after_close |
| yes | no | open/confirmed/in_progress/reopened | update last_seen only | still_open |
| no | yes | fixed | no change (awaiting manual verify) | fixed_pending_verify |
| no | yes | open/confirmed/in_progress/reopened (incl. accepted_risk, see note) | no change | absent_unconfirmed |

"new" vs "new_regression" is decided by whether THIS scan has a
``previous_scan_run_id`` at all (the project's very first scan for this
target -> "new"; every later scan -> "new_regression"), not by whether this
particular fingerprint specifically existed before - a fingerprint that is
brand new relative to the immediately preceding scan is a regression by
definition once any preceding scan exists.

Note on ``accepted_risk`` in the absence branch: the brief's decision table
(mirroring the plan text) only spells out "fixed" and the four
open-like statuses for "absent as of this scan, was live as of the previous
one". ``accepted_risk`` is not excluded from the "live" set by
``FindingRepository.get_live_as_of`` (only ``closed``/``false_positive``
are - see that method's docstring), so an ``accepted_risk`` finding *can*
reach this branch if its fingerprint was live at the previous scan and is
now absent. This module treats that case the same conservative way as the
open-like statuses (``absent_unconfirmed`` - no status change, flagged for
review) rather than inventing a new label: the plan is unambiguous that
``accepted_risk`` must never be auto-transitioned under any circumstances,
and "no change, flagged for review" is the only action here that is
correct for every status that can reach this branch.
"""
from __future__ import annotations

import uuid
from typing import Any, Optional, TypedDict

from sqlalchemy.ext.asyncio import AsyncSession

from backend.repositories.findings import FindingRepository
from backend.services.finding import FindingService

#: Every label ``apply()`` can produce, always present as a (possibly empty)
#: key in the returned dict so callers/tests never need a ``.get(..., [])``.
DIFF_LABELS: tuple[str, ...] = (
    "still_open",
    "new",
    "new_regression",
    "reopened_regression",
    "fixed_pending_verify",
    "absent_unconfirmed",
    "regressed_but_dismissed",
    "regressed_after_close",
)

#: A human explicitly judged these - never silently reopen them (the plan's
#: explicit prohibition; see the module docstring's decision table).
_DISMISSED_STATUSES = frozenset({"false_positive", "accepted_risk"})


class NewFindingInput(TypedDict):
    """One raw scan finding, already fingerprinted, in the shape
    ``FindingRepository.create`` expects."""

    fingerprint: str
    rule_id: str
    category: str
    title: str
    evidence: str
    impact: str
    remediation: str
    severity: str
    target: str


class RescanDiff:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._findings = FindingRepository(session)
        self._finding_service = FindingService(session)

    async def apply(
        self,
        *,
        project_id: uuid.UUID,
        this_run_id: uuid.UUID,
        previous_scan_run_id: Optional[uuid.UUID],
        actor_user_id: uuid.UUID,
        new_items: list[NewFindingInput],
    ) -> dict[str, list[str]]:
        diff: dict[str, list[str]] = {label: [] for label in DIFF_LABELS}

        previous_live: dict[str, Any] = {}
        if previous_scan_run_id is not None:
            rows = await self._findings.get_live_as_of(
                project_id=project_id, scan_run_id=previous_scan_run_id
            )
            previous_live = {row.fingerprint: row for row in rows}

        new_fingerprints = {item["fingerprint"] for item in new_items}

        for item in new_items:
            fingerprint = item["fingerprint"]

            if fingerprint in previous_live:
                finding = previous_live[fingerprint]
                await self._findings.touch_last_seen(finding, scan_run_id=this_run_id)
                diff["still_open"].append(str(finding.id))
                continue

            existing = await self._findings.get_by_fingerprint(
                project_id=project_id, fingerprint=fingerprint
            )
            if existing is None:
                created = await self._findings.create(
                    project_id=project_id,
                    scan_run_id=this_run_id,
                    fingerprint=fingerprint,
                    rule_id=item["rule_id"],
                    category=item["category"],
                    title=item["title"],
                    evidence=item["evidence"],
                    impact=item["impact"],
                    remediation=item["remediation"],
                    severity=item["severity"],
                    target=item["target"],
                    status="open",
                    first_seen_scan_run_id=this_run_id,
                    last_seen_scan_run_id=this_run_id,
                )
                label = "new_regression" if previous_scan_run_id is not None else "new"
                diff[label].append(str(created.id))
            elif existing.status == "fixed":
                reopened = await self._finding_service.auto_reopen_for_rescan(
                    existing, scan_run_id=this_run_id, actor_user_id=actor_user_id
                )
                await self._findings.touch_last_seen(reopened, scan_run_id=this_run_id)
                diff["reopened_regression"].append(str(reopened.id))
            elif existing.status in _DISMISSED_STATUSES:
                diff["regressed_but_dismissed"].append(str(existing.id))
            elif existing.status == "closed":
                diff["regressed_after_close"].append(str(existing.id))
            else:
                # open / confirmed / in_progress / reopened, reached via a
                # gap in scan cadence (this fingerprint's last_seen_scan_run_id
                # predates the immediately-preceding scan) rather than the
                # normal still-open path above.
                await self._findings.touch_last_seen(existing, scan_run_id=this_run_id)
                diff["still_open"].append(str(existing.id))

        if previous_scan_run_id is not None:
            for fingerprint, finding in previous_live.items():
                if fingerprint in new_fingerprints:
                    continue
                if finding.status == "fixed":
                    diff["fixed_pending_verify"].append(str(finding.id))
                else:
                    diff["absent_unconfirmed"].append(str(finding.id))

        return diff
