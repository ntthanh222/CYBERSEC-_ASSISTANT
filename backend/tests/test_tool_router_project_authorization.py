"""Task 8: AI Project Security Copilot - authorization test suite.

THE most important test file in Task 8. Every new project-scoped
tool-router handler in ``backend.services.rag.tool_router.AppDataToolRouter``
MUST call the shared ``resolve_project_access`` helper as its very first
action, before touching any Finding/ScanRun/CveAssessment data. This file
exercises every one of those handlers directly (not through the full HTTP
+ RAG pipeline, so the assertions are exact and deterministic) across four
scenarios each:

(a) a project member gets real data back;
(b) a non-member gets the EXACT denial message (never a generic
    "no evidence"/"not found" style fallback that could be misread as "this
    project has no problems");
(c) a global admin bypasses without any ProjectMember row;
(d) a nonexistent project_id gets a clear "not found" message, never a
    crash or a silent empty response.
"""
import uuid

import pytest

from backend.core.authorization import AppUser
from backend.database.models.cve_assessment import CveAssessment
from backend.database.models.finding import Finding
from backend.database.models.project import Project, ProjectMember
from backend.database.models.sla_policy import SlaPolicy
from backend.database.models.workspace import Workspace, WorkspaceMember
from backend.services.rag.entity_extractor import ExtractedEntities
from backend.services.rag.project_context import ACCESS_DENIED_MESSAGE
from backend.services.rag.tool_router import AppDataToolRouter


def _app_user(user_id: uuid.UUID | None = None, *, role: str = "user") -> AppUser:
    return AppUser(id=user_id or uuid.uuid4(), email=None, role=role, is_active=True)


async def _seed_workspace_and_project(
    session, *, creator_id: uuid.UUID, criticality: str = "high", internet_facing: bool = True
) -> tuple[Workspace, Project]:
    workspace = Workspace(name="W", created_by_user_id=creator_id)
    session.add(workspace)
    await session.flush()
    project = Project(
        workspace_id=workspace.id,
        name="Payments API",
        environment="production",
        criticality=criticality,
        internet_facing=internet_facing,
        owner_user_id=creator_id,
    )
    session.add(project)
    await session.flush()
    await session.commit()
    return workspace, project


async def _add_member(session, *, project_id: uuid.UUID, user_id: uuid.UUID, role: str = "developer"):
    session.add(ProjectMember(project_id=project_id, user_id=user_id, project_role=role))
    await session.commit()


async def _add_finding(
    session,
    *,
    project_id: uuid.UUID,
    rule_id: str = "rule-1",
    cve_id: str | None = None,
    severity: str = "critical",
    status: str = "open",
    assignee_user_id: uuid.UUID | None = None,
    target: str = "api.example.com",
) -> Finding:
    finding = Finding(
        project_id=project_id,
        scan_run_id=None,
        fingerprint=f"fp-{uuid.uuid4()}",
        rule_id=rule_id,
        category="vuln",
        title=f"Finding for {rule_id}",
        evidence="evidence",
        impact="impact",
        remediation="remediation",
        severity=severity,
        status=status,
        target=target,
        cve_id=cve_id,
        assignee_user_id=assignee_user_id,
    )
    session.add(finding)
    await session.commit()
    return finding


async def _add_cve_assessment(
    session, *, project_id: uuid.UUID, cve_id: str = "CVE-2021-44228"
) -> CveAssessment:
    assessment = CveAssessment(
        project_id=project_id,
        cve_id=cve_id,
        cvss_score=9.8,
        epss_score=0.9,
        is_kev=True,
        priority="patch_now",
        score=9.5,
        rationale={"reasoning": "Known-exploited and internet-facing."},
    )
    session.add(assessment)
    await session.commit()
    return assessment


async def _add_sla_policy(session, *, project_id: uuid.UUID | None, severity: str, hours: int):
    session.add(SlaPolicy(project_id=project_id, severity=severity, hours_to_deadline=hours))
    await session.commit()


# ---------------------------------------------------------------------------
# _route_project_status
# ---------------------------------------------------------------------------


