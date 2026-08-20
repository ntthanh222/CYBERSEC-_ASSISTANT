"""Task 8: AI Project Security Copilot - end-to-end wiring through the real
``POST /api/chatbot/chat`` endpoint.

Complements ``test_tool_router_project_authorization.py`` (which exercises
every new handler directly): this file verifies the full pipeline wiring -
the ``project_id`` request field reaches ``AssistantService.chat()`` and
``AppDataToolRouter.try_route()`` correctly, ``project_id=None`` changes
nothing about existing behavior, and citations/metadata still work when the
tool-route metadata comes from a new project-context handler.
"""
import uuid

from backend.database.models.cve_assessment import CveAssessment
from backend.database.models.finding import Finding
from backend.database.models.project import Project, ProjectMember
from backend.database.models.rbac import UserRole
from backend.database.models.sla_policy import SlaPolicy
from backend.database.models.workspace import Workspace
from backend.tests.conftest import TEST_USER_A


async def _seed_project(session, *, creator_id=None, add_member=True):
    creator_id = creator_id or uuid.uuid4()
    workspace = Workspace(name="W", created_by_user_id=creator_id)
    session.add(workspace)
    await session.flush()
    project = Project(
        workspace_id=workspace.id,
        name="Checkout Service",
        environment="production",
        criticality="critical",
        internet_facing=True,
        owner_user_id=creator_id,
    )
    session.add(project)
    await session.flush()
    if add_member:
        session.add(
            ProjectMember(project_id=project.id, user_id=TEST_USER_A.id, project_role="security")
        )
    await session.commit()
    return project


async def _seed_finding(session, *, project_id, **kwargs):
    defaults = dict(
        project_id=project_id,
        scan_run_id=None,
        fingerprint=f"fp-{uuid.uuid4()}",
        rule_id="rule-1",
        category="vuln",
        title="SQL Injection in /checkout",
        evidence="e",
        impact="i",
        remediation="r",
        severity="critical",
        status="open",
        target="checkout.example.com",
    )
    defaults.update(kwargs)
    finding = Finding(**defaults)
    session.add(finding)
    await session.commit()
    return finding


async def _make_admin(session, user_id):
    session.add(UserRole(user_id=user_id, role="admin", is_active=True))
    await session.commit()


# ---------------------------------------------------------------------------
# project_id=None: zero regression
# ---------------------------------------------------------------------------


def test_no_project_id_field_behaves_like_before(api_client):
    """Omitting project_id entirely (the pre-Task-8 request shape) still
    works and never engages a project-context handler."""
    response = api_client.post("/api/chatbot/chat", json={"message": "What is SSRF?"})
    assert response.status_code == 200
    body = response.json()
    assert body["metadata"].get("tool_name") not in {
        "project_status",
        "findings_priority",
        "assignment",
        "overdue",
        "rescan_history",
        "cve_priority",
        "policy",
    }


def test_explicit_null_project_id_behaves_like_before(api_client):
    response = api_client.post(
        "/api/chatbot/chat", json={"message": "What is SSRF?", "project_id": None}
    )
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# project_id set: routes to the new handlers, citations/metadata intact
# ---------------------------------------------------------------------------


