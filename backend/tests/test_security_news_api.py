"""Security news API tests.

News is a shared feed (see migration 0022) - any authenticated user reads
every article, but only admin/super_admin may create or curate one. Ordinary
users may still toggle their own read/bookmark flags on any article.
"""

from backend.database.models.rbac import UserRole
from backend.tests.conftest import TEST_USER_A, TEST_USER_B


async def _seed_role(db_sessionmaker, user_id, *, role="user", is_active=True):
    async with db_sessionmaker() as session:
        session.add(UserRole(user_id=user_id, role=role, is_active=is_active))
        await session.commit()


async def _admin_client(api_client, db_sessionmaker):
    await _seed_role(db_sessionmaker, TEST_USER_A.id, role="admin")
    return api_client


def _payload(**overrides):
    payload = {
        "title": "Vendor releases critical patch",
        "summary": "A vendor advisory describes a critical remotely exploitable issue.",
        "url": "https://example.com/advisory",
        "source": "Vendor Advisory",
        "published_at": "2026-08-04T08:00:00Z",
        "category": "Threat Advisory",
        "related_cves": ["CVE-2026-10001"],
        "bookmarked": False,
        "read": False,
    }
    payload.update(overrides)
    return payload


async def test_security_news_crud_filters_and_flags(api_client, db_sessionmaker):
    await _admin_client(api_client, db_sessionmaker)

    created = api_client.post("/api/news", json=_payload())
    assert created.status_code == 201
    article = created.json()
    assert article["title"] == "Vendor releases critical patch"

    listed = api_client.get("/api/news?search=vendor&unread=true")
    assert listed.status_code == 200
    assert listed.json()["total"] == 1

    bookmarked = api_client.patch(f"/api/news/{article['id']}/bookmark", json={"bookmarked": True})
    assert bookmarked.status_code == 200
    assert bookmarked.json()["bookmarked"] is True

    read = api_client.patch(f"/api/news/{article['id']}/read", json={"read": True})
    assert read.status_code == 200
    assert read.json()["read"] is True

    detail = api_client.get(f"/api/news/{article['id']}")
    assert detail.status_code == 200
    assert detail.json()["related_cves"] == ["CVE-2026-10001"]


async def test_security_news_create_requires_admin(api_client):
    # TEST_USER_A defaults to the plain "user" role - creating an article
    # must be refused, not silently allowed, per the admin-only write policy.
    response = api_client.post("/api/news", json=_payload())
    assert response.status_code == 403


async def test_security_news_is_shared_across_users(api_client, db_sessionmaker, switch_user):
    await _admin_client(api_client, db_sessionmaker)
    created = api_client.post("/api/news", json=_payload())
    assert created.status_code == 201
    article_id = created.json()["id"]

    switch_user(TEST_USER_B)
    # A plain user cannot create, but must still see the admin-curated article
    # in the shared feed - this is the fix for the previously-empty News page.
    assert api_client.get(f"/api/news/{article_id}").status_code == 200
    listed = api_client.get("/api/news")
    assert listed.status_code == 200
    assert listed.json()["total"] == 1

    # Any authenticated user may still toggle read/bookmark on a shared article.
    bookmarked = api_client.patch(f"/api/news/{article_id}/bookmark", json={"bookmarked": True})
    assert bookmarked.status_code == 200


async def test_security_news_duplicate_and_validation_are_safe(api_client, db_sessionmaker):
    await _admin_client(api_client, db_sessionmaker)
    assert api_client.post("/api/news", json=_payload()).status_code == 201
    duplicate = api_client.post("/api/news", json=_payload(title="Duplicate"))
    assert duplicate.status_code == 409
    assert duplicate.json()["message"] == "URL bài viết này đã được lưu."

    invalid = api_client.post("/api/news", json=_payload(url="not-a-url"))
    assert invalid.status_code == 422
    assert invalid.json()["message"] == "Invalid request."


def test_security_news_routes_require_authentication(unauthenticated_client):
    response = unauthenticated_client.get("/api/news")
    assert response.status_code == 401


def test_security_news_detail_bookmark_read_404_for_unknown_id(api_client):
    unknown_id = "00000000-0000-4000-8000-000000000000"
    assert api_client.get(f"/api/news/{unknown_id}").status_code == 404
    assert (
        api_client.patch(f"/api/news/{unknown_id}/bookmark", json={"bookmarked": True}).status_code
        == 404
    )
    assert (
        api_client.patch(f"/api/news/{unknown_id}/read", json={"read": True}).status_code == 404
    )