async def test_project_status_member_gets_real_data(db_sessionmaker):
    async with db_sessionmaker() as session:
        creator_id = uuid.uuid4()
        _ws, project = await _seed_workspace_and_project(session, creator_id=creator_id)
        member_id = uuid.uuid4()
        await _add_member(session, project_id=project.id, user_id=member_id)
        await _add_finding(session, project_id=project.id, severity="critical")

        router = AppDataToolRouter(session)
        result = await router._route_project_status(project.id, _app_user(member_id))

        assert result.handled is True
        assert ACCESS_DENIED_MESSAGE not in result.content
        assert "Payments API" in result.content
        assert result.metadata["tool_name"] == "project_status"
        assert result.metadata["grounding_status"] == "GROUNDED"


async def test_project_status_non_member_gets_explicit_denial(db_sessionmaker):
    async with db_sessionmaker() as session:
        creator_id = uuid.uuid4()
        _ws, project = await _seed_workspace_and_project(session, creator_id=creator_id)

        router = AppDataToolRouter(session)
        result = await router._route_project_status(project.id, _app_user())

        assert result.handled is True
        assert result.content == ACCESS_DENIED_MESSAGE
        assert result.metadata["routing_reason"] == "project_access_denied"
        # Must never be conflated with a "no evidence found"/"nothing here"
        # style response, which could be misread as "this project has no
        # problems" rather than "you are not authorized to see it".
        assert "không tìm thấy" not in result.content.lower()
        assert "chưa tìm thấy" not in result.content.lower()


async def test_project_status_admin_bypasses_without_membership(db_sessionmaker):
    async with db_sessionmaker() as session:
        creator_id = uuid.uuid4()
        _ws, project = await _seed_workspace_and_project(session, creator_id=creator_id)

        router = AppDataToolRouter(session)
        result = await router._route_project_status(project.id, _app_user(role="admin"))

        assert result.handled is True
        assert result.content != ACCESS_DENIED_MESSAGE
        assert "Payments API" in result.content


async def test_project_status_nonexistent_project_gets_not_found(db_sessionmaker):
    async with db_sessionmaker() as session:
        router = AppDataToolRouter(session)
        result = await router._route_project_status(uuid.uuid4(), _app_user())

        assert result.handled is True
        assert result.content != ACCESS_DENIED_MESSAGE
        assert "Không tìm thấy project" in result.content
        assert result.metadata["routing_reason"] == "project_not_found"


# ---------------------------------------------------------------------------
# _route_findings_priority
# ---------------------------------------------------------------------------


async def test_findings_priority_member_gets_real_data(db_sessionmaker):
    async with db_sessionmaker() as session:
        creator_id = uuid.uuid4()
        _ws, project = await _seed_workspace_and_project(session, creator_id=creator_id)
        member_id = uuid.uuid4()
        await _add_member(session, project_id=project.id, user_id=member_id)
        finding = await _add_finding(session, project_id=project.id, severity="critical")

        router = AppDataToolRouter(session)
        result = await router._route_findings_priority(project.id, _app_user(member_id))

        assert result.handled is True
        assert finding.title in result.content


async def test_findings_priority_non_member_gets_explicit_denial(db_sessionmaker):
    async with db_sessionmaker() as session:
        creator_id = uuid.uuid4()
        _ws, project = await _seed_workspace_and_project(session, creator_id=creator_id)
        await _add_finding(session, project_id=project.id, severity="critical")

        router = AppDataToolRouter(session)
        result = await router._route_findings_priority(project.id, _app_user())

        assert result.content == ACCESS_DENIED_MESSAGE


async def test_findings_priority_admin_bypasses_without_membership(db_sessionmaker):
    async with db_sessionmaker() as session:
        creator_id = uuid.uuid4()
        _ws, project = await _seed_workspace_and_project(session, creator_id=creator_id)
        finding = await _add_finding(session, project_id=project.id, severity="high")

        router = AppDataToolRouter(session)
        result = await router._route_findings_priority(project.id, _app_user(role="super_admin"))

        assert result.content != ACCESS_DENIED_MESSAGE
        assert finding.title in result.content


async def test_findings_priority_nonexistent_project_gets_not_found(db_sessionmaker):
    async with db_sessionmaker() as session:
        router = AppDataToolRouter(session)
        result = await router._route_findings_priority(uuid.uuid4(), _app_user())

        assert "Không tìm thấy project" in result.content


# ---------------------------------------------------------------------------
# _route_assignment
# ---------------------------------------------------------------------------


