"""DB-backed app role/authorization: the JWT `role` claim is never trusted."""

from backend.database.models.rbac import UserRole

from .conftest import TEST_USER_A, TEST_USER_B


async def _seed_role(db_sessionmaker, user_id, *, role="user", is_active=True):
    async with db_sessionmaker() as session:
        session.add(UserRole(user_id=user_id, role=role, is_active=is_active))
        await session.commit()


def test_me_defaults_a_never_seen_identity_to_user_role(api_client):
    body = api_client.get("/api/auth/me").json()
    assert body["role"] == "user"
    assert body["is_active"] is True
    assert body["id"] == str(TEST_USER_A.id)


def test_me_requires_bearer_token(unauthenticated_client):
    assert unauthenticated_client.get("/api/auth/me").status_code == 401


async def test_admin_endpoint_rejects_a_plain_user(api_client, db_sessionmaker):
    await _seed_role(db_sessionmaker, TEST_USER_A.id, role="user")
    response = api_client.get("/api/admin/summary")
    assert response.status_code == 403
    assert response.json()["error"] == "forbidden"


async def test_admin_endpoint_allows_a_real_admin(api_client, db_sessionmaker):
    await _seed_role(db_sessionmaker, TEST_USER_A.id, role="admin")
    response = api_client.get("/api/admin/summary")
    assert response.status_code == 200


def test_admin_endpoint_requires_bearer_token(unauthenticated_client):
    assert unauthenticated_client.get("/api/admin/summary").status_code == 401


async def test_deactivated_account_is_rejected_even_with_a_valid_token(
    api_client, db_sessionmaker
):
    await _seed_role(db_sessionmaker, TEST_USER_A.id, role="admin", is_active=False)
    response = api_client.get("/api/auth/me")
    assert response.status_code == 401


async def test_deactivated_admin_loses_admin_access_immediately(api_client, db_sessionmaker):
    """A token minted before deactivation must not keep working - the check
    reads the database on every request, not just at token-mint time."""
    await _seed_role(db_sessionmaker, TEST_USER_A.id, role="admin")
    assert api_client.get("/api/admin/summary").status_code == 200

    async with db_sessionmaker() as session:
        row = await session.get(UserRole, TEST_USER_A.id)
        row.is_active = False
        await session.commit()

    assert api_client.get("/api/admin/summary").status_code == 401


def test_a_forged_role_claim_on_the_jwt_grants_nothing(api_client, db_sessionmaker, switch_user):
    """TEST_USER_B has no user_roles row yet - even though nothing stops a
    caller from putting an arbitrary `role` string in their own JWT claims
    dict, authorization never reads `AuthenticatedUser.claims`/`.role` for
    this decision, only the database."""
    from backend.core.auth import AuthenticatedUser

    forged = AuthenticatedUser(id=TEST_USER_B.id, role="admin", claims={"role": "admin"})
    switch_user(forged)
    response = api_client.get("/api/admin/summary")
    assert response.status_code == 403
