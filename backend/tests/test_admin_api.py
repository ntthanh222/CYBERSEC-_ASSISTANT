"""Admin user/role management: last-admin lockout protection, audit trail."""
import uuid

from backend.database.models.rbac import UserRole

from .conftest import TEST_USER_A, TEST_USER_B


async def _seed_role(db_sessionmaker, user_id, *, role="user", is_active=True):
    async with db_sessionmaker() as session:
        session.add(UserRole(user_id=user_id, role=role, is_active=is_active))
        await session.commit()


async def _admin_client(api_client, db_sessionmaker):
    await _seed_role(db_sessionmaker, TEST_USER_A.id, role="admin")
    return api_client


def test_change_role_requires_admin(api_client, db_sessionmaker):
    other_id = uuid.uuid4()
    response = api_client.patch(
        f"/api/admin/users/{other_id}/role", json={"role": "admin"}
    )
    assert response.status_code == 403


async def test_change_role_404s_for_an_unknown_user(api_client, db_sessionmaker):
    await _admin_client(api_client, db_sessionmaker)
    response = api_client.patch(
        f"/api/admin/users/{uuid.uuid4()}/role", json={"role": "admin"}
    )
    assert response.status_code == 404


async def test_promote_a_user_to_admin_then_demote_is_allowed_with_two_admins(
    api_client, db_sessionmaker
):
    await _admin_client(api_client, db_sessionmaker)
    await _seed_role(db_sessionmaker, TEST_USER_B.id, role="user")

    promote = api_client.patch(
        f"/api/admin/users/{TEST_USER_B.id}/role", json={"role": "admin"}
    )
    assert promote.status_code == 200
    assert promote.json()["role"] == "admin"

    # Two active admins now exist, so demoting TEST_USER_A is allowed.
    demote = api_client.patch(
        f"/api/admin/users/{TEST_USER_A.id}/role", json={"role": "user"}
    )
    assert demote.status_code == 200
    assert demote.json()["role"] == "user"


async def test_cannot_demote_the_only_active_admin(api_client, db_sessionmaker):
    await _admin_client(api_client, db_sessionmaker)
    response = api_client.patch(
        f"/api/admin/users/{TEST_USER_A.id}/role", json={"role": "user"}
    )
    assert response.status_code == 409
    assert response.json()["error"] == "conflict"

    async with db_sessionmaker() as session:
        row = await session.get(UserRole, TEST_USER_A.id)
        assert row.role == "admin"


async def test_cannot_deactivate_the_only_active_admin(api_client, db_sessionmaker):
    await _admin_client(api_client, db_sessionmaker)
    response = api_client.patch(
        f"/api/admin/users/{TEST_USER_A.id}/active", json={"is_active": False}
    )
    assert response.status_code == 409

    async with db_sessionmaker() as session:
        row = await session.get(UserRole, TEST_USER_A.id)
        assert row.is_active is True


async def test_can_deactivate_a_non_admin_user(api_client, db_sessionmaker):
    await _admin_client(api_client, db_sessionmaker)
    await _seed_role(db_sessionmaker, TEST_USER_B.id, role="user")

    response = api_client.patch(
        f"/api/admin/users/{TEST_USER_B.id}/active", json={"is_active": False}
    )
    assert response.status_code == 200
    assert response.json()["is_active"] is False


async def test_role_change_rejects_an_invalid_role_value(api_client, db_sessionmaker):
    await _admin_client(api_client, db_sessionmaker)
    await _seed_role(db_sessionmaker, TEST_USER_B.id, role="user")
    response = api_client.patch(
        f"/api/admin/users/{TEST_USER_B.id}/role", json={"role": "superuser"}
    )
    assert response.status_code == 422


async def test_plain_admin_cannot_assign_super_admin(api_client, db_sessionmaker):
    """Only an existing super_admin may create/manage another - a plain
    admin (the fixture's default) must be refused, not silently allowed."""
    await _admin_client(api_client, db_sessionmaker)
    await _seed_role(db_sessionmaker, TEST_USER_B.id, role="user")
    response = api_client.patch(
        f"/api/admin/users/{TEST_USER_B.id}/role", json={"role": "super_admin"}
    )
    assert response.status_code == 403


async def test_role_change_writes_a_persisted_audit_row(api_client, db_sessionmaker):
    await _admin_client(api_client, db_sessionmaker)
    await _seed_role(db_sessionmaker, TEST_USER_B.id, role="user")

    api_client.patch(f"/api/admin/users/{TEST_USER_B.id}/role", json={"role": "admin"})

    audit = api_client.get("/api/admin/audit").json()
    actions = [item["action"] for item in audit["items"]]
    assert "role_changed" in actions
    changed = next(item for item in audit["items"] if item["action"] == "role_changed")
    assert changed["target_user_id"] == str(TEST_USER_B.id)
    assert changed["actor_user_id"] == str(TEST_USER_A.id)
    assert changed["metadata"]["from"] == "user"
    assert changed["metadata"]["to"] == "admin"
    assert changed["metadata"]["request_id"]


def test_audit_log_requires_admin(api_client, db_sessionmaker):
    assert api_client.get("/api/admin/audit").status_code == 403


async def test_role_change_notifies_the_target_user(api_client, db_sessionmaker):
    await _admin_client(api_client, db_sessionmaker)
    await _seed_role(db_sessionmaker, TEST_USER_B.id, role="user")

    response = api_client.patch(
        f"/api/admin/users/{TEST_USER_B.id}/role", json={"role": "admin"}
    )
    assert response.status_code == 200

    from backend.repositories.notifications import NotificationRepository

    async with db_sessionmaker() as session:
        repo = NotificationRepository(session)
        items, total, _ = await repo.list(user_id=TEST_USER_B.id, page=1, page_size=10)
        assert total == 1
        assert items[0].category == "system"


async def test_summary_reflects_real_content_counts(api_client, db_sessionmaker):
    await _admin_client(api_client, db_sessionmaker)
    api_client.post("/api/chatbot/conversations", json={"title": "admin summary check"})

    body = api_client.get("/api/admin/summary").json()
    assert body["users"]["total"] >= 1
    assert body["users"]["admins"] >= 1
    assert body["content"]["conversations"] >= 1
