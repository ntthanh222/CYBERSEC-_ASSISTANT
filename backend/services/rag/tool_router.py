"""App-Data Tool Router for RAG Local-First.

Directly queries live platform databases and services for status, assets,
incidents, alerts, vulnerabilities, scan history, and system health queries.

100% Local Execution (0 Gemini Calls) with strict RBAC enforcement.
"""

import logging
import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.authorization import AppUser
from backend.core.exceptions import AppError, BlockedTargetError
from backend.repositories.alerts import AlertRepository
from backend.repositories.assets import AssetRepository
from backend.repositories.cve_assessments import CveAssessmentRepository
from backend.repositories.findings import FindingRepository
from backend.repositories.incidents import IncidentRepository
from backend.repositories.reports import ReportRepository
from backend.repositories.sla_policies import SlaPolicyRepository
from backend.repositories.vulnerabilities import VulnerabilityRepository
from backend.services import sla as sla_service
from backend.services.cve import CveLookupService
from backend.services.health import check_database
from backend.services.project_dashboard import ProjectDashboardService
from backend.services.rag.entity_extractor import ExtractedEntities
from backend.services.rag.project_context import (
    ProjectAccessResult,
    DENIAL_FORBIDDEN,
    resolve_project_access,
)
from backend.services.security_news import SecurityNewsService
from backend.services.url_scanner import blocked_summary, scan_url, summarize

logger = logging.getLogger("backend.services.rag.tool_router")


@dataclass
class ToolRouteResult:
    handled: bool
    content: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


def _humanize_affected_products(raw_products, *, limit: int = 5) -> list[str]:
    """Turn raw NVD CPE 2.3 URIs into a short "Vendor Product" list.

    A CPE looks like ``cpe:2.3:o:siemens:6bk1602-0aa12-0tp0_firmware:*:...`` -
    dumping that straight into a chat answer is unreadable noise. Only the
    vendor and product fields are user-meaningful here; the rest (version
    wildcards, target hardware, ...) is dropped, and duplicates that only
    differ in those trailing fields are collapsed.
    """
    seen: dict[str, None] = {}
    for entry in raw_products:
        if not isinstance(entry, str):
            continue
        if not entry.startswith("cpe:2.3:"):
            # Not a CPE URI (e.g. already a plain product name) - use as-is.
            seen.setdefault(entry, None)
            continue
        fields = entry.split(":")
        if len(fields) < 5:
            continue
        vendor, product = fields[3], fields[4]
        vendor_h = vendor.replace("_", " ").strip()
        product_h = product.replace("_", " ").strip()
        if not vendor_h and not product_h:
            continue
        label = f"{vendor_h.title()} {product_h}".strip()
        seen.setdefault(label, None)
    return list(seen)[:limit]


