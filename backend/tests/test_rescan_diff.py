"""Rescan diff scenario tests - one (or more) test per row of the Task 3
decision table (see backend/services/rescan_diff.py's module docstring for
the full table and its derivation).

| Fingerprint in new scan? | In previous-live set? | Existing Finding status | Action | Diff label |
|---|---|---|---|---|
| yes | yes | any ("live") | update last_seen only | still_open |
| yes | no | (none exists) | create Finding(open) | new / new_regression |
| yes | no | fixed | auto-transition fixed->reopened | reopened_regression |
| yes | no | false_positive / accepted_risk | no change | regressed_but_dismissed |
| yes | no | closed | no change | regressed_after_close |
| yes | no | open/confirmed/in_progress/reopened | update last_seen only | still_open |
| no | yes | fixed | no change (awaiting verify) | fixed_pending_verify |
| no | yes | open/confirmed/in_progress/reopened | no change | absent_unconfirmed |

Every test drives the real ``POST /api/projects/{id}/scans`` endpoint (not
the orchestrator/diff module directly) so the whole path - auto-chained
``previous_scan_run_id``, Finding creation/touch, the automatic
``fixed -> reopened`` transition and its ``FindingTransition`` row - is
exercised exactly as a real caller would hit it.
"""
import uuid

from backend.services import scan_orchestrator as scan_orchestrator_module

from .conftest import TEST_USER_A


def _create_workspace(api_client) -> dict:
    return api_client.post(
        "/api/workspaces", json={"name": "Acme Corp Security", "description": None}
    ).json()


def _create_project(api_client, workspace_id: str) -> dict:
    return api_client.post(
        "/api/projects",
        json={
            "workspace_id": workspace_id,
            "name": "Customer Portal",
            "environment": "production",
            "criticality": "high",
            "internet_facing": True,
        },
    ).json()


def _finding_item(code: str, **overrides) -> dict:
    base = {"code": code, "severity": "medium", "message": f"{code} detected.", "weight": 20}
    base.update(overrides)
    return base


def _scan_result(items: list[dict]) -> dict:
    return {
        "url": "https://example.com",
        "normalized_url": "https://example.com/",
        "hostname": "example.com",
        "port": 443,
        "scheme": "https",
        "has_https": True,
        "reachable": True,
        "status": "suspicious" if items else "clean",
        "risk_score": 10 * len(items),
        "severity": "medium",
        "http_status": 200,
        "final_url": "https://example.com/",
        "redirect_chain": [],
        "redirect_count": 0,
        "headers": {},
        "body_truncated": False,
        "failure_reason": None,
        "findings": items,
        "recommendations": [],
        "reputation": {"configured": False},
        "duration_ms": 5.0,
    }


def _patch_scan_sequence(monkeypatch, *item_lists: list[dict]):
    """Each successive call to ``scan_url`` returns the next entry in
    ``item_lists`` (the last entry repeats once exhausted, matching "the
    scanner returns the same thing forever" for tests that only care about
    the first N calls)."""
    calls = {"n": 0}

    async def fake_scan_url(raw_url: str, **kwargs):
        index = min(calls["n"], len(item_lists) - 1)
        calls["n"] += 1
        return _scan_result(item_lists[index])

    monkeypatch.setattr(scan_orchestrator_module, "scan_url", fake_scan_url)


def _run_scan(api_client, project_id: str) -> dict:
    response = api_client.post(
        f"/api/projects/{project_id}/scans", json={"target": "https://example.com"}
    )
    assert response.status_code == 201, response.text
    return response.json()


def _finding_by_rule(api_client, project_id: str, rule_id: str) -> dict:
    findings = api_client.get(f"/api/projects/{project_id}/findings").json()["items"]
    matches = [item for item in findings if item["rule_id"] == rule_id]
    assert len(matches) == 1, f"expected exactly one finding for rule {rule_id!r}, got {matches}"
    return matches[0]


