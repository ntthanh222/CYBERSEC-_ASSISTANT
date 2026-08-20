"""Task 7 (Admin Console Upgrade): cross-project/cross-workspace admin
visibility over Workspaces/Projects/Findings, filter-preset correctness for
every named Findings sub-view, admin archive-any-project, and
authorization. Every number asserted here is provably derived from seeded
rows - same "no fake data" discipline as test_project_dashboard.py."""
import uuid
from datetime import datetime, timedelta, timezone

from backend.database.models.finding import Finding
from backend.database.models.rbac import UserRole

from .conftest import TEST_USER_A, TEST_USER_B


async def _make_admin(db_sessionmaker):
    """Promotes TEST_USER_A to admin. Unlike test_admin_api.py's
    ``_seed_role`` (always called *before* any other API call in that
    file), the tests here create workspaces/projects/findings as
    TEST_USER_A first - which lazily creates its ``UserRole`` row as
    ``get_app_user``'s first call always does (see
    backend/core/authorization.py) - so a bare INSERT here would violate
    the primary key. Upsert instead: update the row if it already exists,
    else insert."""
    async with db_sessionmaker() as session:
        existing = await session.get(UserRole, TEST_USER_A.id)
        if existing is not None:
            existing.role = "admin"
            existing.is_active = True
        else:
            session.add(UserRole(user_id=TEST_USER_A.id, role="admin", is_active=True))
        await session.commit()


def _create_workspace(api_client, name: str = "Acme Corp Security") -> dict:
    response = api_client.post("/api/workspaces", json={"name": name, "description": None})
    assert response.status_code == 201, response.text
    return response.json()