async def test_assignment_member_gets_real_data(db_sessionmaker):
    async with db_sessionmaker() as session:
        creator_id = uuid.uuid4()
        _ws, project = await _seed_workspace_and_project(session, creator_id=creator_id)
        member_id = uuid.uuid4()
        assignee_id = uuid.uuid4()
        await _add_member(session, project_id=project.id, user_id=member_id)
        finding = await _add_finding(
            session, project_id=project.id, assignee_user_id=assignee_id, status="in_progress"
        )

        router = AppDataToolRouter(session)
        result = await router._route_assignment(project.id, _app_user(member_id))

        assert result.handled is True
        assert str(assignee_id) in result.content
        assert finding.title in result.content


async def test_assignment_non_member_gets_explicit_denial(db_sessionmaker):
    async with db_sessionmaker() as session:
        creator_id = uuid.uuid4()
        _ws, project = await _seed_workspace_and_project(session, creator_id=creator_id)
        await _add_finding(session, project_id=project.id, assignee_user_id=uuid.uuid4())

        router = AppDataToolRouter(session)
        result = await router._route_assignment(project.id, _app_user())

        assert result.content == ACCESS_DENIED_MESSAGE


async def test_assignment_admin_bypasses_without_membership(db_sessionmaker):
    async with db_sessionmaker() as session:
        creator_id = uuid.uuid4()
        _ws, project = await _seed_workspace_and_project(session, creator_id=creator_id)
        assignee_id = uuid.uuid4()
        await _add_finding(session, project_id=project.id, assignee_user_id=assignee_id)

        router = AppDataToolRouter(session)
        result = await router._route_assignment(project.id, _app_user(role="admin"))

        assert result.content != ACCESS_DENIED_MESSAGE
        assert str(assignee_id) in result.content


async def test_assignment_nonexistent_project_gets_not_found(db_sessionmaker):
    async with db_sessionmaker() as session:
        router = AppDataToolRouter(session)
        result = await router._route_assignment(uuid.uuid4(), _app_user())

        assert "Không tìm thấy project" in result.content


# ---------------------------------------------------------------------------
# _route_overdue
# ---------------------------------------------------------------------------


async def test_overdue_member_gets_real_data(db_sessionmaker):
    from datetime import datetime, timedelta, timezone

    async with db_sessionmaker() as session:
        creator_id = uuid.uuid4()
        _ws, project = await _seed_workspace_and_project(session, creator_id=creator_id)
        member_id = uuid.uuid4()
        await _add_member(session, project_id=project.id, user_id=member_id)
        finding = await _add_finding(session, project_id=project.id, status="confirmed")
        finding.deadline = datetime.now(timezone.utc) - timedelta(hours=5)
        await session.commit()

        router = AppDataToolRouter(session)
        result = await router._route_overdue(project.id, _app_user(member_id))

        assert result.handled is True
        assert finding.title in result.content


async def test_overdue_non_member_gets_explicit_denial(db_sessionmaker):
    async with db_sessionmaker() as session:
        creator_id = uuid.uuid4()
        _ws, project = await _seed_workspace_and_project(session, creator_id=creator_id)

        router = AppDataToolRouter(session)
        result = await router._route_overdue(project.id, _app_user())

        assert result.content == ACCESS_DENIED_MESSAGE


async def test_overdue_admin_bypasses_without_membership(db_sessionmaker):
    async with db_sessionmaker() as session:
        creator_id = uuid.uuid4()
        _ws, project = await _seed_workspace_and_project(session, creator_id=creator_id)

        router = AppDataToolRouter(session)
        result = await router._route_overdue(project.id, _app_user(role="admin"))

        assert result.content != ACCESS_DENIED_MESSAGE


async def test_overdue_nonexistent_project_gets_not_found(db_sessionmaker):
    async with db_sessionmaker() as session:
        router = AppDataToolRouter(session)
        result = await router._route_overdue(uuid.uuid4(), _app_user())

        assert "Không tìm thấy project" in result.content


# ---------------------------------------------------------------------------
# _route_rescan_history
# ---------------------------------------------------------------------------


async def test_rescan_history_member_gets_real_data(db_sessionmaker):
    async with db_sessionmaker() as session:
        creator_id = uuid.uuid4()
        _ws, project = await _seed_workspace_and_project(session, creator_id=creator_id)
        member_id = uuid.uuid4()
        await _add_member(session, project_id=project.id, user_id=member_id)
        await _add_finding(
            session, project_id=project.id, cve_id="CVE-2021-44228", status="closed"
        )

        router = AppDataToolRouter(session)
        result = await router._route_rescan_history(
            project.id, "CVE-2021-44228", _app_user(member_id)
        )

        assert result.handled is True
        assert "CVE-2021-44228" in result.content
        assert "closed" in result.content


