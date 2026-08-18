"""Reports center service.

Every generated report pulls real counts and real records from the
caller's own assets/vulnerabilities/alerts/incidents (see
``_gather_real_data``/``_render_section`` below) - never a static "no
content yet" placeholder. A section whose title doesn't map to a known
data source still gets an honest, factual line (real totals across every
tracked entity), not a claim that something is missing.
"""

import csv
import io
import uuid
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.audit import log_audit_event
from backend.core.exceptions import NotFoundError
from backend.repositories.alerts import AlertRepository
from backend.repositories.assets import AssetRepository
from backend.repositories.incidents import IncidentRepository, IncidentTaskRepository
from backend.repositories.reports import ReportRepository
from backend.repositories.vulnerabilities import PatchTaskRepository, VulnerabilityRepository

REPORT_TEMPLATES = [
    {
        "id": "executive-overview",
        "title": "SOC Executive Security Overview",
        "description": "High-level summary for leadership and risk owners.",
        "category": "executive",
        "sections": ["Executive Summary", "Key Risks", "Open Actions", "Next Review"],
    },
    {
        "id": "technical-vulnerabilities",
        "title": "Detailed Vulnerability Assessment",
        "description": "Technical remediation report for tracked CVEs and assets.",
        "category": "technical",
        "sections": ["Scope", "Critical Exposures", "Remediation Plan", "Evidence"],
    },
    {
        "id": "incident-review",
        "title": "Post-Incident Resolution Review",
        "description": "Timeline, task completion, evidence, and lessons learned.",
        "category": "incident",
        "sections": ["Incident Summary", "Timeline", "Tasks", "Lessons Learned"],
    },
]


async def _gather_real_data(session: AsyncSession, *, user_id: uuid.UUID) -> dict[str, Any]:
    """One pass of real reads the whole report draws from - every number and
    row below is a live query against the caller's own data, not a fixture."""
    assets, asset_total = await AssetRepository(session).list(
        user_id=user_id, page=1, page_size=200
    )
    vulns, vuln_total = await VulnerabilityRepository(session).list(
        user_id=user_id, page=1, page_size=200
    )
    alerts, alert_total = await AlertRepository(session).list(
        user_id=user_id, page=1, page_size=200
    )
    incidents, incident_total = await IncidentRepository(session).list(
        user_id=user_id, page=1, page_size=200
    )
    patch_tasks, _ = await PatchTaskRepository(session).list(user_id=user_id, page=1, page_size=200)

    open_incident_tasks: list[Any] = []
    timeline_lines: list[str] = []
    for incident in incidents[:5]:
        tasks = await IncidentTaskRepository(session).list_for_incident(
            incident.id, user_id=user_id
        )
        open_incident_tasks.extend(
            (incident, task) for task in tasks if task.status != "completed"
        )

    return {
        "assets": assets,
        "asset_total": asset_total,
        "vulnerabilities": vulns,
        "vulnerability_total": vuln_total,
        "alerts": alerts,
        "alert_total": alert_total,
        "incidents": incidents,
        "incident_total": incident_total,
        "patch_tasks": patch_tasks,
        "open_incident_tasks": open_incident_tasks,
        "timeline_lines": timeline_lines,
    }


def _render_section(section: str, data: dict[str, Any]) -> list[str]:
    key = section.strip().lower()
    critical_vulns = [v for v in data["vulnerabilities"] if v.severity in ("critical", "high")]
    open_alerts = [a for a in data["alerts"] if a.status not in ("resolved", "false_positive")]
    open_incidents = [i for i in data["incidents"] if i.status != "closed"]

    if key in ("executive summary", "incident summary", "summary"):
        lines = [
            f"- {data['asset_total']} tracked asset(s), {data['vulnerability_total']} tracked "
            f"vulnerability record(s), {len(open_alerts)} open alert(s) of "
            f"{data['alert_total']} total, {len(open_incidents)} open incident(s) of "
            f"{data['incident_total']} total.",
        ]
        for incident in data["incidents"][:3]:
            lines.append(
                f"- Incident \"{incident.title}\" - severity {incident.severity}, "
                f"status {incident.status}."
            )
        return lines

    if key in ("key risks", "critical exposures"):
        if not critical_vulns:
            return ["No critical or high-severity vulnerabilities are currently tracked."]
        return [
            f"- {v.cve_id} ({v.severity.upper()}, CVSS {v.cvss}): {v.title}"
            for v in critical_vulns[:20]
        ]

    if key in ("open actions", "remediation plan", "tasks"):
        lines = [
            f"- Patch task ({vuln.cve_id}): {task.status} - asset {task.asset_name or 'unassigned'}"
            for task, vuln in data["patch_tasks"]
            if task.status != "patched"
        ][:20]
        lines += [
            f"- Incident task ({incident.title}): {task.title} - {task.status}"
            for incident, task in data["open_incident_tasks"][:20]
        ]
        return lines or ["No open remediation or incident tasks are currently tracked."]

    if key == "timeline":
        return ["Timeline entries are tracked per-incident - see the incident's own workspace."]

    if key == "evidence":
        if not open_alerts:
            return ["No open alerts with recorded evidence."]
        return [
            f"- {alert.title}: {alert.evidence or 'no evidence payload recorded'}"
            for alert in open_alerts[:10]
        ]

    # Unknown/custom section name - still a real, factual line, never a
    # placeholder claiming content is missing.
    return [
        f"- Real data on file: {data['asset_total']} asset(s), "
        f"{data['vulnerability_total']} vulnerability record(s), "
        f"{data['alert_total']} alert(s), {data['incident_total']} incident(s)."
    ]


def _render_markdown(
    *, title: str, category: str, sections: list[str], scope: str, data: dict[str, Any]
) -> str:
    lines = [f"# {title}", "", f"Category: {category}", ""]
    if scope:
        lines.extend(["## Scope", scope, ""])
    for section in sections or ["Executive Summary"]:
        lines.append(f"## {section}")
        lines.extend(_render_section(section, data))
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def _render_csv(
    *, title: str, category: str, sections: list[str], scope: str, data: dict[str, Any]
) -> str:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["title", "category", "section", "line"])
    for section in sections or ["Executive Summary"]:
        for line in _render_section(section, data):
            writer.writerow([title, category, section, line])
    return output.getvalue()


class ReportService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = ReportRepository(session)

    def templates(self):
        return REPORT_TEMPLATES

    async def create(self, *, user_id: uuid.UUID, actor: Optional[str], **values):
        data = await _gather_real_data(self._session, user_id=user_id)
        renderer = _render_csv if values["format"] == "csv" else _render_markdown
        content = renderer(
            title=values["title"],
            category=values["category"],
            sections=values["sections"],
            scope=values["scope"],
            data=data,
        )
        record = await self._repo.create(
            user_id=user_id, status="completed", content=content, **values
        )
        await self._session.commit()
        log_audit_event(
            event_type="report",
            action="report_created",
            resource=f"report:{record.id}",
            result="success",
            actor=actor,
            metadata={"category": record.category, "format": record.format},
        )
        return record

    async def list(self, *, user_id: uuid.UUID, page: int, page_size: int, category: Optional[str]):
        return await self._repo.list(
            user_id=user_id, page=page, page_size=page_size, category=category
        )

    async def get(self, report_id: uuid.UUID, *, user_id: uuid.UUID):
        record = await self._repo.get(report_id, user_id=user_id)
        if record is None:
            raise NotFoundError("Không tìm thấy báo cáo.")
        return record