def _create_project(api_client, workspace_id: str, name: str = "Customer Portal", **overrides) -> dict:
    payload = {
        "workspace_id": workspace_id,
        "name": name,
        "environment": "production",
        "criticality": "high",
        "internet_facing": True,
    }
    payload.update(overrides)
    response = api_client.post("/api/projects", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def _finding_payload(**overrides) -> dict:
    payload = {
        "rule_id": "sqli",
        "category": "injection",
        "title": "SQL injection in login form",
        "evidence": "payload reflected",
        "impact": "Full DB read access",
        "remediation": "Use parameterized queries",
        "severity": "high",
        "target": "https://example.com/login",
    }
    payload.update(overrides)
    return payload


def _create_finding(api_client, project_id: str, **overrides) -> dict:
    response = api_client.post(f"/api/projects/{project_id}/findings", json=_finding_payload(**overrides))
    assert response.status_code == 201, response.text
    return response.json()


def _transition(api_client, project_id: str, finding_id: str, to_status: str, reason: str | None = None) -> dict:
    body = {"to_status": to_status}
    if reason is not None:
        body["reason"] = reason
    response = api_client.post(f"/api/projects/{project_id}/findings/{finding_id}/transition", json=body)
    assert response.status_code == 200, response.text
    return response.json()


async def _force_deadline(db_sessionmaker, finding_id: str, deadline) -> None:
    async with db_sessionmaker() as session:
        record = await session.get(Finding, uuid.UUID(finding_id))
        record.deadline = deadline
        await session.commit()


async def _force_closed_at(db_sessionmaker, finding_id: str, closed_at) -> None:
    async with db_sessionmaker() as session:
        record = await session.get(Finding, uuid.UUID(finding_id))
        record.closed_at = closed_at
        await session.commit()


# ─── Authorization: every new endpoint requires admin ──────────────────────


def test_admin_workspaces_requires_admin(api_client):
    assert api_client.get("/api/admin/workspaces").status_code == 403


def test_admin_projects_requires_admin(api_client):
    assert api_client.get("/api/admin/projects").status_code == 403


def test_admin_findings_requires_admin(api_client):
    assert api_client.get("/api/admin/findings").status_code == 403


def test_admin_archive_requires_admin(api_client):
    response = api_client.post(f"/api/admin/projects/{uuid.uuid4()}/archive")
    assert response.status_code == 403


# ─── Workspaces ──────────────────────────────────────────────────────────────


async def test_admin_workspaces_lists_every_workspace_with_counts(
    api_client, db_sessionmaker, switch_user
):
    workspace = _create_workspace(api_client)
    _create_project(api_client, workspace["id"])
    api_client.post(
        f"/api/workspaces/{workspace['id']}/members",
        json={"user_id": str(TEST_USER_B.id), "workspace_role": "member"},
    )

    # TEST_USER_A has no involvement with this second workspace at all -
    # proves the admin list is not membership-scoped.
    switch_user(TEST_USER_B)
    other_workspace = _create_workspace(api_client, name="Other Org")
    switch_user(TEST_USER_A)

    await _make_admin(db_sessionmaker)

    page = api_client.get("/api/admin/workspaces").json()
    assert page["total"] == 2
    by_id = {item["id"]: item for item in page["items"]}
    assert by_id[workspace["id"]]["member_count"] == 2  # A (owner) + B (member)
    assert by_id[workspace["id"]]["project_count"] == 1
    assert by_id[other_workspace["id"]]["member_count"] == 1
    assert by_id[other_workspace["id"]]["project_count"] == 0


# ─── Projects ────────────────────────────────────────────────────────────────


async def test_admin_projects_lists_every_project_with_filters_and_counts(
    api_client, db_sessionmaker, switch_user
):
    workspace_a = _create_workspace(api_client, name="WS A")
    project_a = _create_project(
        api_client, workspace_a["id"], name="Prod App", environment="production", criticality="critical"
    )
    api_client.post(
        f"/api/projects/{project_a['id']}/members",
        json={"user_id": str(TEST_USER_B.id), "project_role": "developer"},
    )
    _create_finding(api_client, project_a["id"], severity="high")  # left "open"

    # TEST_USER_A is not a member of this project at all.
    switch_user(TEST_USER_B)
    workspace_b = _create_workspace(api_client, name="WS B")
    project_b = _create_project(
        api_client, workspace_b["id"], name="Staging App", environment="staging", criticality="low"
    )
    switch_user(TEST_USER_A)

    await _make_admin(db_sessionmaker)

    page = api_client.get("/api/admin/projects").json()
    assert page["total"] == 2  # sees project_b despite not being a member

    prod_page = api_client.get("/api/admin/projects?environment=production").json()
    assert prod_page["total"] == 1
    assert prod_page["items"][0]["id"] == project_a["id"]
    assert prod_page["items"][0]["member_count"] == 2  # owner A + developer B
    assert prod_page["items"][0]["open_findings_count"] == 1

    critical_page = api_client.get("/api/admin/projects?criticality=critical").json()
    assert critical_page["total"] == 1
    assert critical_page["items"][0]["id"] == project_a["id"]

    workspace_filtered = api_client.get(f"/api/admin/projects?workspace_id={workspace_b['id']}").json()
    assert workspace_filtered["total"] == 1
    assert workspace_filtered["items"][0]["id"] == project_b["id"]
    assert workspace_filtered["items"][0]["open_findings_count"] == 0


async def test_admin_can_archive_a_project_they_are_not_a_member_of(
    api_client, db_sessionmaker, switch_user
):
    switch_user(TEST_USER_B)
    workspace = _create_workspace(api_client)
    project = _create_project(api_client, workspace["id"])
    switch_user(TEST_USER_A)

    await _make_admin(db_sessionmaker)

    response = api_client.post(f"/api/admin/projects/{project['id']}/archive")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "archived"
    assert body["archived_at"]

    status_page = api_client.get("/api/admin/projects?status=archived").json()
    assert status_page["total"] == 1
    assert status_page["items"][0]["id"] == project["id"]

    audit = api_client.get("/api/admin/audit").json()
    entry = next(item for item in audit["items"] if item["action"] == "project_archived_by_admin")
    assert entry["actor_user_id"] == str(TEST_USER_A.id)
    assert entry["metadata"]["project_id"] == project["id"]


async def test_admin_archive_404s_for_an_unknown_project(api_client, db_sessionmaker):
    await _make_admin(db_sessionmaker)
    response = api_client.post(f"/api/admin/projects/{uuid.uuid4()}/archive")
    assert response.status_code == 404


# ─── Findings ────────────────────────────────────────────────────────────────


async def test_admin_findings_visible_across_projects_not_membership_scoped(
    api_client, db_sessionmaker, switch_user
):
    switch_user(TEST_USER_B)
    workspace = _create_workspace(api_client)
    project = _create_project(api_client, workspace["id"])
    finding = _create_finding(api_client, project["id"])
    switch_user(TEST_USER_A)

    await _make_admin(db_sessionmaker)

    page = api_client.get("/api/admin/findings").json()
    ids = {item["id"] for item in page["items"]}
    assert finding["id"] in ids
    matched = next(item for item in page["items"] if item["id"] == finding["id"])
    assert matched["project_name"] == project["name"]


async def test_admin_findings_filter_presets_match_exact_seeded_rows(api_client, db_sessionmaker):
    workspace = _create_workspace(api_client)
    project = _create_project(api_client, workspace["id"])
    project_id = project["id"]

    # Open (never transitioned) - critical.
    f_open_critical = _create_finding(
        api_client, project_id, rule_id="r1", severity="critical", target="https://x/1"
    )
    # Confirmed (still "open" bucket-wise) - high.
    f_high = _create_finding(api_client, project_id, rule_id="r2", severity="high", target="https://x/2")
    _transition(api_client, project_id, f_high["id"], "confirmed")
    # Waiting verify (status == "fixed").
    f_fixed = _create_finding(api_client, project_id, rule_id="r3", severity="medium", target="https://x/3")
    _transition(api_client, project_id, f_fixed["id"], "confirmed")
    _transition(api_client, project_id, f_fixed["id"], "in_progress")
    _transition(api_client, project_id, f_fixed["id"], "fixed")
    # Overdue - confirmed with a deadline forced into the past.
    f_overdue = _create_finding(api_client, project_id, rule_id="r4", severity="low", target="https://x/4")
    _transition(api_client, project_id, f_overdue["id"], "confirmed")
    await _force_deadline(db_sessionmaker, f_overdue["id"], datetime.now(timezone.utc) - timedelta(hours=3))
    # Fixed this week - closed just now.
    f_closed_recent = _create_finding(
        api_client, project_id, rule_id="r5", severity="high", target="https://x/5"
    )
    _transition(api_client, project_id, f_closed_recent["id"], "confirmed")
    _transition(api_client, project_id, f_closed_recent["id"], "in_progress")
    _transition(api_client, project_id, f_closed_recent["id"], "fixed")
    _transition(api_client, project_id, f_closed_recent["id"], "verified")
    _transition(api_client, project_id, f_closed_recent["id"], "closed")
    # Closed, but outside the fixed_since window - must NOT appear in "fixed this week".
    f_closed_old = _create_finding(
        api_client, project_id, rule_id="r6", severity="high", target="https://x/6"
    )
    _transition(api_client, project_id, f_closed_old["id"], "confirmed")
    _transition(api_client, project_id, f_closed_old["id"], "in_progress")
    _transition(api_client, project_id, f_closed_old["id"], "fixed")
    _transition(api_client, project_id, f_closed_old["id"], "verified")
    _transition(api_client, project_id, f_closed_old["id"], "closed")
    await _force_closed_at(db_sessionmaker, f_closed_old["id"], datetime.now(timezone.utc) - timedelta(days=30))
    # Accepted risk.
    f_accepted = _create_finding(
        api_client, project_id, rule_id="r7", severity="medium", target="https://x/7"
    )
    _transition(api_client, project_id, f_accepted["id"], "accepted_risk", reason="Compensating control in place")
    # False positive.
    f_false_positive = _create_finding(
        api_client, project_id, rule_id="r8", severity="low", target="https://x/8"
    )
    _transition(api_client, project_id, f_false_positive["id"], "false_positive", reason="Not exploitable")

    await _make_admin(db_sessionmaker)

    def ids(query: str) -> set[str]:
        response = api_client.get(f"/api/admin/findings{query}")
        assert response.status_code == 200, response.text
        return {item["id"] for item in response.json()["items"]}

    assert ids("?status=open") == {f_open_critical["id"]}
    assert ids("?severity=critical") == {f_open_critical["id"]}
    assert ids("?severity=high") == {f_high["id"], f_closed_recent["id"], f_closed_old["id"]}
    assert ids("?overdue=true") == {f_overdue["id"]}
    assert ids("?status=fixed") == {f_fixed["id"]}
    assert ids("?preset=fixed_this_week") == {f_closed_recent["id"]}
    assert ids("?status=closed") == {f_closed_recent["id"], f_closed_old["id"]}
    assert ids("?status=accepted_risk") == {f_accepted["id"]}
    assert ids("?status=false_positive") == {f_false_positive["id"]}

    # project_id filter narrows to just this project (no other project exists
    # here, but exercises the filter is honoured, not ignored).
    assert ids(f"?project_id={project_id}") == {
        f_open_critical["id"],
        f_high["id"],
        f_fixed["id"],
        f_overdue["id"],
        f_closed_recent["id"],
        f_closed_old["id"],
        f_accepted["id"],
        f_false_positive["id"],
    }


# ─── Summary: exact nonzero values against real seeded lifecycle data ──────


async def test_admin_summary_lifecycle_fields_exact_values(api_client, db_sessionmaker, switch_user):
    workspace = _create_workspace(api_client)
    project = _create_project(api_client, workspace["id"])
    project_id = project["id"]

    other_project = _create_project(api_client, workspace["id"], name="Legacy App")
    archive_response = api_client.post(f"/api/projects/{other_project['id']}/archive")
    assert archive_response.status_code == 200, archive_response.text

    switch_user(TEST_USER_B)
    _create_workspace(api_client, name="Other org")
    switch_user(TEST_USER_A)

    f_critical = _create_finding(api_client, project_id, rule_id="r1", severity="critical", target="https://x/1")
    f_high = _create_finding(api_client, project_id, rule_id="r2", severity="high", target="https://x/2")
    _transition(api_client, project_id, f_high["id"], "confirmed")
    await _force_deadline(db_sessionmaker, f_high["id"], datetime.now(timezone.utc) - timedelta(hours=1))
    f_fixed = _create_finding(api_client, project_id, rule_id="r3", severity="medium", target="https://x/3")
    _transition(api_client, project_id, f_fixed["id"], "confirmed")
    _transition(api_client, project_id, f_fixed["id"], "in_progress")
    _transition(api_client, project_id, f_fixed["id"], "fixed")
    f_closed = _create_finding(api_client, project_id, rule_id="r4", severity="low", target="https://x/4")
    _transition(api_client, project_id, f_closed["id"], "confirmed")
    _transition(api_client, project_id, f_closed["id"], "in_progress")
    _transition(api_client, project_id, f_closed["id"], "fixed")
    _transition(api_client, project_id, f_closed["id"], "verified")
    _transition(api_client, project_id, f_closed["id"], "closed")

    await _make_admin(db_sessionmaker)

    body = api_client.get("/api/admin/summary").json()

    assert body["active_workspaces"] == 2
    assert body["active_projects"] == 1
    # Open bucket: f_critical(open) + f_high(confirmed) + f_fixed(fixed) = 3.
    # f_closed excluded (terminal).
    assert body["open_findings"] == 3
    assert body["critical_findings"] == 1
    assert body["high_findings"] == 1
    assert body["overdue_findings"] == 1
    assert body["waiting_verify_findings"] == 1
    assert body["fixed_this_week_findings"] == 1

    # Project Health: 1 active project. open_by_severity = {critical:1,
    # high:1, medium:1, low:0}. score = 100 - min(100, 1*15+1*8+1*3+0*1)
    # = 100 - 26 = 74 -> "warning" bucket (50 <= 74 < 80).
    health = {item["bucket"]: item["count"] for item in body["project_health"]}
    assert health == {"healthy": 0, "warning": 1, "critical": 0}
    assert f_critical["severity"] == "critical"  # sanity: seeded as intended