async def test_project_status_question_routes_to_new_handler(api_client, db_sessionmaker):
    async with db_sessionmaker() as session:
        project = await _seed_project(session)
        await _seed_finding(session, project_id=project.id)

    response = api_client.post(
        "/api/chatbot/chat",
        json={
            "message": "Project này có vấn đề gì không?",
            "project_id": str(project.id),
            "mode": "fast",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["metadata"]["tool_name"] == "project_status"
    assert body["provider"] == "local"
    assert "Checkout Service" in body["content"]
    # metadata shape matches existing tool-route handlers exactly - the
    # citation-building code in assistant.py needs no changes for this.
    assert body["metadata"]["gemini_called"] is False
    assert body["citations"] == []


async def test_non_member_gets_explicit_denial_not_generic_fallback(api_client, db_sessionmaker):
    async with db_sessionmaker() as session:
        project = await _seed_project(session, add_member=False)

    response = api_client.post(
        "/api/chatbot/chat",
        json={
            "message": "Project này có vấn đề gì không?",
            "project_id": str(project.id),
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["content"] == "Bạn không có quyền truy cập project này."
    assert body["metadata"]["routing_reason"] == "project_access_denied"


async def test_nonexistent_project_id_gets_not_found_message(api_client):
    response = api_client.post(
        "/api/chatbot/chat",
        json={"message": "Project này có vấn đề gì không?", "project_id": str(uuid.uuid4())},
    )
    assert response.status_code == 200
    body = response.json()
    assert "Không tìm thấy project" in body["content"]
    assert body["metadata"]["routing_reason"] == "project_not_found"


async def test_global_admin_bypasses_without_membership_over_http(api_client, db_sessionmaker):
    async with db_sessionmaker() as session:
        project = await _seed_project(session, add_member=False)
        await _make_admin(session, TEST_USER_A.id)

    response = api_client.post(
        "/api/chatbot/chat",
        json={"message": "Project này có vấn đề gì không?", "project_id": str(project.id)},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["content"] != "Bạn không có quyền truy cập project này."
    assert "Checkout Service" in body["content"]


# ---------------------------------------------------------------------------
# Scenario tests matching the plan's example questions - one per type,
# asserting on the deterministic tool-route metadata/content (never on
# non-deterministic LLM prose).
# ---------------------------------------------------------------------------


async def test_what_to_fix_first_question(api_client, db_sessionmaker):
    async with db_sessionmaker() as session:
        project = await _seed_project(session)
        await _seed_finding(session, project_id=project.id, severity="critical")

    response = api_client.post(
        "/api/chatbot/chat",
        json={"message": "Tôi nên sửa gì trước?", "project_id": str(project.id)},
    )
    body = response.json()
    assert body["metadata"]["tool_name"] == "findings_priority"
    assert "SQL Injection" in body["content"]


async def test_whos_working_on_it_question(api_client, db_sessionmaker):
    async with db_sessionmaker() as session:
        project = await _seed_project(session)
        await _seed_finding(
            session, project_id=project.id, assignee_user_id=TEST_USER_A.id, status="in_progress"
        )

    response = api_client.post(
        "/api/chatbot/chat",
        json={"message": "Ai đang xử lý lỗi này?", "project_id": str(project.id)},
    )
    body = response.json()
    assert body["metadata"]["tool_name"] == "assignment"
    assert str(TEST_USER_A.id) in body["content"]


async def test_whats_overdue_question(api_client, db_sessionmaker):
    from datetime import datetime, timedelta, timezone

    async with db_sessionmaker() as session:
        project = await _seed_project(session)
        finding = await _seed_finding(session, project_id=project.id, status="confirmed")
        finding.deadline = datetime.now(timezone.utc) - timedelta(hours=10)
        await session.commit()

    response = api_client.post(
        "/api/chatbot/chat",
        json={"message": "Có gì đang quá hạn không?", "project_id": str(project.id)},
    )
    body = response.json()
    assert body["metadata"]["tool_name"] == "overdue"
    assert "SQL Injection" in body["content"]


async def test_was_this_fixed_question(api_client, db_sessionmaker):
    async with db_sessionmaker() as session:
        project = await _seed_project(session)
        await _seed_finding(
            session, project_id=project.id, cve_id="CVE-2021-44228", status="closed"
        )

    response = api_client.post(
        "/api/chatbot/chat",
        json={
            "message": "CVE-2021-44228 đã sửa chưa?",
            "project_id": str(project.id),
        },
    )
    body = response.json()
    assert body["metadata"]["tool_name"] == "rescan_history"
    assert "closed" in body["content"]


async def test_how_to_fix_cve_question(api_client, db_sessionmaker):
    async with db_sessionmaker() as session:
        project = await _seed_project(session)
        session.add(
            CveAssessment(
                project_id=project.id,
                cve_id="CVE-2021-44228",
                cvss_score=9.8,
                epss_score=0.9,
                is_kev=True,
                priority="patch_now",
                score=9.5,
                rationale={"reasoning": "Actively exploited and internet-facing."},
            )
        )
        await session.commit()

    response = api_client.post(
        "/api/chatbot/chat",
        json={"message": "CVE-2021-44228 nên xử lý thế nào?", "project_id": str(project.id)},
    )
    body = response.json()
    assert body["metadata"]["tool_name"] == "cve_priority"
    assert "patch_now" in body["content"]


async def test_what_does_policy_say_question(api_client, db_sessionmaker):
    async with db_sessionmaker() as session:
        project = await _seed_project(session)
        session.add(SlaPolicy(project_id=None, severity="critical", hours_to_deadline=24))
        await session.commit()

    response = api_client.post(
        "/api/chatbot/chat",
        json={"message": "Chính sách SLA của project này là gì?", "project_id": str(project.id)},
    )
    body = response.json()
    assert body["metadata"]["tool_name"] == "policy"
    assert "24" in body["content"]


# ---------------------------------------------------------------------------
# Security-review fix round 2 regression test: the RLS-session finding was
# NOT actually fixed by round 1's `authz_session: AsyncSession =
# Depends(get_db)` parameter, because `get_rls_db` is itself implemented as
# `get_rls_db(session: AsyncSession = Depends(get_db))` and FastAPI caches a
# dependency's resolved value per request by callable identity - both
# `Depends(get_db)` call sites silently collapsed onto the same cached,
# already-RLS-touched session object. This test exercises the REAL route
# via TestClient (never a hand-built AppDataToolRouter construction, which
# is exactly what let the round-1 defect slip through its own test).
#
# IMPORTANT SUBTLETY (found in round 2's own first attempt at this test):
# `conftest.py`'s `api_client` fixture overrides `get_rls_db` itself with a
# SQLite stand-in (`_make_override_get_rls_db`) that has NO `Depends(get_db)`
# sub-parameter at all - it calls `override_get_db()` directly as a plain
# Python coroutine, bypassing FastAPI's dependency graph/cache for `get_db`
# entirely on that path. That flattened shape structurally CANNOT reproduce
# the collapse bug (there is no nested `Depends(get_db)` for the route's own
# `authz_session: Depends(get_db)` to collide with), so a test built
# directly on top of the default `api_client` fixture passes vacuously
# regardless of whether `use_cache=False` is present - confirmed by manually
# reverting the fix and re-running this exact test shape, which still
# passed. This test instead overrides `get_rls_db` with a STRUCTURALLY
# faithful stand-in - `async def faithful_get_rls_db(session:
# AsyncSession = Depends(get_db)): yield session` - identical in shape to
# the real `backend.database.session.get_rls_db` (same nested
# `Depends(get_db)`), just without the Postgres-only `SET LOCAL`/
# `set_config` calls SQLite cannot execute. This reproduces the exact
# dependency-graph shape that causes the collapse (verified with a
# standalone FastAPI+TestClient script during development: the faithful
# shape collapses under default caching and stays genuinely separate with
# `use_cache=False`, exactly matching production's `get_rls_db`).
# ---------------------------------------------------------------------------


async def test_chat_route_forbidden_message_reachable_with_real_rls_session_wiring(
    api_client, db_sessionmaker, monkeypatch
):
    """Proves two things through the real FastAPI dependency-injection path,
    with `get_rls_db` replaced by a structurally faithful (shape-identical)
    stand-in so the real collapse-prone dependency graph is exercised:

    1. The `session` and `authz_session` objects `AppDataToolRouter`
       actually receives for one real `/api/chatbot/chat` request are
       genuinely different Python objects (not the same session collapsed
       by FastAPI's dependency cache).
    2. Because of that, a non-member caller gets the mandated FORBIDDEN
       message, not NOT_FOUND - even when `ProjectRepository.get` is
       patched to return None for exactly the session object standing in
       for the RLS-scoped connection (simulating, at the precise point real
       Postgres RLS would intervene, "this session cannot see the row" -
       SQLite has no real RLS to enforce, so this is the closest faithful
       simulation available in the unit-test suite; real Postgres RLS
       end-to-end coverage lives in test_live_postgres_integration.py).

    If `authz_session` ever regresses to being the same object as
    `session` again (e.g. someone removes `use_cache=False`), both
    assertions below fail: the identity check directly, and
    `ProjectRepository.get` (patched below) returns None for that shared
    object too, producing the NOT_FOUND message instead of FORBIDDEN.
    """
    from fastapi import Depends
    from sqlalchemy.ext.asyncio import AsyncSession

    from backend.database.session import get_db, get_rls_db
    from backend.main import app
    from backend.repositories.project import ProjectRepository
    from backend.services.rag.tool_router import AppDataToolRouter

    async def faithful_get_rls_db(session: AsyncSession = Depends(get_db)):
        # Same dependency SHAPE as the real get_rls_db (its own nested
        # Depends(get_db)) - no Postgres-only SET LOCAL/set_config calls,
        # which SQLite cannot execute and which are not what this test is
        # verifying (that is covered separately by
        # test_live_postgres_integration.py against a real Postgres).
        yield session

    # Replaces conftest's flattening get_rls_db override for this test only
    # (monkeypatch restores the dict entry afterward) - see the module-level
    # comment above for why the default api_client override cannot exercise
    # this bug at all.
    monkeypatch.setitem(app.dependency_overrides, get_rls_db, faithful_get_rls_db)

    async with db_sessionmaker() as seed_session:
        project = await _seed_project(seed_session, add_member=False)

    captured: dict[str, int] = {}
    original_init = AppDataToolRouter.__init__

    def spy_init(self, session, *, authz_session=None):
        original_init(self, session, authz_session=authz_session)
        captured["session_id"] = id(self._session)
        captured["authz_session_id"] = id(self._authz_session)

    monkeypatch.setattr(AppDataToolRouter, "__init__", spy_init)

    real_get = ProjectRepository.get

    async def patched_get(self_repo, project_id):
        # Stand-in for Postgres RLS hiding the row: only the session
        # object identified as AppDataToolRouter's main `session` (the
        # RLS-scoped one in production) is blind to the project; any other
        # session object (i.e. a genuinely separate authz_session) sees it.
        if id(self_repo._session) == captured.get("session_id"):
            return None
        return await real_get(self_repo, project_id)

    monkeypatch.setattr(ProjectRepository, "get", patched_get)

    response = api_client.post(
        "/api/chatbot/chat",
        json={
            "message": "Project này có vấn đề gì không?",
            "project_id": str(project.id),
        },
    )
    assert response.status_code == 200
    body = response.json()

    # The core fix: the two session objects the real route injected are
    # genuinely distinct instances, not the same object under two names.
    assert captured["session_id"] != captured["authz_session_id"]

    assert body["content"] == "Bạn không có quyền truy cập project này."
    assert body["metadata"]["routing_reason"] == "project_access_denied"