def _transition(api_client, project_id: str, finding_id: str, to_status: str, reason=None) -> dict:
    body = {"to_status": to_status}
    if reason is not None:
        body["reason"] = reason
    response = api_client.post(
        f"/api/projects/{project_id}/findings/{finding_id}/transition", json=body
    )
    assert response.status_code == 200, response.text
    return response.json()


# ─── yes/no (none exists) -> new / new_regression ──────────────────────────


def test_first_scan_with_no_previous_run_labels_findings_new(api_client, monkeypatch):
    workspace = _create_workspace(api_client)
    project = _create_project(api_client, workspace["id"])
    _patch_scan_sequence(monkeypatch, [_finding_item("no_https")])

    scan = _run_scan(api_client, project["id"])
    assert scan["previous_scan_run_id"] is None
    diff = scan["summary"]["diff"]
    assert len(diff["new"]) == 1
    assert diff["new_regression"] == []


def test_a_new_fingerprint_on_a_later_scan_is_new_regression(api_client, monkeypatch):
    workspace = _create_workspace(api_client)
    project = _create_project(api_client, workspace["id"])
    _patch_scan_sequence(
        monkeypatch,
        [_finding_item("no_https")],
        [_finding_item("no_https"), _finding_item("long_url")],
    )

    _run_scan(api_client, project["id"])
    second = _run_scan(api_client, project["id"])
    assert second["previous_scan_run_id"] is not None

    diff = second["summary"]["diff"]
    assert len(diff["new_regression"]) == 1
    assert diff["new"] == []
    long_url_finding = _finding_by_rule(api_client, project["id"], "long_url")
    assert long_url_finding["id"] in diff["new_regression"]
    assert long_url_finding["status"] == "open"


# ─── yes/yes -> still_open ───────────────────────────────────────────────


def test_fingerprint_present_in_both_scans_is_still_open(api_client, monkeypatch):
    workspace = _create_workspace(api_client)
    project = _create_project(api_client, workspace["id"])
    _patch_scan_sequence(monkeypatch, [_finding_item("no_https")])

    first = _run_scan(api_client, project["id"])
    second = _run_scan(api_client, project["id"])

    finding = _finding_by_rule(api_client, project["id"], "no_https")
    assert finding["status"] == "open"
    assert finding["last_seen_scan_run_id"] == second["id"]
    assert finding["first_seen_scan_run_id"] == first["id"]

    diff = second["summary"]["diff"]
    assert finding["id"] in diff["still_open"]
    assert diff["new"] == []
    assert diff["new_regression"] == []


def test_open_finding_re_encountered_after_a_scan_gap_is_still_open_via_existing_lookup(
    api_client, monkeypatch
):
    # Fingerprint absent for one scan (still open, absent_unconfirmed), then
    # reappears on the scan after that - reached via the "existing Finding
    # row lookup" branch (its last_seen_scan_run_id predates the
    # immediately-preceding scan), not the previous-live-intersection
    # branch, but must land in the same still_open bucket either way.
    workspace = _create_workspace(api_client)
    project = _create_project(api_client, workspace["id"])
    _patch_scan_sequence(
        monkeypatch,
        [_finding_item("no_https")],
        [],
        [_finding_item("no_https")],
    )

    _run_scan(api_client, project["id"])
    _run_scan(api_client, project["id"])
    third = _run_scan(api_client, project["id"])

    finding = _finding_by_rule(api_client, project["id"], "no_https")
    assert finding["status"] == "open"
    assert finding["last_seen_scan_run_id"] == third["id"]
    assert finding["id"] in third["summary"]["diff"]["still_open"]


# ─── yes/no, existing fixed -> auto-reopen ─────────────────────────────────


