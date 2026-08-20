"""API-level tests for project-scoped CVE risk prioritization (Task 6).

Enrichment providers (CVE lookup, EPSS, KEV) are swapped for fixtures/fakes
- mirroring backend/tests/test_cve_api.py's `_use_fixture_provider` pattern
- so these tests never touch the network."""
import uuid

from backend.database.models.rbac import UserRole
from backend.providers.cve.fixture import FixtureCVEProvider
from backend.providers.enrichment.base import EpssScore
from backend.services import project_cve as project_cve_module
from backend.services.cve import CveLookupService

from .conftest import TEST_USER_B


class FakeEpssProvider:
    def __init__(self, *, score=None):
        self._score = score

    async def get(self, cve_id: str):
        if self._score is None:
            return None
        return EpssScore(cve_id=cve_id.upper(), score=self._score, percentile=self._score)


class FakeKevProvider:
    def __init__(self, *, is_kev: bool = False):
        self._is_kev = is_kev

    async def is_kev(self, cve_id: str) -> bool:
        return self._is_kev

    async def get(self, cve_id: str) -> bool:
        return self._is_kev


def _wire_fixtures(monkeypatch, *, epss_score=None, is_kev=False):
    monkeypatch.setattr(
        project_cve_module,
        "CveLookupService",
        lambda *a, **k: CveLookupService(provider=FixtureCVEProvider()),
    )
    monkeypatch.setattr("backend.services.cve.get_redis", lambda: None)
    epss = FakeEpssProvider(score=epss_score)
    kev = FakeKevProvider(is_kev=is_kev)
    monkeypatch.setattr(project_cve_module, "get_epss_provider", lambda: epss)
    monkeypatch.setattr(project_cve_module, "get_kev_provider", lambda: kev)


async def _seed_role(db_sessionmaker, user_id, *, role="user", is_active=True):
    async with db_sessionmaker() as session:
        session.add(UserRole(user_id=user_id, role=role, is_active=is_active))
        await session.commit()


def _create_workspace(api_client) -> dict:
    return api_client.post(
        "/api/workspaces", json={"name": "Acme Corp Security", "description": None}
    ).json()


def _create_project(api_client, workspace_id: str, **overrides) -> dict:
    payload = {
        "workspace_id": workspace_id,
        "name": "Customer Portal",
        "environment": "production",
        "criticality": "critical",
        "internet_facing": True,
    }
    payload.update(overrides)
    return api_client.post("/api/projects", json=payload).json()


def _add_member(api_client, project_id: str, user_id, role: str) -> None:
    response = api_client.post(
        f"/api/projects/{project_id}/members",
        json={"user_id": str(user_id), "project_role": role},
    )
    assert response.status_code == 201, response.text


# ─── Successful assessment end-to-end ───────────────────────────────────────


