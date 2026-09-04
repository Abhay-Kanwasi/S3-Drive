"""Tests for starred files/folders API."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import patch

import pytest

from tests.conftest import SUPER_ADMIN, USER_RW, USER_RW_2, _override_get_db
from core.auth import get_current_user
from db.postgresdb import get_db
from db.models import (
    Organization,
    User,
    UserGroup,
    GroupMembership,
    FolderGrant,
    StarredItem,
)
from core.auth import ROLE_SUPER_ADMIN, ROLE_USER

API = "/api/v2/explorer/stars"


@pytest.fixture
def seed_stars(db):
    org = Organization(
        id=1,
        org_key="org-001",
        org_name="TestOrg",
        bucket_name="test-bucket",
        region="us-east-1",
        onboarded_by=None,
    )
    db.add(org)
    db.flush()
    for u in (
        User(id=SUPER_ADMIN.id, username="SuperAdmin", email="super@test.com", role=ROLE_SUPER_ADMIN, organization_id=1, active=True),
        User(id=USER_RW.id, username="User1", email="user1@test.com", role=ROLE_USER, organization_id=1, active=True),
        User(id=USER_RW_2.id, username="User2", email="user2@test.com", role=ROLE_USER, organization_id=1, active=True),
    ):
        db.merge(u)
    db.flush()
    org.onboarded_by = SUPER_ADMIN.id
    db.commit()

    group = UserGroup(org_id=org.id, name="team-alpha", created_by=SUPER_ADMIN.id)
    db.add(group)
    db.commit()
    db.refresh(group)
    db.add(GroupMembership(group_id=group.id, user_id=USER_RW.id, added_by=SUPER_ADMIN.id))
    db.add(FolderGrant(
        group_id=group.id, org_id=org.id, prefix="ProjectA/",
        access_level="read_write", created_by=SUPER_ADMIN.id,
    ))
    db.commit()
    return {"org": org, "group": group}


def _star_body(key="ProjectA/sub/", name="sub", item_type="folder", size=None, last_modified=None):
    body = {"org_id": 1, "key": key, "type": item_type, "name": name}
    if size is not None:
        body["size"] = size
    if last_modified is not None:
        body["last_modified"] = last_modified
    return body


@pytest.mark.asyncio
async def test_put_then_get_accessible(client_as, db, seed_stars):
    async with client_as(USER_RW) as c:
        put = await c.put(API, json=_star_body())
        assert put.status_code == 200
        assert put.json()["starred"] is True
        listed = await c.get(API, params={"org_id": 1})
    assert listed.status_code == 200
    items = listed.json()["items"]
    assert len(items) == 1
    assert items[0]["key"] == "ProjectA/sub/"
    assert items[0]["type"] == "folder"
    assert items[0]["accessible"] is True
    assert items[0]["name"] == "sub"


@pytest.mark.asyncio
async def test_put_preserves_file_size(client_as, db, seed_stars):
    async with client_as(USER_RW) as c:
        put = await c.put(API, json=_star_body(
            key="ProjectA/file.txt",
            name="file.txt",
            item_type="file",
            size="12.0 KB",
            last_modified="September 04, 2026",
        ))
        assert put.status_code == 200
        listed = await c.get(API, params={"org_id": 1})
    item = listed.json()["items"][0]
    assert item["size"] == "12.0 KB"
    assert item["last_modified"] == "September 04, 2026"
    assert item["type"] == "file"


@pytest.mark.asyncio
async def test_upsert_does_not_duplicate(client_as, db, seed_stars):
    async with client_as(USER_RW) as c:
        await c.put(API, json=_star_body())
        await c.put(API, json=_star_body(name="sub-renamed"))
        listed = await c.get(API, params={"org_id": 1})
    assert listed.status_code == 200
    items = listed.json()["items"]
    assert len(items) == 1
    assert items[0]["name"] == "sub-renamed"
    assert db.query(StarredItem).count() == 1


@pytest.mark.asyncio
async def test_delete_and_missing_404(client_as, db, seed_stars):
    async with client_as(USER_RW) as c:
        await c.put(API, json=_star_body())
        deleted = await c.delete(API, params={"org_id": 1, "key": "ProjectA/sub/"})
        assert deleted.status_code == 200
        assert deleted.json()["starred"] is False
        missing = await c.delete(API, params={"org_id": 1, "key": "ProjectA/sub/"})
        assert missing.status_code == 404
        listed = await c.get(API, params={"org_id": 1})
    assert listed.json()["items"] == []


@pytest.mark.asyncio
async def test_other_user_cannot_see_or_delete(client_as, db, seed_stars):
    async with client_as(USER_RW) as c:
        await c.put(API, json=_star_body())
    async with client_as(USER_RW_2) as c:
        listed = await c.get(API, params={"org_id": 1})
        assert listed.status_code == 200
        assert listed.json()["items"] == []
        deleted = await c.delete(API, params={"org_id": 1, "key": "ProjectA/sub/"})
        assert deleted.status_code == 404


@pytest.mark.asyncio
async def test_put_without_grant_403(client_as, db, seed_stars):
    async with client_as(USER_RW_2) as c:
        resp = await c.put(API, json=_star_body())
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_inaccessible_after_grant_removed(client_as, db, seed_stars):
    async with client_as(USER_RW) as c:
        await c.put(API, json=_star_body())
    db.query(FolderGrant).delete()
    db.commit()
    async with client_as(USER_RW) as c:
        listed = await c.get(API, params={"org_id": 1})
    assert listed.status_code == 200
    items = listed.json()["items"]
    assert len(items) == 1
    assert items[0]["accessible"] is False


@pytest.mark.asyncio
async def test_star_cap(client_as, db, seed_stars):
    with patch("api.endpoints.stars.STAR_LIMIT", 2):
        async with client_as(USER_RW) as c:
            r1 = await c.put(API, json=_star_body("ProjectA/a/", "a"))
            r2 = await c.put(API, json=_star_body("ProjectA/b/", "b"))
            r3 = await c.put(API, json=_star_body("ProjectA/c/", "c"))
        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r3.status_code == 400
        assert "200/200" not in r3.json()["detail"]
        assert "2/2" in r3.json()["detail"]


@pytest.mark.asyncio
async def test_invalid_type_400(client_as, db, seed_stars):
    async with client_as(USER_RW) as c:
        resp = await c.put(API, json={**_star_body(), "type": "link"})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_org_not_found_404(client_as, db, seed_stars):
    async with client_as(SUPER_ADMIN) as c:
        resp = await c.get(API, params={"org_id": 999})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_401_without_auth(setup_db):
    import httpx
    from httpx import ASGITransport
    from main import app
    from api.router import api_router
    from core.config import settings as app_settings
    from tests.conftest import _override_get_db

    browse_route = f"{app_settings.API_V1_STR}/browse/browse"
    if not any(getattr(r, "path", "") == browse_route for r in app.routes):
        app.include_router(api_router, prefix=app_settings.API_V1_STR)

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides.pop(get_current_user, None)
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get(API, params={"org_id": 1})
    app.dependency_overrides.clear()
    assert resp.status_code == 401
