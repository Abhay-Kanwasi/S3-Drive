"""
Tests for In-App Notifications.

Covers:
- Notification creation on grant creation (Trigger A)
- Notification creation on member addition (Trigger B)
- GET /notifications (ownership enforcement, ordering)
- POST /notifications/read (mark by ids, mark all)
- DELETE /notifications/{id} (ownership enforcement)
- Cap enforcement (max 50 per user)
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import pytest_asyncio
from unittest.mock import patch

from tests.conftest import (
    SUPER_ADMIN,
    MASTER_ADMIN,
    ORG_ADMIN,
    USER_RW,
    USER_RW_2,
    USER_OTHER_ORG,
    TestSession,
)
from db.models import (
    Org, UserGroup, GroupMembership, FolderGrant, UserNotification,
)


@pytest.fixture(autouse=True)
def patch_notif_session():
    """Override the DBSession in groups.py to use TestSession (SQLite)."""
    with patch("api.endpoints.groups.DBSession", TestSession):
        yield


NOTIF_API = "/api/v2/explorer/notifications"
GROUPS_API = "/api/v2/explorer/admin/groups"


@pytest.fixture
def seed_org(db):
    org = Org(
        subscription_id="sub-001",
        org_name="TestOrg",
        bucket_name="test-bucket",
        region="us-east-1",
        onboarded_by=1,
    )
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


@pytest.fixture
def seed_group_with_members(db, seed_org, seed_uam_users):
    """Create a group with USER_RW and USER_RW_2 as members."""
    group = UserGroup(name="dp-NotifGroup", org_id=seed_org.id, created_by=1)
    db.add(group)
    db.commit()
    db.refresh(group)

    for uid in [USER_RW.id, USER_RW_2.id]:
        db.add(GroupMembership(group_id=group.id, user_id=uid, added_by=1))
    db.commit()
    return group


@pytest.fixture
def seed_group_with_grant(db, seed_org, seed_group_with_members):
    """Add a grant to the group (for testing Trigger B)."""
    grant = FolderGrant(
        group_id=seed_group_with_members.id,
        org_id=seed_org.id,
        prefix="Data/",
        access_level="read_write",
        created_by=1,
    )
    db.add(grant)
    db.commit()
    return seed_group_with_members


@pytest.fixture
def seed_notifications(db, seed_org):
    """Seed some notifications for USER_RW."""
    for i in range(5):
        db.add(UserNotification(
            user_id=USER_RW.id,
            org_id=seed_org.id,
            type="folder_access",
            title=f"Notification {i}",
            message=f"You have access to folder_{i}/",
        ))
    db.add(UserNotification(
        user_id=USER_RW_2.id,
        org_id=seed_org.id,
        type="folder_access",
        title="Other user notif",
        message="This belongs to user 2",
    ))
    db.commit()


# ─────────────────── Trigger A: grant creation ───────────────────

@pytest.mark.asyncio
async def test_grant_creation_sends_notifications(
    client_as, db, seed_org, seed_group_with_members, mock_s3,
):
    mock_s3.put_object(Bucket="test-bucket", Key="Reports/file.csv", Body=b"data")

    async with client_as(SUPER_ADMIN) as c:
        resp = await c.post(
            f"{GROUPS_API}/{seed_group_with_members.id}/grants",
            json={"prefix": "Reports/", "access_level": "read"},
        )
    assert resp.status_code == 201

    notifs = db.query(UserNotification).filter(
        UserNotification.type == "folder_access"
    ).all()
    assert len(notifs) == 2
    user_ids = {n.user_id for n in notifs}
    assert user_ids == {USER_RW.id, USER_RW_2.id}
    assert all("Reports/" in n.message for n in notifs)


# ─────────────────── Trigger B: member addition ───────────────────

@pytest.mark.asyncio
async def test_member_addition_sends_notifications(
    client_as, db, seed_org, seed_group_with_grant, seed_uam_users, mock_s3,
):
    """Adding a new user to a group with existing grants should notify them."""
    from core.auth import UAMUser
    new_user_id = 30
    db.merge(UAMUser(
        id=new_user_id, user_name="NewUser", email="new@test.com",
        role=2, subscription_id="sub-001", active=True,
    ))
    db.commit()

    async with client_as(SUPER_ADMIN) as c:
        resp = await c.post(
            f"{GROUPS_API}/{seed_group_with_grant.id}/members",
            json={"user_ids": [new_user_id]},
        )
    assert resp.status_code == 201
    data = resp.json()
    assert new_user_id in data["added"]

    notifs = db.query(UserNotification).filter(
        UserNotification.user_id == new_user_id
    ).all()
    assert len(notifs) == 1
    assert "Data/" in notifs[0].message


# ─────────────────── GET /notifications ───────────────────

@pytest.mark.asyncio
async def test_list_notifications_returns_own_only(
    client_as, db, seed_org, seed_notifications,
):
    async with client_as(USER_RW) as c:
        resp = await c.get(NOTIF_API)
    assert resp.status_code == 200
    data = resp.json()
    assert data["unread_count"] == 5
    assert len(data["items"]) == 5
    assert all(item["title"].startswith("Notification") for item in data["items"])


@pytest.mark.asyncio
async def test_list_notifications_empty_for_other_user(
    client_as, db, seed_org, seed_notifications,
):
    """USER_OTHER_ORG should not see USER_RW's notifications."""
    async with client_as(USER_OTHER_ORG) as c:
        resp = await c.get(NOTIF_API)
    assert resp.status_code == 200
    data = resp.json()
    assert data["unread_count"] == 0
    assert len(data["items"]) == 0