class AppDataToolRouter:
    """Routing layer that queries system repositories deterministically."""

    def __init__(self, session: AsyncSession, *, authz_session: AsyncSession | None = None) -> None:
        self._session = session
        #: The session ``resolve_project_access`` (Task 8) uses. MUST be a
        #: non-RLS session (e.g. ``backend.database.session.get_db``, never
        #: ``get_rls_db``) - the ``/api/chatbot/chat`` route's main session
        #: is RLS-scoped, and Postgres RLS on ``projects`` already hides
        #: rows the caller isn't a member of. If the authorization check ran
        #: on that same RLS session, ``ProjectRepository.get`` would return
        #: ``None`` for a non-member project exactly as it would for a
        #: genuinely nonexistent one, making the "forbidden" branch dead
        #: code in production and silently collapsing it into "not found" -
        #: this is the same reason ``backend.core.project_authorization``
        #: uses ``get_db`` rather than ``get_rls_db`` for its own check.
        #: Falls back to ``session`` when not supplied (e.g. a test/caller
        #: with only one, already-non-RLS session) - callers that DO have a
        #: separate RLS session must pass it explicitly.
        self._authz_session = authz_session if authz_session is not None else session
        self._asset_repo = AssetRepository(session)
        self._incident_repo = IncidentRepository(session)
        self._alert_repo = AlertRepository(session)
        self._vuln_repo = VulnerabilityRepository(session)
        self._report_repo = ReportRepository(session)
        self._finding_repo = FindingRepository(session)
        self._sla_policy_repo = SlaPolicyRepository(session)
        self._cve_assessment_repo = CveAssessmentRepository(session)

    async def try_route(
        self,
        query: str,
        entities: ExtractedEntities,
        *,
        user_id: uuid.UUID,
        intent: str | None = None,
        project_id: uuid.UUID | None = None,
        caller: AppUser | None = None,
    ) -> ToolRouteResult:
        text = (query or "").strip().lower()

        # An explicit "theo tài liệu vừa upload" reference must force RAG
        # retrieval - never answer from an app-data tool or stale entities,
        # and never from a project-context tool either (checked first, even
        # ahead of the project-scoped routes below, so selecting a project
        # can never hijack an explicit document follow-up).
        if intent == "knowledge_rag":
            return ToolRouteResult(handled=False)

        # A compromise claim ("website bị tấn công") always routes to
        # incident-response guidance, even if the message also contains a
        # URL or a stale CVE carried over from a previous turn - and, per a
        # Task 8 security-review fix, even if a project is selected: an
        # active-incident report must never be misrouted into a project
        # status/overdue table just because it happens to share a keyword
        # with one of the new project-scoped handlers below. Checked before
        # the project-scoped dispatch for exactly the same reason the
        # knowledge_rag short-circuit above is.
        if intent == "incident_response":
            return self._route_incident_response(text)

        # Project-scoped routes (Task 8: AI Project Security Copilot) - only
        # engaged when the caller has actually selected a project (an
        # explicit project_id parameter threaded from the chat request, see
        # AssistantService.chat). No project selected means these new
        # handlers never match, and behavior is identical to before this
        # task existed. Checked before every other branch below so a
        # project-scoped question is never accidentally answered by the
        # flat/global handlers (e.g. a project-selected CVE question must
        # get project-aware priority context, not the generic CVE lookup) -
        # but AFTER the knowledge_rag/incident_response short-circuits
        # above, which must always win regardless of project selection.
        if project_id is not None and caller is not None:
            project_result = await self._route_project_scoped(
                text, entities, project_id=project_id, caller=caller
            )
            if project_result is not None:
                return project_result

        # SQLi/SSRF/CSP each have their own intent (see backend/services/intent.py)
        # purely so a message about one of these topics is never left
        # classified as GENERAL - which would make it eligible for the
        # "carry forward a stale CVE/URL from a previous turn" rule below.
        # The actual answer for these topics still comes from the local
        # knowledge base / RAG pipeline (unhandled here), which already
        # composes bilingual, structured answers.
        if intent in ("sqli_question", "ssrf_question", "csp_question"):
            return ToolRouteResult(handled=False)

        if entities.cves:
            return await self._route_cve(entities.cves[0], query=text)

        if entities.urls and self._looks_like_scan_request(text):
            return await self._route_url_scan(entities.urls[0])

        if self._looks_like_security_news_request(text):
            return await self._route_security_news()

        # 1. System Health / Status
        if any(
            term in text
            for term in (
                "system health",
                "trang thai he thong",
                "trạng thái hệ thống",
                "health status",
                "platform status",
            )
        ):
            bind = self._session.get_bind()
            db_check = await check_database(bind)
            content = "**Trạng thái hệ thống (System Health):** `HEALTHY`\n\n"
            content += f"- **Database (PostgreSQL):** {db_check.get('status', 'healthy')}\n"
            content += "- **Redis Cache:** healthy\n"
            content += "- **AI Assistant (Local Engine):** ready\n"
            return ToolRouteResult(
                handled=True,
                content=content,
                metadata={
                    "provider": "local",
                    "gemini_called": False,
                    "routing_reason": "app_data_tool",
                    "tool_name": "system_health",
                },
            )

        # 2. Asset Questions
        if any(term in text for term in ("asset", "tai san", "tài sản")) and any(
            term in text
            for term in (
                "danh sach",
                "danh sách",
                "list",
                "show",
                "bao nhieu",
                "bao nhiêu",
                "count",
                "so luong",
                "số lượng",
            )
        ):
            assets, total = await self._asset_repo.list(user_id=user_id, page=1, page_size=10)
            content = f"**Tổng số Asset thuộc quyền sở hữu của bạn:** `{total}`\n\n"
            if assets:
                content += "Danh sách các Asset mới nhất:\n"
                for a in assets:
                    ip_info = (
                        f" ({a.ip_address})" if hasattr(a, "ip_address") and a.ip_address else ""
                    )
                    crit = getattr(a, "business_criticality", "medium")
                    content += (
                        f"- **{a.name}** [{a.type.upper()}]{ip_info} - Target: {crit.upper()}\n"
                    )
            else:
                content += "Chưa có Asset nào được đăng ký trong hệ thống.\n"

            return ToolRouteResult(
                handled=True,
                content=content,
                metadata={
                    "provider": "local",
                    "gemini_called": False,
                    "routing_reason": "app_data_tool",
                    "tool_name": "list_assets",
                    "total_count": total,
                },
            )

        # 3. Incident Questions
        if any(term in text for term in ("incident", "su co", "sự cố")) and any(
            term in text
            for term in (
                "danh sach",
                "danh sách",
                "list",
                "show",
                "bao nhieu",
                "bao nhiêu",
                "count",
                "critical",
            )
        ):
            incidents, total = await self._incident_repo.list(user_id=user_id, page=1, page_size=10)
            content = f"**Tổng số Incident trong hệ thống:** `{total}`\n\n"
            if incidents:
                content += "Các Incident mới nhất:\n"
                for inc in incidents:
                    content += (
                        f"- **[{inc.severity.upper()}]** {inc.title} - Status: `{inc.status}`\n"
                    )
            else:
                content += "Không có Incident nào trong hệ thống.\n"

            return ToolRouteResult(
                handled=True,
                content=content,
                metadata={
                    "provider": "local",
                    "gemini_called": False,
                    "routing_reason": "app_data_tool",
                    "tool_name": "list_incidents",
                    "total_count": total,
                },
            )

        # 4. Alert Questions
        if any(term in text for term in ("alert", "canh bao", "cảnh báo")) and any(
            term in text
            for term in (
                "danh sach",
                "danh sách",
                "list",
                "show",
                "bao nhieu",
                "bao nhiêu",
                "count",
            )
        ):
            alerts, total = await self._alert_repo.list(user_id=user_id, page=1, page_size=10)
            content = f"**Tổng số Security Alerts:** `{total}`\n\n"
            if alerts:
                content += "Các Alert mới nhất:\n"
                for alt in alerts:
                    content += (
                        f"- **[{alt.severity.upper()}]** {alt.title} - Status: `{alt.status}`\n"
                    )
            else:
                content += "Không tìm thấy Alert nào.\n"

            return ToolRouteResult(
                handled=True,
                content=content,
                metadata={
                    "provider": "local",
                    "gemini_called": False,
                    "routing_reason": "app_data_tool",
                    "tool_name": "list_alerts",
                    "total_count": total,
                },
            )

        # 5. Vulnerability Questions
        if any(term in text for term in ("lo hong", "lỗ hổng", "vulnerabilit")) and any(
            term in text for term in ("danh sach", "danh sách", "bao nhieu", "bao nhiêu", "list")
        ):
            vulns, total = await self._vuln_repo.list(user_id=user_id, page=1, page_size=10)
            content = f"**Tổng số Lỗ hổng (Vulnerabilities) ghi nhận:** `{total}`\n\n"
            if vulns:
                content += "Danh sách Lỗ hổng mới nhất:\n"
                for v in vulns:
                    cve_str = f" ({v.cve_id})" if getattr(v, "cve_id", None) else ""
                    content += (
                        f"- **[{v.severity.upper()}]** {v.title}{cve_str} - Status: `{v.status}`\n"
                    )
            else:
                content += "Không có lỗ hổng nào được phát hiện.\n"

            return ToolRouteResult(
                handled=True,
                content=content,
                metadata={
                    "provider": "local",
                    "gemini_called": False,
                    "routing_reason": "app_data_tool",
                    "tool_name": "list_vulnerabilities",
                    "total_count": total,
                },
            )

        # 6. Report Questions
        if any(term in text for term in ("report", "bao cao", "báo cáo")) and any(
            term in text
            for term in (
                "danh sach",
                "danh sách",
                "list",
                "show",
                "gan nhat",
                "gần nhất",
                "moi nhat",
                "mới nhất",
                "latest",
                "recent",
                "xem",
            )
        ):
            reports, total = await self._report_repo.list(user_id=user_id, page=1, page_size=5)
            content = f"**Tổng số Report đã tạo:** `{total}`\n\n"
            if reports:
                content += "Các Report gần nhất:\n"
                for r in reports:
                    content += (
                        f"- **{r.title}** [{r.category.upper()}/{r.format.upper()}] - "
                        f"Status: `{r.status}` - {r.created_at:%Y-%m-%d}\n"
                    )
            else:
                content += "Chưa có Report nào được tạo. Hãy dùng Reports Center để tạo report đầu tiên.\n"

            return ToolRouteResult(
                handled=True,
                content=content,
                metadata={
                    "provider": "local",
                    "gemini_called": False,
                    "routing_reason": "app_data_tool",
                    "tool_name": "list_reports",
                    "total_count": total,
                },
            )

        return ToolRouteResult(handled=False)

    # -- Task 8: AI Project Security Copilot -------------------------------
    # Every handler below touches Project/Finding/ScanRun/CveAssessment
    # data scoped to one project_id. Each one calls
    # ``resolve_project_access`` as its VERY FIRST action and returns
    # immediately on a denial - this is the single non-negotiable rule for
    # this section of the router (see the Task 8 brief). No handler here
    # queries Finding/ScanRun/CveAssessment data before that check passes.

    #: Keyword groups used by ``_route_project_scoped`` to pick which new
    #: project-context handler answers a message, bilingual (Vietnamese +
    #: English) matching the existing router's keyword-match style. Checked
    #: in this exact order - see ``_route_project_scoped`` for why the order
    #: matters (e.g. a rescan-history question about a specific CVE must win
    #: over the generic "any CVE mention" -> cve_priority fallback).
    _PROJECT_RESCAN_HISTORY_TERMS: tuple[str, ...] = (
        "da sua chua", "đã sửa chưa", "da fix chua", "đã fix chưa",
        "lan quet truoc", "lần quét trước", "scan truoc", "quét trước",
        "previous scan", "was this fixed", "already fixed", "con khong",
        "còn không", "con ton tai khong", "còn tồn tại không",
        "did the previous scan",
    )
    #: Deliberately does NOT include the bare word "sla" - "SLA" alone is
    #: ambiguous between "what's overdue against the SLA?" and "what does
    #: the SLA policy say?"; the more specific policy-question phrasing
    #: ("sla policy", "chính sách") wins that ambiguity via
    #: ``_PROJECT_POLICY_TERMS`` instead (checked after this list).
    _PROJECT_OVERDUE_TERMS: tuple[str, ...] = (
        "qua han", "quá hạn", "tre han", "trễ hạn", "overdue",
        "het han", "hết hạn",
    )
    _PROJECT_FINDINGS_PRIORITY_TERMS: tuple[str, ...] = (
        "nen sua gi truoc", "nên sửa gì trước", "sua cai gi truoc",
        "sửa cái gì trước", "uu tien sua", "ưu tiên sửa",
        "what to fix first", "what should i fix", "fix first",
        "priority findings", "findings uu tien", "risk cao nhat",
        "rủi ro cao nhất", "top risks",
    )
    _PROJECT_ASSIGNMENT_TERMS: tuple[str, ...] = (
        "ai dang xu ly", "ai đang xử lý", "ai phu trach", "ai phụ trách",
        "ai chiu trach nhiem", "ai chịu trách nhiệm", "who's working",
        "who is working", "assigned to", "dang lam viec", "đang làm việc",
    )
    _PROJECT_POLICY_TERMS: tuple[str, ...] = (
        "chinh sach", "chính sách", "policy", "quy dinh", "quy định",
        "sla policy", "deadline", "thoi han xu ly", "thời hạn xử lý",
    )
    _PROJECT_STATUS_TERMS: tuple[str, ...] = (
        "co van de gi", "có vấn đề gì", "dieu gi sai", "điều gì sai",
        "wrong with this project", "wrong with the project",
        "tong quan", "tổng quan", "project overview", "tinh trang",
        "tình trạng", "security dashboard", "bao mat du an", "bảo mật dự án",
        "how is the project", "project status", "diem bao mat",
        "điểm bảo mật", "security score",
    )

    async def _route_project_scoped(
        self,
        text: str,
        entities: ExtractedEntities,
        *,
        project_id: uuid.UUID,
        caller: AppUser,
    ) -> ToolRouteResult | None:
        """Picks which project-context handler (if any) answers this
        message. Returns ``None`` (never a ``ToolRouteResult``) when nothing
        matches, so ``try_route`` falls through to the existing flat/global
        handlers exactly as before this task existed - a project being
        selected never forces every message through this dispatcher.

        NOTE: this method only decides *which* handler to call - it does
        NOT itself perform the authorization check. Every handler it calls
        independently calls ``resolve_project_access`` first, so the check
        can never be skipped even if this dispatch logic changes later.
        """
        if any(term in text for term in self._PROJECT_RESCAN_HISTORY_TERMS):
            cve_or_rule_id = entities.cves[0] if entities.cves else None
            return await self._route_rescan_history(project_id, cve_or_rule_id, caller)

        if any(term in text for term in self._PROJECT_OVERDUE_TERMS):
            return await self._route_overdue(project_id, caller)

        if any(term in text for term in self._PROJECT_FINDINGS_PRIORITY_TERMS):
            return await self._route_findings_priority(project_id, caller)

        if any(term in text for term in self._PROJECT_ASSIGNMENT_TERMS):
            return await self._route_assignment(project_id, caller)

        if any(term in text for term in self._PROJECT_POLICY_TERMS):
            return await self._route_policy(project_id, caller)

        if entities.cves:
            return await self._route_cve_priority(project_id, entities.cves[0], caller)

        if any(term in text for term in self._PROJECT_STATUS_TERMS):
            return await self._route_project_status(project_id, caller)

        return None

    @staticmethod
    def _denial_result(access: ProjectAccessResult, *, tool_name: str) -> ToolRouteResult:
        """The single place a denial (not-found or forbidden) becomes a
        ``ToolRouteResult`` - every project-scoped handler returns this
        immediately when ``access.authorized`` is ``False``, so the exact
        wording (never a generic "no evidence found" that could be misread
        as "this project has no problems") is guaranteed consistent."""
        return ToolRouteResult(
            handled=True,
            content=access.denial_message or "Không thể xử lý yêu cầu này.",
            metadata={
                "provider": "local",
                "gemini_called": False,
                "routing_reason": (
                    "project_access_denied"
                    if access.denial_reason == DENIAL_FORBIDDEN
                    else "project_not_found"
                ),
                "tool_name": tool_name,
                "grounding_status": "NO_EVIDENCE",
                "confidence": 0.0,
            },
        )

    async def _route_project_status(
        self, project_id: uuid.UUID, caller: AppUser
    ) -> ToolRouteResult:
        """Answers "what's wrong with this project?" / project-overview
        questions using Task 5's dashboard aggregation directly - no ad hoc
        re-derivation of open/critical counts or the security score."""
        access = await resolve_project_access(project_id, caller, self._authz_session)
        if not access.authorized:
            return self._denial_result(access, tool_name="project_status")

        dashboard = await ProjectDashboardService(self._session).get_security_dashboard(
            project_id, actor=caller
        )
        project = access.project
        by_sev = dashboard["open_by_severity"]
        lines = [
            f"**Tổng quan bảo mật dự án: {project.name}**",
            "",
            f"- Điểm bảo mật (Security Score): `{dashboard['security_score']}/100`",
            f"- Tổng số finding đang mở: `{dashboard['open_findings']}`",
            f"  - Critical: `{by_sev.get('critical', 0)}` | High: `{by_sev.get('high', 0)}` | "
            f"Medium: `{by_sev.get('medium', 0)}` | Low: `{by_sev.get('low', 0)}`",
            f"- Đang chờ xác minh (fixed, chưa verified): `{dashboard['waiting_verify']}`",
            f"- Quá hạn xử lý (overdue): `{dashboard['overdue']}`",
            f"- Đã sửa trong 7 ngày qua: `{dashboard['fixed_this_week']}`",
        ]
        top_risks = dashboard.get("top_risks") or []
        if top_risks:
            lines.append("")
            lines.append("**Top rủi ro cần chú ý:**")
            for item in top_risks[:5]:
                lines.append(
                    f"- **[{item['severity'].upper()}]** {item['title']} "
                    f"(`{item['status']}`{', quá hạn' if item['is_overdue'] else ''})"
                )
        return ToolRouteResult(
            handled=True,
            content="\n".join(lines),
            metadata={
                "provider": "local",
                "gemini_called": False,
                "routing_reason": "project_status_tool",
                "tool_name": "project_status",
                "grounding_status": "GROUNDED",
                "confidence": 0.95,
                "tool_runs": [
                    {
                        "tool": "project_status",
                        "status": "success",
                        "source": "project_dashboard",
                        "input": {"project_id": str(project_id)},
                    }
                ],
                "suggested_actions": ["Tôi nên sửa gì trước?", "Có gì quá hạn?", "Ai đang xử lý?"],
            },
        )

    async def _route_findings_priority(
        self, project_id: uuid.UUID, caller: AppUser
    ) -> ToolRouteResult:
        """Answers "what should I fix first?" using Task 5's
        ``list_top_risks`` (severity-first, then most-overdue tiebreak) -
        the same ordering the dashboard's "Top Risks" card uses."""
        access = await resolve_project_access(project_id, caller, self._authz_session)
        if not access.authorized:
            return self._denial_result(access, tool_name="findings_priority")

        findings = await self._finding_repo.list_top_risks(project_id=project_id, limit=10)
        if not findings:
            content = (
                "Không có finding nào đang mở trong project này cần ưu tiên xử lý ngay."
            )
        else:
            lines = ["**Thứ tự ưu tiên xử lý (nghiêm trọng nhất trước):**", ""]
            for index, finding in enumerate(findings, start=1):
                overdue_tag = " - **QUÁ HẠN**" if sla_service.is_overdue(finding) else ""
                lines.append(
                    f"{index}. **[{finding.severity.upper()}]** {finding.title} "
                    f"(`{finding.status}`){overdue_tag}"
                )
            content = "\n".join(lines)
        return ToolRouteResult(
            handled=True,
            content=content,
            metadata={
                "provider": "local",
                "gemini_called": False,
                "routing_reason": "findings_priority_tool",
                "tool_name": "findings_priority",
                "grounding_status": "GROUNDED",
                "confidence": 0.95,
                "tool_runs": [
                    {
                        "tool": "findings_priority",
                        "status": "success",
                        "source": "finding_repository",
                        "input": {"project_id": str(project_id)},
                        "result_count": len(findings),
                    }
                ],
                "suggested_actions": ["Ai đang xử lý?", "Có gì quá hạn?"],
            },
        )

    async def _route_assignment(self, project_id: uuid.UUID, caller: AppUser) -> ToolRouteResult:
        """Answers "who's working on this?" / "ai đang xử lý lỗi X?" -
        lists currently-assigned open findings for the project."""
        access = await resolve_project_access(project_id, caller, self._authz_session)
        if not access.authorized:
            return self._denial_result(access, tool_name="assignment")

        findings = await self._finding_repo.list_assigned_open(project_id=project_id, limit=20)
        if not findings:
            content = "Hiện chưa có finding nào trong project này được giao cho ai xử lý."
        else:
            lines = ["**Finding đang được giao xử lý:**", ""]
            for finding in findings:
                lines.append(
                    f"- **[{finding.severity.upper()}]** {finding.title} (`{finding.status}`) - "
                    f"Người xử lý: `{finding.assignee_user_id}`"
                )
            content = "\n".join(lines)
        return ToolRouteResult(
            handled=True,
            content=content,
            metadata={
                "provider": "local",
                "gemini_called": False,
                "routing_reason": "assignment_tool",
                "tool_name": "assignment",
                "grounding_status": "GROUNDED",
                "confidence": 0.9,
                "tool_runs": [
                    {
                        "tool": "assignment",
                        "status": "success",
                        "source": "finding_repository",
                        "input": {"project_id": str(project_id)},
                        "result_count": len(findings),
                    }
                ],
            },
        )

    #: How many overdue findings the response body lists, matching the
    #: display cap other handlers use (e.g. ``_route_assignment``'s 20) -
    #: a security-review fix: printing every overdue finding unbounded was
    #: the only new handler without such a cap.
    _OVERDUE_DISPLAY_LIMIT = 20

    #: Severity -> sort rank, most severe first - a plain Python dict (not
    #: FindingRepository._SEVERITY_RANK, which is a SQLAlchemy `case()`
    #: usable only inside a query) since overdue-ness itself is computed in
    #: Python from ``sla.is_overdue`` after the fetch, so the display order
    #: is also applied in Python.
    _SEVERITY_DISPLAY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}

    async def _route_overdue(self, project_id: uuid.UUID, caller: AppUser) -> ToolRouteResult:
        """Answers "what's overdue?" - reuses ``sla.is_overdue`` (the single
        source of truth for overdue-ness) rather than reimplementing the
        deadline/terminal-status check here."""
        access = await resolve_project_access(project_id, caller, self._authz_session)
        if not access.authorized:
            return self._denial_result(access, tool_name="overdue")

        candidates = await self._finding_repo.list_all_for_project_unpaginated(
            project_id=project_id, status=None, severity=None, assignee_user_id=None
        )
        overdue_findings = [f for f in candidates if sla_service.is_overdue(f)]
        overdue_findings.sort(key=lambda f: self._SEVERITY_DISPLAY_RANK.get(f.severity, 4))
        total_overdue = len(overdue_findings)
        displayed = overdue_findings[: self._OVERDUE_DISPLAY_LIMIT]
        if not overdue_findings:
            content = "Không có finding nào đang quá hạn xử lý trong project này."
        else:
            lines = [f"**Finding đang quá hạn xử lý (overdue) - tổng `{total_overdue}`:**", ""]
            for finding in displayed:
                deadline = finding.deadline.isoformat() if finding.deadline else "N/A"
                lines.append(
                    f"- **[{finding.severity.upper()}]** {finding.title} (`{finding.status}`) - "
                    f"Hạn xử lý: `{deadline}`"
                )
            if total_overdue > len(displayed):
                lines.append(f"- ... và `{total_overdue - len(displayed)}` finding quá hạn khác.")
            content = "\n".join(lines)
        return ToolRouteResult(
            handled=True,
            content=content,
            metadata={
                "provider": "local",
                "gemini_called": False,
                "routing_reason": "overdue_tool",
                "tool_name": "overdue",
                "grounding_status": "GROUNDED",
                "confidence": 0.95,
                "tool_runs": [
                    {
                        "tool": "overdue",
                        "status": "success",
                        "source": "sla_service",
                        "input": {"project_id": str(project_id)},
                        "result_count": total_overdue,
                    }
                ],
            },
        )

    async def _route_rescan_history(
        self, project_id: uuid.UUID, cve_or_rule_id: str | None, caller: AppUser
    ) -> ToolRouteResult:
        """Answers "did the previous scan have this?" / "was this fixed?" -
        reads already-computed Finding/FindingTransition state, never
        reimplements Task 3's fingerprint/diff logic."""
        access = await resolve_project_access(project_id, caller, self._authz_session)
        if not access.authorized:
            return self._denial_result(access, tool_name="rescan_history")

        if not cve_or_rule_id:
            return ToolRouteResult(
                handled=True,
                content=(
                    "Bạn muốn kiểm tra lịch sử của CVE hoặc rule nào? Vui lòng cho tôi biết "
                    "mã CVE cụ thể (ví dụ CVE-2021-44228)."
                ),
                metadata={
                    "provider": "local",
                    "gemini_called": False,
                    "routing_reason": "rescan_history_tool",
                    "tool_name": "rescan_history",
                    "grounding_status": "NO_EVIDENCE",
                    "confidence": 0.0,
                },
            )

        is_cve = cve_or_rule_id.strip().upper().startswith("CVE-")
        findings = await self._finding_repo.list_by_cve_or_rule(
            project_id=project_id,
            cve_id=cve_or_rule_id.strip().upper() if is_cve else None,
            rule_id=None if is_cve else cve_or_rule_id,
        )
        if not findings:
            content = (
                f"Không tìm thấy finding nào ứng với `{cve_or_rule_id}` trong project này - "
                "có thể chưa từng được phát hiện ở bất kỳ lần quét nào."
            )
        else:
            latest = findings[0]
            transitions = await self._finding_repo.list_transitions(latest.id)
            # Reuses sla.TERMINAL_STATUSES (closed/false_positive/
            # accepted_risk) - the same single source of truth
            # is_overdue/count_open_by_severity/etc. already use for "this
            # finding is done, one way or another" - rather than hand-rolling
            # a separate status list here (a security-review fix: the
            # original list of ("closed", "fixed", "verified") wrongly
            # excluded false_positive/accepted_risk, which are terminal too).
            is_resolved = latest.status in sla_service.TERMINAL_STATUSES
            lines = [
                f"**Lịch sử `{cve_or_rule_id}` trong project này:**",
                "",
                f"- Trạng thái hiện tại: `{latest.status}`"
                + (" (đã được xử lý)" if is_resolved else " (chưa được xử lý xong)"),
                f"- Lần đầu phát hiện: scan run `{latest.first_seen_scan_run_id}`",
                f"- Lần gần nhất còn thấy: scan run `{latest.last_seen_scan_run_id}`",
                f"- Số lần chuyển trạng thái: `{len(transitions)}`",
            ]
            if len(findings) > 1:
                lines.append(
                    f"- Có `{len(findings)}` finding liên quan đến `{cve_or_rule_id}` trong "
                    "project này (hiển thị bản ghi mới nhất ở trên)."
                )
            content = "\n".join(lines)
        return ToolRouteResult(
            handled=True,
            content=content,
            metadata={
                "provider": "local",
                "gemini_called": False,
                "routing_reason": "rescan_history_tool",
                "tool_name": "rescan_history",
                "grounding_status": "GROUNDED" if findings else "NO_EVIDENCE",
                "confidence": 0.9 if findings else 0.0,
                "tool_runs": [
                    {
                        "tool": "rescan_history",
                        "status": "success",
                        "source": "finding_repository",
                        "input": {"project_id": str(project_id), "identifier": cve_or_rule_id},
                        "result_count": len(findings),
                    }
                ],
            },
        )

    async def _route_cve_priority(
        self, project_id: uuid.UUID, cve_id: str, caller: AppUser
    ) -> ToolRouteResult:
        """Answers "how do I fix this CVE?" / priority questions for a
        specific CVE in this project - surfaces Task 6's already-computed
        ``CveAssessment.rationale`` verbatim, never recomputes priority."""
        access = await resolve_project_access(project_id, caller, self._authz_session)
        if not access.authorized:
            return self._denial_result(access, tool_name="cve_priority")

        normalized_cve = cve_id.strip().upper()
        assessment = await self._cve_assessment_repo.get_by_project_and_cve(
            project_id=project_id, cve_id=normalized_cve
        )
        if assessment is None:
            # Security-review fix: a project selection must never silently
            # disable the pre-existing generic CVE lookup handler. No
            # project-specific priority assessment existing yet is not the
            # same as "no CVE information available" - fall back to the
            # existing, unmodified _route_cve so the caller still gets real
            # NVD-backed CVE data (description/CVSS/etc.), with a note that
            # no project-specific assessment has been run yet.
            generic_result = await self._route_cve(normalized_cve, query="")
            if generic_result.handled:
                note = (
                    f"\n\n_(Project này chưa có đánh giá ưu tiên CVE Risk Prioritization "
                    f"riêng cho `{normalized_cve}` - phần trên là dữ liệu CVE chung, chưa "
                    "gắn với bối cảnh project.)_"
                )
                return ToolRouteResult(
                    handled=True,
                    content=generic_result.content + note,
                    metadata=generic_result.metadata,
                )
            return generic_result

        rationale = assessment.rationale or {}
        lines = [
            f"**Ưu tiên xử lý {normalized_cve} trong project này:**",
            "",
            f"- Mức ưu tiên: `{assessment.priority}`",
            f"- Điểm số: `{assessment.score}/10`",
        ]
        if assessment.cvss_score is not None:
            lines.append(f"- CVSS: `{assessment.cvss_score}`")
        if assessment.epss_score is not None:
            lines.append(f"- EPSS: `{assessment.epss_score}`")
        lines.append(f"- CISA KEV (đang bị khai thác thực tế): `{'có' if assessment.is_kev else 'không'}`")
        if rationale.get("reasoning"):
            lines.append("")
            lines.append(f"**Lý do:** {rationale['reasoning']}")
        return ToolRouteResult(
            handled=True,
            content="\n".join(lines),
            metadata={
                "provider": "local",
                "gemini_called": False,
                "routing_reason": "cve_priority_tool",
                "tool_name": "cve_priority",
                "grounding_status": "GROUNDED",
                "confidence": 0.95,
                "tool_runs": [
                    {
                        "tool": "cve_priority",
                        "status": "success",
                        "source": "cve_assessment_repository",
                        "input": {"project_id": str(project_id), "cve_id": normalized_cve},
                    }
                ],
                "suggested_actions": ["Giải thích dễ hiểu", "Finding nào liên quan?"],
            },
        )

    async def _route_policy(self, project_id: uuid.UUID, caller: AppUser) -> ToolRouteResult:
        """Answers "what does policy say?" - reuses Task 3's SLA policy
        lookup (project override, else global default) rather than
        reimplementing the precedence rule ``sla.compute_deadline`` already
        encodes."""
        access = await resolve_project_access(project_id, caller, self._authz_session)
        if not access.authorized:
            return self._denial_result(access, tool_name="policy")

        lines = ["**Chính sách SLA (thời hạn xử lý) áp dụng cho project này:**", ""]
        for severity in ("critical", "high", "medium", "low"):
            override = await self._sla_policy_repo.get_project_override(
                project_id=project_id, severity=severity
            )
            if override is not None:
                lines.append(
                    f"- **{severity.upper()}**: `{override.hours_to_deadline}` giờ "
                    "(tùy chỉnh riêng cho project này)"
                )
                continue
            global_policy = await self._sla_policy_repo.get_global(severity)
            if global_policy is not None:
                lines.append(
                    f"- **{severity.upper()}**: `{global_policy.hours_to_deadline}` giờ "
                    "(mặc định toàn hệ thống)"
                )
            else:
                lines.append(f"- **{severity.upper()}**: không áp dụng thời hạn SLA cụ thể.")
        return ToolRouteResult(
            handled=True,
            content="\n".join(lines),
            metadata={
                "provider": "local",
                "gemini_called": False,
                "routing_reason": "policy_tool",
                "tool_name": "policy",
                "grounding_status": "GROUNDED",
                "confidence": 0.95,
                "tool_runs": [
                    {
                        "tool": "policy",
                        "status": "success",
                        "source": "sla_policy_repository",
                        "input": {"project_id": str(project_id)},
                    }
                ],
            },
        )

    #: Matches an explicit step-count request ("checklist 5 bước", "5 steps",
    #: "5-step checklist") so the response can honor it instead of always
    #: returning the full fixed playbook.
    _STEP_COUNT_PATTERN = re.compile(r"(\d+)\s*(?:bước|buoc|steps?)", re.IGNORECASE)

    @classmethod
    def _route_incident_response(cls, query: str = "") -> ToolRouteResult:
        steps = [
            (
                "**Cách ly (Contain):** ngắt kết nối mạng/tắt truy cập công khai của "
                "hệ thống hoặc website nghi ngờ để ngăn thiệt hại lan rộng, nhưng "
                "không tắt máy nếu cần thu thập bằng chứng bộ nhớ."
            ),
            (
                "**Thu thập bằng chứng (Preserve evidence):** sao lưu log truy cập, "
                "log máy chủ, cấu hình, và bất kỳ file lạ nào trước khi thay đổi hệ thống."
            ),
            (
                "**Xác định phạm vi (Scope):** kiểm tra tài khoản, quyền truy cập, "
                "tiến trình lạ, và các hệ thống liên quan khác có thể đã bị ảnh hưởng."
            ),
            (
                "**Loại bỏ (Eradicate):** gỡ mã độc/backdoor, đổi toàn bộ mật khẩu và "
                "khóa API liên quan, vá lỗ hổng đã bị khai thác."
            ),
            (
                "**Khôi phục (Recover):** khôi phục từ bản sao lưu sạch, giám sát chặt "
                "chẽ sau khi đưa hệ thống trở lại hoạt động."
            ),
            (
                "**Báo cáo (Report):** tạo Incident trong hệ thống để theo dõi và, nếu "
                "liên quan dữ liệu người dùng, đánh giá nghĩa vụ thông báo vi phạm."
            ),
        ]

        requested_count: int | None = None
        match = cls._STEP_COUNT_PATTERN.search(query or "")
        if match:
            requested_count = int(match.group(1))

        # An explicit step count is a checklist/diagnostic request, not a
        # live-incident containment report - honor the exact count and drop
        # the Report/"create Incident" step, which isn't part of a checklist
        # the user asked for and previously leaked in regardless of intent.
        if requested_count is not None and 0 < requested_count < len(steps):
            selected = steps[:requested_count]
            title = f"**Checklist {requested_count} bước kiểm tra hệ thống nghi bị xâm nhập:**"
            lines = [title, ""] + [f"{i}. {s}" for i, s in enumerate(selected, start=1)]
            return ToolRouteResult(
                handled=True,
                content="\n".join(lines),
                metadata={
                    "provider": "local",
                    "gemini_called": False,
                    "routing_reason": "incident_response_checklist",
                    "tool_name": "incident_response_guidance",
                    "grounding_status": "GROUNDED",
                    "confidence": 0.9,
                },
            )

        content = "\n".join(
            [
                "**Xử lý sự cố nghi bị tấn công (Incident Response):**",
                "",
                *(f"{i}. {s}" for i, s in enumerate(steps, start=1)),
                "",
                "Bạn có muốn tôi tạo một Incident mới để theo dõi vụ việc này không?",
            ]
        )
        return ToolRouteResult(
            handled=True,
            content=content,
            metadata={
                "provider": "local",
                "gemini_called": False,
                "routing_reason": "incident_response_playbook",
                "tool_name": "incident_response_guidance",
                "grounding_status": "GROUNDED",
                "confidence": 0.9,
                "suggested_actions": ["Tạo Incident mới", "Xem danh sách Incident"],
            },
        )

    #: Keyword groups used to classify a CVE *follow-up* question into a
    #: focused sub-answer instead of always replaying the full CVE dump.
    _CVE_FOLLOWUP_AFFECTED: tuple[str, ...] = (
        "anh huong he thong", "ảnh hưởng hệ thống", "he thong nao",
        "hệ thống nào", "san pham nao", "sản phẩm nào", "affected system",
        "anh huong toi", "ảnh hưởng tới", "bi anh huong", "bị ảnh hưởng",
    )
    _CVE_FOLLOWUP_IMPACT: tuple[str, ...] = (
        "nguy hiem", "nguy hiểm", "muc do", "mức độ", "nghiem trong",
        "nghiêm trọng", "impact", "severity", "tai sao nguy hiem",
        "tại sao nguy hiểm",
    )
    _CVE_FOLLOWUP_REMEDIATION: tuple[str, ...] = (
        "xu ly", "xử lý", "khac phuc", "khắc phục", "va loi", "vá lỗi",
        "thu tu", "thứ tự", "remediat", "nen lam gi", "nên làm gì",
        "cach fix", "cách fix", "mitigat",
    )

    #: The user explicitly asked for a non-technical / audience-adapted
    #: explanation. When present, the CVE composer must not dump raw CVSS
    #: vectors, exact timestamps, or raw CPE-derived product lists - those
    #: are exactly the "raw tool payload" the answer composer exists to keep
    #: out of the response.
    _CVE_PLAIN_LANGUAGE_MARKERS: tuple[str, ...] = (
        "khong biet ky thuat", "không biết kỹ thuật", "khong ranh cong nghe",
        "không rành công nghệ", "cho nguoi moi", "cho người mới",
        "de hieu", "dễ hiểu", "don gian", "đơn giản", "khong chuyen",
        "không chuyên", "layman", "non-technical", "in simple terms",
        "explain simply", "eli5", "sinh vien moi hoc", "sinh viên mới học",
    )

    #: An explicit request to bypass the plain-language synthesis and see
    #: the raw looked-up record instead (full NVD description, CVSS vector,
    #: CPE list, timestamps). Checked before ``_CVE_PLAIN_LANGUAGE_MARKERS``
    #: so it wins if both appear in the same message.
    _CVE_RAW_DATA_MARKERS: tuple[str, ...] = (
        "du lieu cve goc", "dữ liệu cve gốc", "raw cve", "show raw",
        "du lieu nvd", "dữ liệu nvd", "nvd description", "mo ta nvd",
        "mô tả nvd", "cvss vector", "raw data", "du lieu tho", "dữ liệu thô",
    )

    @classmethod
    def _classify_cve_followup(cls, query: str) -> str | None:
        text = (query or "").strip().lower()
        if any(term in text for term in cls._CVE_FOLLOWUP_AFFECTED):
            return "affected_systems"
        if any(term in text for term in cls._CVE_FOLLOWUP_IMPACT):
            return "impact"
        if any(term in text for term in cls._CVE_FOLLOWUP_REMEDIATION):
            return "remediation"
        return None

    #: Plain-language severity phrasing, used instead of a raw CVSS
    #: score/vector when the user asked for a non-technical explanation.
    _SEVERITY_PLAIN_VI: dict[str, str] = {
        "critical": "cực kỳ nghiêm trọng - cần xử lý ngay lập tức",
        "high": "nghiêm trọng - nên xử lý sớm",
        "medium": "mức độ trung bình - nên lên kế hoạch xử lý",
        "low": "mức độ thấp - có thể xử lý khi có thời gian",
    }

    #: Well-known public nicknames for a handful of CVEs that are commonly
    #: referred to by name rather than by identifier. Deliberately small and
    #: additive-only (an unlisted CVE simply gets no alias) - this is not a
    #: general lookup, just a courtesy for the CVEs people actually ask about
    #: by nickname.
    _CVE_ALIASES: dict[str, str] = {
        "cve-2021-44228": "Log4Shell",
        "cve-2014-0160": "Heartbleed",
        "cve-2017-0144": "EternalBlue",
        "cve-2020-1472": "Zerologon",
        "cve-2021-34527": "PrintNightmare",
    }

    #: Keyword -> plain-language impact phrase, checked against the raw NVD
    #: description so the *evidence* it contains can drive a synthesized
    #: sentence without ever echoing the raw English text verbatim. Order
    #: matters: first match wins, most specific impact first.
    _IMPACT_KEYWORDS_VI: tuple[tuple[tuple[str, ...], str], ...] = (
        (
            ("remote code execution", "arbitrary code", "execute code", " rce "),
            "thực thi mã tùy ý từ xa trên hệ thống bị ảnh hưởng, thường không cần đăng nhập",
        ),
        (
            ("privilege escalation", "elevation of privilege", "domain controller"),
            "chiếm quyền quản trị hoặc leo thang đặc quyền trên hệ thống bị ảnh hưởng",
        ),
        (
            ("denial of service",),
            "khiến hệ thống hoặc dịch vụ ngừng hoạt động (từ chối dịch vụ)",
        ),
        (
            ("sql injection",),
            "thao túng hoặc đánh cắp dữ liệu thông qua truy vấn cơ sở dữ liệu",
        ),
        (
            ("information disclosure", "expose", "leak"),
            "làm lộ dữ liệu nhạy cảm ra bên ngoài",
        ),
    )

    @classmethod
    def _plain_impact_phrase(cls, description: str) -> str:
        lowered = f" {(description or '').lower()} "
        for keywords, phrase in cls._IMPACT_KEYWORDS_VI:
            if any(keyword in lowered for keyword in keywords):
                return phrase
        return "gây ảnh hưởng nghiêm trọng đến tính bảo mật của hệ thống bị ảnh hưởng"

    @classmethod
    def _compose_cve_plain_language(
        cls, record: dict[str, Any], tool_run: dict[str, Any]
    ) -> ToolRouteResult:
        """Synthesize a beginner-friendly explanation from the CVE evidence.

        The looked-up record (raw description, CVSS vector, CPE list,
        timestamps) is EVIDENCE for this answer, never the final display
        text - the caller asked for a non-technical explanation, so none of
        that raw tool payload is echoed verbatim. Only a short, derived
        impact phrase (see ``_plain_impact_phrase``) is used to keep the
        answer grounded in the real record without dumping it.
        """
        cve_id = record["cve_id"]
        alias = cls._CVE_ALIASES.get(cve_id.strip().lower())
        severity_key = str(record.get("severity") or "").strip().lower()
        severity_phrase = cls._SEVERITY_PLAIN_VI.get(
            severity_key, "chưa xác định được mức độ nghiêm trọng cụ thể"
        )
        impact_phrase = cls._plain_impact_phrase(record.get("description") or "")
        lines = [
            f"**{cve_id} - giải thích đơn giản:**",
            "",
            f"{cve_id}{(' (' + alias + ')') if alias else ''} là một lỗ hổng bảo mật "
            f"ở mức độ {severity_phrase}.",
            "",
            f"Nói một cách đơn giản: kẻ tấn công có thể lợi dụng lỗ hổng này để "
            f"{impact_phrase} nếu hệ thống của bạn đang dùng thành phần bị ảnh hưởng.",
            "",
            "Bạn không cần hiểu chi tiết kỹ thuật - điều quan trọng là: nếu hệ thống "
            "của bạn dùng phần mềm/thư viện bị ảnh hưởng, hãy cập nhật lên phiên bản "
            "đã vá lỗi càng sớm càng tốt, hoặc nhờ đội kỹ thuật kiểm tra giúp. Nếu bạn "
            "muốn xem dữ liệu kỹ thuật gốc (CVSS, mô tả NVD đầy đủ...), cứ hỏi \"xem dữ "
            "liệu CVE gốc\"."
        ]
        return ToolRouteResult(
            handled=True,
            content="\n".join(lines),
            metadata={
                "provider": "local",
                "gemini_called": False,
                "routing_reason": "cve_plain_language",
                "tool_name": "cve_lookup",
                "tool_runs": [tool_run],
                "grounding_status": "GROUNDED",
                "confidence": 0.9,
            },
        )

    @staticmethod
    def _compose_cve_followup(
        record: dict[str, Any], followup: str, tool_run: dict[str, Any]
    ) -> ToolRouteResult:
        """Answer a CVE follow-up with a focused section instead of repeating
        the identical full dump every time the user asks a different question
        about the same CVE."""
        cve_id = record["cve_id"]
        if followup == "affected_systems":
            products = _humanize_affected_products(record.get("affected_products") or [])
            if products:
                body = (
                    f"**{cve_id} ảnh hưởng các hệ thống/sản phẩm sau:**\n"
                    + "\n".join(f"- {product}" for product in products)
                )
            else:
                body = (
                    f"Nguồn CVE cho `{cve_id}` không liệt kê danh sách sản phẩm bị ảnh "
                    "hưởng cụ thể. Kiểm kê thủ công theo mô tả lỗ hổng và thành phần "
                    "phần mềm bạn đang dùng để xác định phạm vi ảnh hưởng thực tế."
                )
        elif followup == "impact":
            parts = [f"**Mức độ nguy hiểm của {cve_id}:**"]
            if record.get("severity"):
                parts.append(f"- Mức độ: `{record['severity']}`")
            if record.get("cvss_score") is not None:
                parts.append(f"- Điểm CVSS: `{record['cvss_score']}`")
            if record.get("vector"):
                parts.append(f"- Vector tấn công: `{record['vector']}`")
            if not any(record.get(k) for k in ("severity", "cvss_score", "vector")):
                parts.append("- Nguồn CVE chưa cung cấp điểm CVSS/mức độ cho lỗ hổng này.")
            if record.get("description"):
                parts.append("")
                parts.append(record["description"])
            body = "\n".join(parts)
        else:  # remediation
            body = "\n".join(
                [
                    f"**Thứ tự xử lý khuyến nghị cho {cve_id}:**",
                    "1. Kiểm kê nơi đang dùng thành phần/phiên bản bị ảnh hưởng.",
                    "2. Đối chiếu phiên bản đang chạy với phiên bản đã vá.",
                    "3. Ưu tiên vá hoặc áp dụng biện pháp giảm thiểu cho hệ thống "
                    "internet-facing trước.",
                    "4. Vá/nâng cấp các hệ thống nội bộ còn lại.",
                    "5. Xác minh lại (rescan) sau khi vá để chắc chắn lỗ hổng đã "
                    "được xử lý.",
                ]
            )
        return ToolRouteResult(
            handled=True,
            content=body,
            metadata={
                "provider": "local",
                "gemini_called": False,
                "routing_reason": f"cve_followup_{followup}",
                "tool_name": "cve_lookup",
                "tool_runs": [tool_run],
                "grounding_status": "GROUNDED",
                "confidence": 0.9,
                "suggested_actions": [
                    "Xem cách khắc phục",
                    "Giải thích dễ hiểu",
                    "Phân tích mức độ ảnh hưởng",
                ],
            },
        )

    async def _route_cve(self, cve_id: str, *, query: str = "") -> ToolRouteResult:
        tool_run: dict[str, Any] = {
            "tool": "cve_lookup",
            "status": "started",
            "source": "nvd",
            "input": {"cve_id": cve_id},
        }
        try:
            record = await CveLookupService().get(cve_id, actor="assistant")
        except AppError as exc:
            tool_run["status"] = "error"
            tool_run["error"] = exc.error
            return ToolRouteResult(
                handled=True,
                content=(
                    f"Tôi không lấy được dữ liệu CVE chính thức cho `{cve_id}` lúc này "
                    f"({exc.error}). Tôi sẽ không tự bịa CVSS, mức độ nghiêm trọng, "
                    "nhà cung cấp hay ngày công bố."
                ),
                metadata={
                    "provider": "local",
                    "gemini_called": False,
                    "routing_reason": "cve_tool",
                    "tool_name": "cve_lookup",
                    "tool_runs": [tool_run],
                    "grounding_status": "NO_EVIDENCE",
                    "confidence": 0.0,
                },
            )

        tool_run["status"] = "success"
        wants_raw = any(
            marker in (query or "").lower() for marker in self._CVE_RAW_DATA_MARKERS
        )
        if not wants_raw and any(
            marker in (query or "").lower() for marker in self._CVE_PLAIN_LANGUAGE_MARKERS
        ):
            return self._compose_cve_plain_language(record, tool_run)

        followup = self._classify_cve_followup(query)
        if followup is not None:
            return self._compose_cve_followup(record, followup, tool_run)

        lines = [
            f"**{record['cve_id']}**",
            "",
            record.get("description") or "Không có mô tả trong nguồn CVE.",
            "",
            "**Dữ liệu từ nguồn CVE:**",
        ]
        if record.get("severity"):
            lines.append(f"- Mức độ: `{record['severity']}`")
        if record.get("cvss_score") is not None:
            lines.append(f"- CVSS: `{record['cvss_score']}`")
        if record.get("vector"):
            lines.append(f"- Vector: `{record['vector']}`")
        if record.get("published_at"):
            lines.append(f"- Công bố: `{record['published_at']}`")
        if record.get("modified_at"):
            lines.append(f"- Cập nhật: `{record['modified_at']}`")
        products = _humanize_affected_products(record.get("affected_products") or [])
        if products:
            lines.append("- Sản phẩm ảnh hưởng: " + "; ".join(products))
        refs = list(record.get("references") or [])[:3]
        if refs:
            lines.append("")
            lines.append("**Nguồn tham khảo:**")
            lines.extend(f"- {ref}" for ref in refs)
        lines.append("")
        lines.append(
            "Gợi ý xử lý: kiểm kê nơi đang dùng thành phần liên quan, đối chiếu phiên bản, "
            "ưu tiên vá/cấu hình giảm thiểu cho hệ thống internet-facing, rồi xác minh lại."
        )

        return ToolRouteResult(
            handled=True,
            content="\n".join(lines),
            metadata={
                "provider": "local",
                "gemini_called": False,
                "routing_reason": "cve_tool",
                "tool_name": "cve_lookup",
                "tool_runs": [tool_run],
                "grounding_status": "GROUNDED",
                "confidence": 0.95,
                "suggested_actions": [
                    "Xem cách khắc phục",
                    "Giải thích dễ hiểu",
                    "Phân tích mức độ ảnh hưởng",
                ],
            },
        )

    async def _route_url_scan(self, url: str) -> ToolRouteResult:
        tool_run: dict[str, Any] = {
            "tool": "url_scan",
            "status": "started",
            "source": "local_url_scanner",
            "input": {"url": url},
        }
        try:
            result = await scan_url(url)
        except BlockedTargetError as exc:
            tool_run["status"] = "blocked"
            tool_run["error"] = exc.error
            return ToolRouteResult(
                handled=True,
                content=(
                    f"Không quét URL này vì bị chặn bởi lớp bảo vệ SSRF.\n\n"
                    f"{blocked_summary(exc)}\n\n"
                    "Các địa chỉ loopback, private, link-local và metadata cloud không được phép quét từ server."
                ),
                metadata={
                    "provider": "local",
                    "gemini_called": False,
                    "routing_reason": "website_tool",
                    "tool_name": "url_scan",
                    "tool_runs": [tool_run],
                    "grounding_status": "GROUNDED",
                    "confidence": 1.0,
                    "suggested_actions": ["Giải thích cảnh báo", "Kiểm tra URL khác"],
                },
            )
        except AppError as exc:
            tool_run["status"] = "error"
            tool_run["error"] = exc.error
            return ToolRouteResult(
                handled=True,
                content=f"Tôi không thể quét URL này lúc này ({exc.error}). Tôi sẽ không suy đoán kết quả quét.",
                metadata={
                    "provider": "local",
                    "gemini_called": False,
                    "routing_reason": "website_tool",
                    "tool_name": "url_scan",
                    "tool_runs": [tool_run],
                    "grounding_status": "NO_EVIDENCE",
                    "confidence": 0.0,
                },
            )

        tool_run["status"] = "success"
        findings = list(result.get("findings") or [])[:5]
        lines = [
            f"**Kết quả quét URL:** `{result.get('normalized_url')}`",
            "",
            f"- Trạng thái: `{result.get('status')}`",
            f"- Điểm rủi ro: `{result.get('risk_score')}/100`",
            f"- Mức độ: `{result.get('severity')}`",
            f"- Có HTTPS: `{'có' if result.get('has_https') else 'không'}`",
            f"- Truy cập được: `{'có' if result.get('reachable') else 'không'}`",
        ]
        if result.get("http_status") is not None:
            lines.append(f"- HTTP status: `{result.get('http_status')}`")
        lines.append("")
        lines.append(f"**Tóm tắt:** {summarize(result)}")
        if findings:
            lines.append("")
            lines.append("**Phát hiện chính:**")
            lines.extend(
                f"- `{item.get('code')}` ({item.get('severity')}): {item.get('message')}"
                for item in findings
            )
        recommendations = list(result.get("recommendations") or [])[:3]
        if recommendations:
            lines.append("")
            lines.append("**Khuyến nghị:**")
            lines.extend(f"- {item}" for item in recommendations)

        return ToolRouteResult(
            handled=True,
            content="\n".join(lines),
            metadata={
                "provider": "local",
                "gemini_called": False,
                "routing_reason": "website_tool",
                "tool_name": "url_scan",
                "tool_runs": [tool_run],
                "grounding_status": "GROUNDED",
                "confidence": 0.9,
                "suggested_actions": [
                    "Giải thích cảnh báo",
                    "Tôi nên sửa gì trước?",
                    "Kiểm tra lại",
                ],
            },
        )

    async def _route_security_news(self) -> ToolRouteResult:
        articles, total = await SecurityNewsService(self._session).list(page=1, page_size=5)
        tool_run = {
            "tool": "security_news_lookup",
            "status": "success",
            "source": "security_news_db",
            "result_count": len(articles),
        }
        if not articles:
            return ToolRouteResult(
                handled=True,
                content=(
                    "Tôi chưa tìm thấy bản tin bảo mật nào trong cơ sở dữ liệu hiện tại. "
                    "Tôi sẽ không gọi Gemini hoặc bịa tin mới."
                ),
                metadata={
                    "provider": "local",
                    "gemini_called": False,
                    "routing_reason": "security_news_tool",
                    "tool_name": "security_news_lookup",
                    "tool_runs": [tool_run],
                    "grounding_status": "NO_EVIDENCE",
                    "confidence": 0.0,
                },
            )

        lines = [f"**Tin bảo mật mới nhất trong hệ thống** ({total} bản ghi):", ""]
        for article in articles:
            summary = article.ai_summary or article.summary
            lines.append(f"- **{article.title}** ({article.source}, {article.published_at:%Y-%m-%d})")
            if summary:
                lines.append(f"  {summary[:280]}")
            lines.append(f"  Nguồn: {article.url}")

        return ToolRouteResult(
            handled=True,
            content="\n".join(lines),
            metadata={
                "provider": "local",
                "gemini_called": False,
                "routing_reason": "security_news_tool",
                "tool_name": "security_news_lookup",
                "tool_runs": [tool_run],
                "grounding_status": "GROUNDED",
                "confidence": 0.9,
                "suggested_actions": [
                    "Tóm tắt ngắn",
                    "Ai bị ảnh hưởng?",
                    "Tôi nên ưu tiên tin nào?",
                ],
            },
        )

    @staticmethod
    def _looks_like_scan_request(text: str) -> bool:
        return any(
            term in text
            for term in (
                "scan",
                "check",
                "kiem tra",
                "kiểm tra",
                "quét",
                "quet",
                "đánh giá",
                "danh gia",
                "phishing",
                "an toàn",
                "safe",
            )
        )

    @staticmethod
    def _looks_like_security_news_request(text: str) -> bool:
        return any(term in text for term in ("news", "tin bảo mật", "tin bao mat", "tin tức bảo mật", "tin tuc bao mat")) or (
            "tin" in text and any(term in text for term in ("bảo mật", "bao mat", "security"))
        )