async def test_fixed_finding_whose_fingerprint_reappears_auto_reopens(
    api_client, db_sessionmaker, monkeypatch
):
    workspace = _create_workspace(api_client)
    project = _create_project(api_client, workspace["id"])
    _patch_scan_sequence(
        monkeypatch,
        [_finding_item("no_https")],
        [],
        [_finding_item("no_https")],
    )

    _run_scan(api_client, project["id"])
    finding = _finding_by_rule(api_client, project["id"], "no_https")
    _transition(api_client, project["id"], finding["id"], "confirmed")
    _transition(api_client, project["id"], finding["id"], "in_progress")
    _transition(api_client, project["id"], finding["id"], "fixed")

    _run_scan(api_client, project["id"])  # fingerprint absent - stays fixed
    still_fixed = _finding_by_rule(api_client, project["id"], "no_https")
    assert still_fixed["status"] == "fixed"

    third = _run_scan(api_client, project["id"])  # fingerprint reappears
    reopened = _finding_by_rule(api_client, project["id"], "no_https")
    assert reopened["status"] == "reopened"
    assert reopened["last_seen_scan_run_id"] == third["id"]

    diff = third["summary"]["diff"]
    assert reopened["id"] in diff["reopened_regression"]

    # The FindingTransition row: actor is the scan-triggering user (no
    # separate "system" identity exists in this codebase), reason is
    # "rescan_regression", and it is a real row alongside the earlier
    # human-initiated transitions.
    from backend.repositories.findings import FindingRepository

    async with db_sessionmaker() as session:
        repo = FindingRepository(session)
        rows = await repo.list_transitions(uuid.UUID(reopened["id"]))

    auto_row = next(row for row in rows if row.to_status == "reopened")
    assert auto_row.from_status == "fixed"
    assert auto_row.reason == "rescan_regression"
    assert str(auto_row.actor_user_id) == str(TEST_USER_A.id)
    assert auto_row.meta.get("diff_label") == "reopened_regression"


# ─── no/yes, fixed -> fixed_pending_verify (no auto-verify) ────────────────


def test_fixed_finding_whose_fingerprint_disappears_stays_fixed_pending_verify(
    api_client, monkeypatch
):
    workspace = _create_workspace(api_client)
    project = _create_project(api_client, workspace["id"])
    _patch_scan_sequence(monkeypatch, [_finding_item("no_https")], [])

    _run_scan(api_client, project["id"])
    finding = _finding_by_rule(api_client, project["id"], "no_https")
    _transition(api_client, project["id"], finding["id"], "confirmed")
    _transition(api_client, project["id"], finding["id"], "in_progress")
    _transition(api_client, project["id"], finding["id"], "fixed")
    fixed_last_seen = _finding_by_rule(api_client, project["id"], "no_https")[
        "last_seen_scan_run_id"
    ]

    second = _run_scan(api_client, project["id"])  # fingerprint absent this time

    after = _finding_by_rule(api_client, project["id"], "no_https")
    assert after["status"] == "fixed"  # NOT auto-verified
    assert after["last_seen_scan_run_id"] == fixed_last_seen  # untouched

    diff = second["summary"]["diff"]
    assert after["id"] in diff["fixed_pending_verify"]
    assert diff["absent_unconfirmed"] == []


# ─── no/yes, open-like -> absent_unconfirmed (no auto-close) ───────────────


def test_open_finding_whose_fingerprint_disappears_stays_open_absent_unconfirmed(
    api_client, monkeypatch
):
    workspace = _create_workspace(api_client)
    project = _create_project(api_client, workspace["id"])
    _patch_scan_sequence(monkeypatch, [_finding_item("no_https")], [])

    first = _run_scan(api_client, project["id"])
    second = _run_scan(api_client, project["id"])

    finding = _finding_by_rule(api_client, project["id"], "no_https")
    assert finding["status"] == "open"  # NOT auto-closed
    assert finding["last_seen_scan_run_id"] == first["id"]  # untouched

    diff = second["summary"]["diff"]
    assert finding["id"] in diff["absent_unconfirmed"]
    assert diff["fixed_pending_verify"] == []