# ─────────────────── POST /notifications/read ───────────────────

@pytest.mark.asyncio
async def test_mark_specific_notifications_read(
    client_as, db, seed_org, seed_notifications,
):
    notifs = db.query(UserNotification).filter_by(user_id=USER_RW.id).limit(2).all()
    ids = [n.id for n in notifs]

    async with client_as(USER_RW) as c:
        resp = await c.post(f"{NOTIF_API}/read", json={"ids": ids})
    assert resp.status_code == 200

    db.expire_all()
    for n_id in ids:
        n = db.query(UserNotification).get(n_id)
        assert n.is_read is True

    unread = db.query(UserNotification).filter_by(
        user_id=USER_RW.id, is_read=False
    ).count()
    assert unread == 3


@pytest.mark.asyncio
async def test_mark_all_notifications_read(
    client_as, db, seed_org, seed_notifications,
):
    async with client_as(USER_RW) as c:
        resp = await c.post(f"{NOTIF_API}/read", json={"all": True})
    assert resp.status_code == 200

    db.expire_all()
    unread = db.query(UserNotification).filter_by(
        user_id=USER_RW.id, is_read=False
    ).count()
    assert unread == 0


@pytest.mark.asyncio
async def test_mark_read_invalid_payload(client_as, db):
    """Neither ids nor all provided → 422."""
    async with client_as(USER_RW) as c:
        resp = await c.post(f"{NOTIF_API}/read", json={})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_mark_read_cannot_affect_other_users(
    client_as, db, seed_org, seed_notifications,
):
    """USER_RW trying to mark USER_RW_2's notification as read should have no effect."""
    other_notif = db.query(UserNotification).filter_by(user_id=USER_RW_2.id).first()

    async with client_as(USER_RW) as c:
        resp = await c.post(f"{NOTIF_API}/read", json={"ids": [other_notif.id]})
    assert resp.status_code == 200

    db.expire_all()
    n = db.query(UserNotification).get(other_notif.id)
    assert n.is_read is False


# ─────────────────── DELETE /notifications/{id} ───────────────────

@pytest.mark.asyncio
async def test_dismiss_own_notification(
    client_as, db, seed_org, seed_notifications,
):
    notif = db.query(UserNotification).filter_by(user_id=USER_RW.id).first()
    notif_id = notif.id

    async with client_as(USER_RW) as c:
        resp = await c.delete(f"{NOTIF_API}/{notif_id}")
    assert resp.status_code == 200
    assert resp.json()["status"] == "deleted"

    db.expire_all()
    assert db.query(UserNotification).filter_by(id=notif_id).first() is None


@pytest.mark.asyncio
async def test_dismiss_other_users_notification_returns_404(
    client_as, db, seed_org, seed_notifications,
):
    """Cannot dismiss another user's notification (IDOR protection)."""
    other_notif = db.query(UserNotification).filter_by(user_id=USER_RW_2.id).first()

    async with client_as(USER_RW) as c:
        resp = await c.delete(f"{NOTIF_API}/{other_notif.id}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_dismiss_nonexistent_notification_returns_404(client_as, db):
    async with client_as(USER_RW) as c:
        resp = await c.delete(f"{NOTIF_API}/99999")
    assert resp.status_code == 404


# ─────────────────── Cap enforcement ───────────────────

@pytest.mark.asyncio
async def test_notification_cap_enforcement(
    client_as, db, seed_org, seed_group_with_members, mock_s3,
):
    """After cap is reached, oldest notifications are pruned."""
    for i in range(50):
        db.add(UserNotification(
            user_id=USER_RW.id,
            org_id=seed_org.id,
            type="folder_access",
            title=f"Old notif {i}",
            message=f"Old message {i}",
        ))
    db.commit()

    count_before = db.query(UserNotification).filter_by(user_id=USER_RW.id).count()
    assert count_before == 50

    mock_s3.put_object(Bucket="test-bucket", Key="NewFolder/data.csv", Body=b"x")

    async with client_as(SUPER_ADMIN) as c:
        resp = await c.post(
            f"{GROUPS_API}/{seed_group_with_members.id}/grants",
            json={"prefix": "NewFolder/", "access_level": "read_write"},
        )
    assert resp.status_code == 201

    count_after = db.query(UserNotification).filter_by(user_id=USER_RW.id).count()
    assert count_after == 50