async def test_rescan_history_non_member_gets_explicit_denial(db_sessionmaker):
    async with db_sessionmaker() as session:
        creator_id = uuid.uuid4()
        _ws, project = await _seed_workspace_and_project(session, creator_id=creator_id)
        await _add_finding(session, project_id=project.id, cve_id="CVE-2021-44228")

        router = AppDataToolRouter(session)
        result = await router._route_rescan_history(
            project.id, "CVE-2021-44228", _app_user()
        )

        assert result.content == ACCESS_DENIED_MESSAGE


async def test_rescan_history_admin_bypasses_without_membership(db_sessionmaker):
    async with db_sessionmaker() as session:
        creator_id = uuid.uuid4()
        _ws, project = await _seed_workspace_and_project(session, creator_id=creator_id)
        await _add_finding(session, project_id=project.id, cve_id="CVE-2021-44228", status="fixed")

        router = AppDataToolRouter(session)
        result = await router._route_rescan_history(
            project.id, "CVE-2021-44228", _app_user(role="admin")
        )

        assert result.content != ACCESS_DENIED_MESSAGE
        assert "CVE-2021-44228" in result.content


async def test_rescan_history_nonexistent_project_gets_not_found(db_sessionmaker):
    async with db_sessionmaker() as session:
        router = AppDataToolRouter(session)
        result = await router._route_rescan_history(
            uuid.uuid4(), "CVE-2021-44228", _app_user()
        )

        assert "Không tìm thấy project" in result.content


# ---------------------------------------------------------------------------
# _route_cve_priority
# ---------------------------------------------------------------------------


async def test_cve_priority_member_gets_real_data(db_sessionmaker):
    async with db_sessionmaker() as session:
        creator_id = uuid.uuid4()
        _ws, project = await _seed_workspace_and_project(session, creator_id=creator_id)
        member_id = uuid.uuid4()
        await _add_member(session, project_id=project.id, user_id=member_id)
        await _add_cve_assessment(session, project_id=project.id, cve_id="CVE-2021-44228")

        router = AppDataToolRouter(session)
        result = await router._route_cve_priority(
            project.id, "CVE-2021-44228", _app_user(member_id)
        )

        assert result.handled is True
        assert "patch_now" in result.content
        assert "Known-exploited" in result.content


async def test_cve_priority_non_member_gets_explicit_denial(db_sessionmaker):
    async with db_sessionmaker() as session:
        creator_id = uuid.uuid4()
        _ws, project = await _seed_workspace_and_project(session, creator_id=creator_id)
        await _add_cve_assessment(session, project_id=project.id, cve_id="CVE-2021-44228")

        router = AppDataToolRouter(session)
        result = await router._route_cve_priority(
            project.id, "CVE-2021-44228", _app_user()
        )

        assert result.content == ACCESS_DENIED_MESSAGE


async def test_cve_priority_admin_bypasses_without_membership(db_sessionmaker):
    async with db_sessionmaker() as session:
        creator_id = uuid.uuid4()
        _ws, project = await _seed_workspace_and_project(session, creator_id=creator_id)
        await _add_cve_assessment(session, project_id=project.id, cve_id="CVE-2021-44228")

        router = AppDataToolRouter(session)
        result = await router._route_cve_priority(
            project.id, "CVE-2021-44228", _app_user(role="admin")
        )

        assert result.content != ACCESS_DENIED_MESSAGE
        assert "patch_now" in result.content


async def test_cve_priority_nonexistent_project_gets_not_found(db_sessionmaker):
    async with db_sessionmaker() as session:
        router = AppDataToolRouter(session)
        result = await router._route_cve_priority(
            uuid.uuid4(), "CVE-2021-44228", _app_user()
        )

        assert "Không tìm thấy project" in result.content


# ---------------------------------------------------------------------------
# _route_policy
# ---------------------------------------------------------------------------


async def test_policy_member_gets_real_data(db_sessionmaker):
    async with db_sessionmaker() as session:
        creator_id = uuid.uuid4()
        _ws, project = await _seed_workspace_and_project(session, creator_id=creator_id)
        member_id = uuid.uuid4()
        await _add_member(session, project_id=project.id, user_id=member_id)
        await _add_sla_policy(session, project_id=None, severity="critical", hours=24)
        await _add_sla_policy(session, project_id=project.id, severity="high", hours=48)

        router = AppDataToolRouter(session)
        result = await router._route_policy(project.id, _app_user(member_id))

        assert result.handled is True
        assert "24" in result.content
        assert "48" in result.content


