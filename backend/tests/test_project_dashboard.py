"""Task 5: project-scoped Security Dashboard - every number asserted here
must be provably derived from seeded rows (no mock/placeholder numbers
anywhere in the production code path, per the plan)."""
import uuid
from datetime import datetime, timedelta, timezone

from backend.database.models.finding import Finding
from backend.database.models.scan import ScanRun
from backend.services.project_dashboard import _score_from_counts

from .conftest import TEST_USER_B


def _create_workspace(api_client) -> dict:
    return api_client.post(
        "/api/workspaces", json={"name": "Acme Corp Security", "description": None}
    ).json()


def _create_project(api_client, workspace_id: str, name: str = "Customer Portal") -> dict:
    response = api_client.post(
        "/api/projects",
        json={
            "workspace_id": workspace_id,
            "name": name,
            "environment": "production",
            "criticality": "high",
            "internet_facing": True,
        },
    )
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
    response = api_client.post(
        f"/api/projects/{project_id}/findings", json=_finding_payload(**overrides)
    )
    assert response.status_code == 201, response.text
    return response.json()


def _add_member(api_client, project_id: str, user_id, role: str) -> None:
    response = api_client.post(
        f"/api/projects/{project_id}/members",
        json={"user_id": str(user_id), "project_role": role},
    )
    assert response.status_code == 201, response.text


def _set_assignee(api_client, project_id: str, finding_id: str, assignee_user_id) -> None:
    response = api_client.patch(
        f"/api/projects/{project_id}/findings/{finding_id}/assignee",
        json={"assignee_user_id": str(assignee_user_id)},
    )
    assert response.status_code == 200, response.text


def _transition(api_client, project_id: str, finding_id: str, to_status: str, reason: str | None = None) -> dict:
    body = {"to_status": to_status}
    if reason is not None:
        body["reason"] = reason
    response = api_client.post(
        f"/api/projects/{project_id}/findings/{finding_id}/transition", json=body
    )
    assert response.status_code == 200, response.text
    return response.json()


async def _force_deadline(db_sessionmaker, finding_id: str, deadline) -> None:
    async with db_sessionmaker() as session:
        record = await session.get(Finding, uuid.UUID(finding_id))
        record.deadline = deadline
        await session.commit()


async def _seed_scan_run(
    db_sessionmaker, *, project_id: str, target: str, completed_at, summary: dict, triggered_by
) -> str:
    async with db_sessionmaker() as session:
        record = ScanRun(
            project_id=uuid.UUID(project_id),
            triggered_by_user_id=triggered_by,
            scan_type="url_scan",
            target=target,
            status="completed",
            started_at=completed_at - timedelta(minutes=1),
            completed_at=completed_at,
            summary=summary,
        )
        session.add(record)
        await session.commit()
        return str(record.id)


# ---------------------------------------------------------------------------
# Security score formula - pure arithmetic, no DB involved.
# ---------------------------------------------------------------------------


def test_security_score_all_zero_is_100():
    assert _score_from_counts({"critical": 0, "high": 0, "medium": 0, "low": 0}) == 100


def test_security_score_single_critical():
    assert _score_from_counts({"critical": 1, "high": 0, "medium": 0, "low": 0}) == 85


def test_security_score_mixed_counts():
    # 2*15 + 3*8 + 1*3 + 5*1 = 30 + 24 + 3 + 5 = 62 -> 100 - 62 = 38
    counts = {"critical": 2, "high": 3, "medium": 1, "low": 5}
    assert _score_from_counts(counts) == 38


def test_security_score_clamped_at_zero_never_negative():
    # 7 criticals = 105 penalty, clamped to 100 -> score 0, not -5.
    counts = {"critical": 7, "high": 0, "medium": 0, "low": 0}
    assert _score_from_counts(counts) == 0


# ---------------------------------------------------------------------------
# Full dashboard aggregation - exact numbers against seeded rows.
# ---------------------------------------------------------------------------


