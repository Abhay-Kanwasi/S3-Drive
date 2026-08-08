"""Tests for GET /browse/me access status."""

import pytest
from jose import jwt

from conftest import ORG_ADMIN, USER_RW
from core.config import settings
from db.models import S3UserDeactivation

API = "/api/v2/explorer/browse/me"


def _token_for(user):
    return jwt.encode(
        {"user_id": user.id, "email": user.email, "type": "access"},
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


@pytest.mark.asyncio
async def test_me_active_user(client_as, db):
    from core.auth import UAMUser

    db.merge(
        UAMUser(
            id=USER_RW.id,
            user_name=USER_RW.user_name,
            email=USER_RW.email,
            role=2,
            subscription_id=USER_RW.subscription_id,
            active=True,
        )
    )
    db.commit()

    async with client_as(USER_RW) as c:
        r = await c.get(
            API,
            headers={"Authorization": f"Bearer {_token_for(USER_RW)}"},
        )
    assert r.status_code == 200
    body = r.json()
    assert body["can_access"] is True
    assert body["s3_deactivated"] is False


@pytest.mark.asyncio
async def test_me_s3_deactivated(client_as, db):
    from core.auth import UAMUser

    db.merge(
        UAMUser(
            id=USER_RW.id,
            user_name=USER_RW.user_name,
            email=USER_RW.email,
            role=2,
            subscription_id=USER_RW.subscription_id,
            active=True,
        )
    )
    db.add(S3UserDeactivation(user_id=USER_RW.id, deactivated_by=ORG_ADMIN.id))
    db.commit()

    async with client_as(USER_RW) as c:
        r = await c.get(
            API,
            headers={"Authorization": f"Bearer {_token_for(USER_RW)}"},
        )
    assert r.status_code == 200
    body = r.json()
    assert body["can_access"] is False
    assert body["s3_deactivated"] is True
    assert body["block_reason"] == "s3_explorer"


@pytest.mark.asyncio
async def test_me_uam_inactive(client_as, db):
    from core.auth import UAMUser

    db.merge(
        UAMUser(
            id=USER_RW.id,
            user_name=USER_RW.user_name,
            email=USER_RW.email,
            role=2,
            subscription_id=USER_RW.subscription_id,
            active=False,
        )
    )
    db.commit()

    async with client_as(USER_RW) as c:
        r = await c.get(
            API,
            headers={"Authorization": f"Bearer {_token_for(USER_RW)}"},
        )
    assert r.status_code == 200
    body = r.json()
    assert body["can_access"] is False
    assert body["uam_active"] is False
    assert body["block_reason"] == "uam"
