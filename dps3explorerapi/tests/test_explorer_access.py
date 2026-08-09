"""Tests for GET /browse/me access status."""

import pytest

from tests.conftest import ORG_ADMIN, USER_RW
from db.models import S3UserDeactivation, User
from core.auth import ROLE_USER

API = "/api/v2/explorer/browse/me"


def _seed_user(db, *, active=True):
    db.merge(
        User(
            id=USER_RW.id,
            username=USER_RW.user_name,
            email=USER_RW.email,
            role=ROLE_USER,
            organization_id=1,
            active=active,
        )
    )
    db.commit()


@pytest.mark.asyncio
async def test_me_active_user(client_as, db, seed_org):
    _seed_user(db, active=True)

    async with client_as(USER_RW) as c:
        r = await c.get(API, headers={"X-User-Id": str(USER_RW.id)})
    assert r.status_code == 200
    body = r.json()
    assert body["can_access"] is True
    assert body["s3_deactivated"] is False


@pytest.mark.asyncio
async def test_me_s3_deactivated(client_as, db, seed_org):
    _seed_user(db, active=True)
    db.add(S3UserDeactivation(user_id=USER_RW.id, deactivated_by=ORG_ADMIN.id))
    db.commit()

    async with client_as(USER_RW) as c:
        r = await c.get(API, headers={"X-User-Id": str(USER_RW.id)})
    assert r.status_code == 200
    body = r.json()
    assert body["can_access"] is False
    assert body["s3_deactivated"] is True
    assert body["block_reason"] == "s3_explorer"


@pytest.mark.asyncio
async def test_me_account_inactive(client_as, db, seed_org):
    _seed_user(db, active=False)

    async with client_as(USER_RW) as c:
        r = await c.get(API, headers={"X-User-Id": str(USER_RW.id)})
    assert r.status_code == 200
    body = r.json()
    assert body["can_access"] is False
    assert body["account_active"] is False
    assert body["block_reason"] == "account"