async def test_policy_non_member_gets_explicit_denial(db_sessionmaker):
    async with db_sessionmaker() as session:
        creator_id = uuid.uuid4()
        _ws, project = await _seed_workspace_and_project(session, creator_id=creator_id)

        router = AppDataToolRouter(session)
        result = await router._route_policy(project.id, _app_user())

        assert result.content == ACCESS_DENIED_MESSAGE


async def test_policy_admin_bypasses_without_membership(db_sessionmaker):
    async with db_sessionmaker() as session:
        creator_id = uuid.uuid4()
        _ws, project = await _seed_workspace_and_project(session, creator_id=creator_id)

        router = AppDataToolRouter(session)
        result = await router._route_policy(project.id, _app_user(role="admin"))

        assert result.content != ACCESS_DENIED_MESSAGE


async def test_policy_nonexistent_project_gets_not_found(db_sessionmaker):
    async with db_sessionmaker() as session:
        router = AppDataToolRouter(session)
        result = await router._route_policy(uuid.uuid4(), _app_user())

        assert "Không tìm thấy project" in result.content


# ---------------------------------------------------------------------------
# Workspace-owner-equivalent bypass (Task 1's third authorization path) -
# every handler shares the same resolve_project_access helper, so one
# handler is exercised here as a representative check that this path also
# works end to end for the new tool-router surface, not just in
# project_authorization.py's own unit tests.
# ---------------------------------------------------------------------------


async def test_project_status_workspace_owner_bypasses_without_project_member_row(
    db_sessionmaker,
):
    async with db_sessionmaker() as session:
        creator_id = uuid.uuid4()
        workspace, project = await _seed_workspace_and_project(session, creator_id=creator_id)
        ws_owner_id = uuid.uuid4()
        session.add(
            WorkspaceMember(
                workspace_id=workspace.id, user_id=ws_owner_id, workspace_role="owner"
            )
        )
        await session.commit()

        router = AppDataToolRouter(session)
        result = await router._route_project_status(project.id, _app_user(ws_owner_id))

        assert result.content != ACCESS_DENIED_MESSAGE
        assert "Payments API" in result.content


# ---------------------------------------------------------------------------
# try_route dispatch wiring - project_id=None must never engage any new
# handler (regression: the flat/global handlers must behave exactly as
# before this task).
# ---------------------------------------------------------------------------


async def test_try_route_ignores_project_context_when_project_id_is_none(db_sessionmaker):
    async with db_sessionmaker() as session:
        router = AppDataToolRouter(session)
        result = await router.try_route(
            "co van de gi voi project nay khong",
            ExtractedEntities(),
            user_id=uuid.uuid4(),
            intent="general",
            project_id=None,
            caller=None,
        )
        # No app-data tool matches this free-text question when unscoped -
        # falls through to RAG/local-knowledge exactly as before Task 8.
        assert result.handled is False


async def test_try_route_dispatches_to_project_status_when_project_selected(db_sessionmaker):
    async with db_sessionmaker() as session:
        creator_id = uuid.uuid4()
        _ws, project = await _seed_workspace_and_project(session, creator_id=creator_id)
        member_id = uuid.uuid4()
        await _add_member(session, project_id=project.id, user_id=member_id)

        router = AppDataToolRouter(session)
        result = await router.try_route(
            "project này có vấn đề gì không?",
            ExtractedEntities(),
            user_id=member_id,
            intent="general",
            project_id=project.id,
            caller=_app_user(member_id),
        )
        assert result.handled is True
        assert "Payments API" in result.content


async def test_try_route_denies_non_member_via_dispatch(db_sessionmaker):
    async with db_sessionmaker() as session:
        creator_id = uuid.uuid4()
        _ws, project = await _seed_workspace_and_project(session, creator_id=creator_id)

        router = AppDataToolRouter(session)
        result = await router.try_route(
            "project này có vấn đề gì không?",
            ExtractedEntities(),
            user_id=uuid.uuid4(),
            intent="general",
            project_id=project.id,
            caller=_app_user(),
        )
        assert result.handled is True
        assert result.content == ACCESS_DENIED_MESSAGE