def test_owner_can_assess_a_cve(api_client, monkeypatch):
    _wire_fixtures(monkeypatch, epss_score=0.94427, is_kev=True)
    workspace = _create_workspace(api_client)
    project = _create_project(api_client, workspace["id"])

    response = api_client.post(
        f"/api/projects/{project['id']}/cve-assessments",
        json={"cve_id": "CVE-2021-44228", "affected_version": "2.14.1"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["cve_id"] == "CVE-2021-44228"
    assert body["cvss_score"] == 10.0
    assert body["epss_score"] == 0.94427
    assert body["is_kev"] is True
    # is_kev + internet_facing (project default True) -> patch_now (rule 2).
    assert body["priority"] == "patch_now"
    assert body["score"] >= 8.5
    assert "reasoning" in body["rationale"]
    assert body["finding_id"] is not None


def test_assessment_without_kev_or_high_cvss_does_not_auto_create_a_finding(api_client, monkeypatch):
    _wire_fixtures(monkeypatch, epss_score=0.01, is_kev=False)
    workspace = _create_workspace(api_client)
    project = _create_project(api_client, workspace["id"], criticality="low", internet_facing=False)

    response = api_client.post(
        f"/api/projects/{project['id']}/cve-assessments",
        json={"cve_id": "CVE-2021-44228", "affected_version": None},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    # CVSS 10.0 still triggers rule 3's patch_now (epss known but <0.5, not
    # kev - so rule 3's OR fails: cvss>=9.0 needs kev/epss>=0.5/epss None,
    # none apply, falls through to composite bucket).
    assert body["priority"] != "patch_now"
    assert body["finding_id"] is None


# ─── Re-assessment upsert behaviour ─────────────────────────────────────────


def test_reassessing_the_same_cve_updates_rather_than_duplicates(api_client, monkeypatch):
    _wire_fixtures(monkeypatch, epss_score=0.01, is_kev=False)
    workspace = _create_workspace(api_client)
    project = _create_project(api_client, workspace["id"], criticality="low", internet_facing=False)

    first = api_client.post(
        f"/api/projects/{project['id']}/cve-assessments",
        json={"cve_id": "CVE-2021-44228"},
    ).json()

    # Re-assess with KEV now true (simulating new intel) - the score/priority
    # must change and update in place.
    monkeypatch.setattr(project_cve_module, "get_kev_provider", lambda: FakeKevProvider(is_kev=True))
    second = api_client.post(
        f"/api/projects/{project['id']}/cve-assessments",
        json={"cve_id": "CVE-2021-44228"},
    ).json()

    assert first["id"] == second["id"]
    assert second["is_kev"] is True

    listing = api_client.get(f"/api/projects/{project['id']}/cve-assessments").json()
    assert len(listing) == 1


# ─── Auto-Finding creation for patch_now/high ───────────────────────────────


def test_patch_now_assessment_auto_creates_a_finding_with_expected_shape(api_client, monkeypatch):
    _wire_fixtures(monkeypatch, epss_score=0.9, is_kev=True)
    workspace = _create_workspace(api_client)
    project = _create_project(api_client, workspace["id"])

    response = api_client.post(
        f"/api/projects/{project['id']}/cve-assessments",
        json={"cve_id": "CVE-2021-44228"},
    )
    body = response.json()
    finding_id = body["finding_id"]
    assert finding_id is not None

    findings = api_client.get(f"/api/projects/{project['id']}/findings").json()
    matches = [f for f in findings["items"] if f["id"] == finding_id]
    assert len(matches) == 1
    finding = matches[0]
    assert finding["cve_id"] == "CVE-2021-44228"
    assert finding["severity"] == "critical"
    assert finding["status"] == "open"
    assert finding["scan_run_id"] is None


def test_reassessment_reuses_existing_finding_instead_of_duplicating(api_client, monkeypatch):
    _wire_fixtures(monkeypatch, epss_score=0.9, is_kev=True)
    workspace = _create_workspace(api_client)
    project = _create_project(api_client, workspace["id"])

    first = api_client.post(
        f"/api/projects/{project['id']}/cve-assessments",
        json={"cve_id": "CVE-2021-44228"},
    ).json()
    second = api_client.post(
        f"/api/projects/{project['id']}/cve-assessments",
        json={"cve_id": "CVE-2021-44228"},
    ).json()

    assert first["finding_id"] == second["finding_id"]

    findings = api_client.get(f"/api/projects/{project['id']}/findings").json()
    cve_findings = [f for f in findings["items"] if f["cve_id"] == "CVE-2021-44228"]
    assert len(cve_findings) == 1


# ─── Authorization ───────────────────────────────────────────────────────


def test_developer_cannot_trigger_an_assessment(api_client, switch_user, monkeypatch):
    _wire_fixtures(monkeypatch, epss_score=0.1, is_kev=False)
    workspace = _create_workspace(api_client)
    project = _create_project(api_client, workspace["id"])
    _add_member(api_client, project["id"], TEST_USER_B.id, "developer")

    switch_user(TEST_USER_B)
    response = api_client.post(
        f"/api/projects/{project['id']}/cve-assessments",
        json={"cve_id": "CVE-2021-44228"},
    )
    assert response.status_code == 403


def test_viewer_cannot_trigger_an_assessment(api_client, switch_user, monkeypatch):
    _wire_fixtures(monkeypatch, epss_score=0.1, is_kev=False)
    workspace = _create_workspace(api_client)
    project = _create_project(api_client, workspace["id"])
    _add_member(api_client, project["id"], TEST_USER_B.id, "viewer")

    switch_user(TEST_USER_B)
    response = api_client.post(
        f"/api/projects/{project['id']}/cve-assessments",
        json={"cve_id": "CVE-2021-44228"},
    )
    assert response.status_code == 403


def test_security_role_can_trigger_an_assessment(api_client, switch_user, monkeypatch):
    _wire_fixtures(monkeypatch, epss_score=0.1, is_kev=False)
    workspace = _create_workspace(api_client)
    project = _create_project(api_client, workspace["id"])
    _add_member(api_client, project["id"], TEST_USER_B.id, "security")

    switch_user(TEST_USER_B)
    response = api_client.post(
        f"/api/projects/{project['id']}/cve-assessments",
        json={"cve_id": "CVE-2021-44228"},
    )
    assert response.status_code == 201


def test_every_member_role_can_list_assessments(api_client, switch_user, monkeypatch):
    _wire_fixtures(monkeypatch, epss_score=0.1, is_kev=False)
    workspace = _create_workspace(api_client)
    project = _create_project(api_client, workspace["id"])
    api_client.post(
        f"/api/projects/{project['id']}/cve-assessments", json={"cve_id": "CVE-2021-44228"}
    )
    _add_member(api_client, project["id"], TEST_USER_B.id, "viewer")

    switch_user(TEST_USER_B)
    response = api_client.get(f"/api/projects/{project['id']}/cve-assessments")
    assert response.status_code == 200
    assert len(response.json()) == 1


def test_assessment_requires_authentication(unauthenticated_client):
    response = unauthenticated_client.post(
        f"/api/projects/{uuid.uuid4()}/cve-assessments", json={"cve_id": "CVE-2021-44228"}
    )
    assert response.status_code == 401


# ─── Detail lookup ───────────────────────────────────────────────────────


def test_get_assessment_detail(api_client, monkeypatch):
    _wire_fixtures(monkeypatch, epss_score=0.1, is_kev=False)
    workspace = _create_workspace(api_client)
    project = _create_project(api_client, workspace["id"])
    api_client.post(
        f"/api/projects/{project['id']}/cve-assessments", json={"cve_id": "CVE-2021-44228"}
    )

    response = api_client.get(f"/api/projects/{project['id']}/cve-assessments/CVE-2021-44228")
    assert response.status_code == 200
    assert response.json()["cve_id"] == "CVE-2021-44228"


def test_get_assessment_detail_404_when_not_yet_assessed(api_client, monkeypatch):
    _wire_fixtures(monkeypatch, epss_score=0.1, is_kev=False)
    workspace = _create_workspace(api_client)
    project = _create_project(api_client, workspace["id"])

    response = api_client.get(f"/api/projects/{project['id']}/cve-assessments/CVE-2099-99999")
    assert response.status_code == 404