def test_in_progress_finding_whose_fingerprint_disappears_stays_in_progress(
    api_client, monkeypatch
):
    workspace = _create_workspace(api_client)
    project = _create_project(api_client, workspace["id"])
    _patch_scan_sequence(monkeypatch, [_finding_item("no_https")], [])

    _run_scan(api_client, project["id"])
    finding = _finding_by_rule(api_client, project["id"], "no_https")
    _transition(api_client, project["id"], finding["id"], "confirmed")
    _transition(api_client, project["id"], finding["id"], "in_progress")

    second = _run_scan(api_client, project["id"])

    after = _finding_by_rule(api_client, project["id"], "no_https")
    assert after["status"] == "in_progress"
    diff = second["summary"]["diff"]
    assert after["id"] in diff["absent_unconfirmed"]


# ─── yes/no, existing false_positive/accepted_risk/closed -> no auto-reopen ─


def test_false_positive_finding_reappearing_does_not_auto_reopen(api_client, monkeypatch):
    workspace = _create_workspace(api_client)
    project = _create_project(api_client, workspace["id"])
    _patch_scan_sequence(
        monkeypatch, [_finding_item("no_https")], [], [_finding_item("no_https")]
    )

    _run_scan(api_client, project["id"])
    finding = _finding_by_rule(api_client, project["id"], "no_https")
    _transition(
        api_client, project["id"], finding["id"], "false_positive", reason="Confirmed benign."
    )

    _run_scan(api_client, project["id"])  # absent - false_positive is not "live"
    third = _run_scan(api_client, project["id"])  # reappears

    after = _finding_by_rule(api_client, project["id"], "no_https")
    assert after["status"] == "false_positive"  # NOT reopened
    diff = third["summary"]["diff"]
    assert after["id"] in diff["regressed_but_dismissed"]
    assert diff["reopened_regression"] == []


def test_accepted_risk_finding_reappearing_does_not_auto_reopen(api_client, monkeypatch):
    workspace = _create_workspace(api_client)
    project = _create_project(api_client, workspace["id"])
    _patch_scan_sequence(
        monkeypatch, [_finding_item("no_https")], [], [_finding_item("no_https")]
    )

    _run_scan(api_client, project["id"])
    finding = _finding_by_rule(api_client, project["id"], "no_https")
    _transition(
        api_client, project["id"], finding["id"], "accepted_risk", reason="Risk accepted by CISO."
    )

    _run_scan(api_client, project["id"])
    third = _run_scan(api_client, project["id"])

    after = _finding_by_rule(api_client, project["id"], "no_https")
    assert after["status"] == "accepted_risk"  # NOT reopened
    diff = third["summary"]["diff"]
    assert after["id"] in diff["regressed_but_dismissed"]
    assert diff["reopened_regression"] == []


def test_closed_finding_reappearing_does_not_auto_reopen(api_client, monkeypatch):
    workspace = _create_workspace(api_client)
    project = _create_project(api_client, workspace["id"])
    _patch_scan_sequence(
        monkeypatch, [_finding_item("no_https")], [], [_finding_item("no_https")]
    )

    _run_scan(api_client, project["id"])
    finding = _finding_by_rule(api_client, project["id"], "no_https")
    _transition(api_client, project["id"], finding["id"], "confirmed")
    _transition(api_client, project["id"], finding["id"], "in_progress")
    _transition(api_client, project["id"], finding["id"], "fixed")
    _transition(api_client, project["id"], finding["id"], "verified")
    _transition(api_client, project["id"], finding["id"], "closed")

    _run_scan(api_client, project["id"])  # absent - closed is not "live"
    third = _run_scan(api_client, project["id"])  # reappears

    after = _finding_by_rule(api_client, project["id"], "no_https")
    assert after["status"] == "closed"  # NOT reopened
    diff = third["summary"]["diff"]
    assert after["id"] in diff["regressed_after_close"]
    assert diff["reopened_regression"] == []
    assert after["closed_at"] is not None