async def test_dashboard_aggregates_exact_numbers(api_client, db_sessionmaker, switch_user):
    workspace = _create_workspace(api_client)
    project = _create_project(api_client, workspace["id"])
    project_id = project["id"]
    _add_member(api_client, project_id, TEST_USER_B.id, "developer")

    # F1: critical, left open.
    f1 = _create_finding(api_client, project_id, rule_id="f1", severity="critical", target="https://x/1")
    # F2: critical, confirmed (still non-terminal -> still "open").
    f2 = _create_finding(api_client, project_id, rule_id="f2", severity="critical", target="https://x/2")
    _transition(api_client, project_id, f2["id"], "confirmed")
    # F3: high, driven to "fixed" (non-terminal -> still "open"; also the
    # one and only "waiting_verify" finding).
    f3 = _create_finding(api_client, project_id, rule_id="f3", severity="high", target="https://x/3")
    _transition(api_client, project_id, f3["id"], "confirmed")
    _transition(api_client, project_id, f3["id"], "in_progress")
    _transition(api_client, project_id, f3["id"], "fixed")
    # F4: medium, driven all the way to "closed" (terminal -> NOT open;
    # this transition is what "fixed_this_week" counts).
    f4 = _create_finding(api_client, project_id, rule_id="f4", severity="medium", target="https://x/4")
    _transition(api_client, project_id, f4["id"], "confirmed")
    _transition(api_client, project_id, f4["id"], "in_progress")
    _transition(api_client, project_id, f4["id"], "fixed")
    _transition(api_client, project_id, f4["id"], "verified")
    _transition(api_client, project_id, f4["id"], "closed")
    # F5: low, dismissed as false_positive (terminal -> NOT open).
    f5 = _create_finding(api_client, project_id, rule_id="f5", severity="low", target="https://x/5")
    _transition(api_client, project_id, f5["id"], "false_positive", reason="Not exploitable")
    # F6: low, confirmed with a deadline forced into the past -> overdue,
    # and still non-terminal -> still "open".
    f6 = _create_finding(api_client, project_id, rule_id="f6", severity="low", target="https://x/6")
    _transition(api_client, project_id, f6["id"], "confirmed")
    await _force_deadline(
        db_sessionmaker, f6["id"], datetime.now(timezone.utc) - timedelta(hours=2)
    )

    # Assign F1 and F3 (both open) to TEST_USER_B.
    _set_assignee(api_client, project_id, f1["id"], TEST_USER_B.id)
    _set_assignee(api_client, project_id, f3["id"], TEST_USER_B.id)

    # Two completed scan runs to seed the trend series, oldest first.
    caller_id = uuid.UUID(project["owner_user_id"])
    older = await _seed_scan_run(
        db_sessionmaker,
        project_id=project_id,
        target="https://x/scan-1",
        completed_at=datetime.now(timezone.utc) - timedelta(days=2),
        summary={"critical": 1, "high": 0, "medium": 0, "low": 0},
        triggered_by=caller_id,
    )
    newer = await _seed_scan_run(
        db_sessionmaker,
        project_id=project_id,
        target="https://x/scan-2",
        completed_at=datetime.now(timezone.utc) - timedelta(hours=1),
        summary={"critical": 0, "high": 2, "medium": 1, "low": 0},
        triggered_by=caller_id,
    )

    response = api_client.get(f"/api/projects/{project_id}/dashboard")
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["project_id"] == project_id

    # Open findings: F1(critical), F2(critical), F3(high, fixed), F6(low,
    # confirmed) = 4. F4(closed) and F5(false_positive) excluded.
    assert body["open_by_severity"] == {"critical": 2, "high": 1, "medium": 0, "low": 1}
    assert body["open_findings"] == 4

    # security_score = 100 - min(100, 2*15 + 1*8 + 0*3 + 1*1) = 100 - 39 = 61
    assert body["security_score"] == 61

    assert body["waiting_verify"] == 1
    assert body["overdue"] == 1
    assert body["fixed_this_week"] == 1

    assert body["assigned_open"] == 2
    assert body["assigned_open_by_assignee"] == [
        {"assignee_user_id": str(TEST_USER_B.id), "open_count": 2}
    ]

    # Latest scan is the most recently completed one.
    assert body["latest_scan"]["id"] == newer
    assert body["latest_scan"]["status"] == "completed"
    assert body["latest_scan"]["target"] == "https://x/scan-2"

    # Trend: oldest first, each point's score from its own stored summary.
    trend = body["security_trend"]
    assert len(trend) == 2
    assert trend[0]["scan_run_id"] == older
    assert trend[0]["open_count"] == 1
    assert trend[0]["score"] == 85  # 100 - 1*15
    assert trend[1]["scan_run_id"] == newer
    assert trend[1]["open_count"] == 3
    assert trend[1]["score"] == 81  # 100 - (2*8 + 1*3) = 100 - 19

    # Top risks: critical-first, then high, then low - 4 open findings total.
    top_risk_ids = [item["id"] for item in body["top_risks"]]
    assert len(top_risk_ids) == 4
    assert set(top_risk_ids[:2]) == {f1["id"], f2["id"]}
    assert top_risk_ids[2] == f3["id"]
    assert top_risk_ids[3] == f6["id"]

    # Latest findings: 5 most recently created of the 6 total - f1 (the
    # very first created) is excluded, f6 (the last created) is included.
    latest_ids = [item["id"] for item in body["latest_findings"]]
    assert len(latest_ids) == 5
    assert f1["id"] not in latest_ids
    assert latest_ids[0] == f6["id"]


async def test_dashboard_with_no_data_is_all_zero_and_score_100(api_client):
    workspace = _create_workspace(api_client)
    project = _create_project(api_client, workspace["id"])

    response = api_client.get(f"/api/projects/{project['id']}/dashboard")
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["security_score"] == 100
    assert body["open_findings"] == 0
    assert body["open_by_severity"] == {"critical": 0, "high": 0, "medium": 0, "low": 0}
    assert body["waiting_verify"] == 0
    assert body["overdue"] == 0
    assert body["fixed_this_week"] == 0
    assert body["latest_scan"] is None
    assert body["security_trend"] == []
    assert body["top_risks"] == []
    assert body["latest_findings"] == []
    assert body["assigned_open"] == 0
    assert body["assigned_open_by_assignee"] == []


# ---------------------------------------------------------------------------
# Authorization
# ---------------------------------------------------------------------------


def test_viewer_can_read_the_dashboard(api_client, switch_user):
    workspace = _create_workspace(api_client)
    project = _create_project(api_client, workspace["id"])
    _add_member(api_client, project["id"], TEST_USER_B.id, "viewer")

    switch_user(TEST_USER_B)
    response = api_client.get(f"/api/projects/{project['id']}/dashboard")
    assert response.status_code == 200, response.text


def test_non_member_gets_404(api_client, switch_user):
    from backend.core.auth import AuthenticatedUser

    workspace = _create_workspace(api_client)
    project = _create_project(api_client, workspace["id"])

    outsider = AuthenticatedUser(id=uuid.uuid4(), role="authenticated", claims={})
    switch_user(outsider)
    response = api_client.get(f"/api/projects/{project['id']}/dashboard")
    assert response.status_code == 404


def test_requires_authentication(unauthenticated_client):
    response = unauthenticated_client.get(f"/api/projects/{uuid.uuid4()}/dashboard")
    assert response.status_code == 401
