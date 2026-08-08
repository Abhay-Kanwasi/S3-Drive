"""
Tests for newly wired audit events (mocked S3 writes).
"""

import os
import sys
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import pytest_asyncio

from tests.conftest import SUPER_ADMIN, USER_RW, TestSession
from db.models import Org, UserGroup, GroupMembership, FolderGrant, PlatformSettings


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


@pytest.mark.asyncio
async def test_platform_settings_update_emits_allowlist_updated(client_as, db, seed_org):
    with patch("core.audit._append_event_line") as mock_append:
        async with client_as(SUPER_ADMIN) as c:
            resp = await c.put(
                "/api/v2/explorer/admin/settings",
                json={"max_upload_bytes": 2 * 1024 * 1024 * 1024},
            )
        assert resp.status_code == 200
        assert mock_append.called
        import json
        line = mock_append.call_args[0][1]
        event = json.loads(line)
        assert event["event_type"] == "ALLOWLIST_UPDATED"


@pytest.mark.asyncio
async def test_grant_creation_emits_folder_access_notified(
    client_as, db, seed_org, seed_uam_users, mock_s3,
):
    mock_s3.put_object(Bucket="test-bucket", Key="Notify/", Body=b"")
    group = UserGroup(name="dp-Notify", org_id=seed_org.id, created_by=1)
    db.add(group)
    db.commit()
    db.refresh(group)
    db.add(GroupMembership(group_id=group.id, user_id=USER_RW.id, added_by=1))
    db.commit()

    with patch("core.audit._append_event_line") as mock_append:
        async with client_as(SUPER_ADMIN) as c:
            resp = await c.post(
                f"/api/v2/explorer/admin/groups/{group.id}/grants",
                json={"prefix": "Notify/", "access_level": "read"},
            )
        assert resp.status_code == 201

        event_types = []
        for call in mock_append.call_args_list:
            event = __import__("json").loads(call[0][1])
            event_types.append(event["event_type"])
        assert "GRANT_CREATED" in event_types
        assert "FOLDER_ACCESS_NOTIFIED" in event_types


@pytest.mark.asyncio
async def test_users_export_emits_users_exported(client_as, db, seed_org, seed_uam_users):
    with patch("core.audit._append_event_line") as mock_append:
        async with client_as(SUPER_ADMIN) as c:
            resp = await c.get("/api/v2/explorer/admin/users/export")
        assert resp.status_code == 200
        line = mock_append.call_args[0][1]
        event = __import__("json").loads(line)
        assert event["event_type"] == "USERS_EXPORTED"
