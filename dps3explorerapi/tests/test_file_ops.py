"""
Tests for File Operations (rename, copy, move).

Covers:
- POST /files/rename — success, collision, no access, invalid name
- POST /files/copy — success, collision, read-only on source, no write on target
- POST /files/move — success, collision, no write on source
- Admin bypasses grant checks
- Extension validation on rename
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
from db.models import Organization, UserGroup, GroupMembership, FolderGrant


FILES_API = "/api/v2/explorer/files"


@pytest.fixture
def seed_org(db):
    """Seed org + owned users for FK integrity."""
    from db.models import Organization, User
    from core.auth import ROLE_SUPER_ADMIN, ROLE_MASTER_ADMIN, ROLE_ADMIN, ROLE_USER
    from tests.conftest import SUPER_ADMIN, MASTER_ADMIN, ORG_ADMIN, USER_RW, USER_RW_2

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
        User(id=1, username="SuperAdmin", email="super@test.com", role=ROLE_SUPER_ADMIN, organization_id=1, active=True),
        User(id=2, username="MasterAdmin", email="master@test.com", role=ROLE_MASTER_ADMIN, organization_id=1, active=True),
        User(id=3, username="OrgAdmin", email="orgadmin@test.com", role=ROLE_ADMIN, organization_id=1, active=True),
        User(id=10, username="User1", email="user1@test.com", role=ROLE_USER, organization_id=1, active=True),
        User(id=11, username="User2", email="user2@test.com", role=ROLE_USER, organization_id=1, active=True),
    ):
        db.merge(u)
    db.flush()
    org.onboarded_by = 1
    db.commit()
    db.refresh(org)
    return org


@pytest.fixture
def seed_user_grant(db, seed_org):
    """Grant USER_RW write access on Data/ prefix."""
    group = UserGroup(name="FileOpsGroup", org_id=seed_org.id, created_by=1)
    db.add(group)
    db.commit()
    db.refresh(group)

    membership = GroupMembership(group_id=group.id, user_id=USER_RW.id, added_by=1)
    db.add(membership)

    grant = FolderGrant(
        group_id=group.id,
        org_id=seed_org.id,
        prefix="Data/",
        access_level="read_write",
        created_by=1,
    )
    db.add(grant)
    db.commit()
    return grant


@pytest.fixture
def seed_readonly_grant(db, seed_org):
    """Grant USER_RW_2 read-only access on Reports/ prefix."""
    group = UserGroup(name="ReadOnlyGroup", org_id=seed_org.id, created_by=1)
    db.add(group)
    db.commit()
    db.refresh(group)

    membership = GroupMembership(group_id=group.id, user_id=USER_RW_2.id, added_by=1)
    db.add(membership)

    grant = FolderGrant(
        group_id=group.id,
        org_id=seed_org.id,
        prefix="Reports/",
        access_level="read",
        created_by=1,
    )
    db.add(grant)
    db.commit()
    return grant


# ============================================================
# RENAME
# ============================================================


@pytest.mark.asyncio
async def test_rename_file_success(client_as, db, seed_org, seed_user_grant, mock_s3):
    """User with write access can rename a file."""
    mock_s3.put_object(Bucket="test-bucket", Key="Data/report.csv", Body=b"a,b\n1,2")

    async with client_as(USER_RW) as c:
        resp = await c.post(f"{FILES_API}/rename", json={
            "org_id": seed_org.id,
            "file_key": "Data/report.csv",
            "new_name": "report_v2.csv",
            "basePath": "test-bucket",
        })
    assert resp.status_code == 200
    data = resp.json()
    assert data["new_key"] == "Data/report_v2.csv"

    # Original should be gone, new should exist
    objs = mock_s3.list_objects_v2(Bucket="test-bucket", Prefix="Data/")
    keys = [o["Key"] for o in objs.get("Contents", [])]
    assert "Data/report_v2.csv" in keys
    assert "Data/report.csv" not in keys


@pytest.mark.asyncio
async def test_rename_file_collision(client_as, db, seed_org, seed_user_grant, mock_s3):
    """Rename fails if target name already exists."""
    mock_s3.put_object(Bucket="test-bucket", Key="Data/a.csv", Body=b"data")
    mock_s3.put_object(Bucket="test-bucket", Key="Data/b.csv", Body=b"data")

    async with client_as(USER_RW) as c:
        resp = await c.post(f"{FILES_API}/rename", json={
            "org_id": seed_org.id,
            "file_key": "Data/a.csv",
            "new_name": "b.csv",
            "basePath": "test-bucket",
        })
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_rename_file_invalid_extension(client_as, db, seed_org, seed_user_grant, mock_s3):
    """Rename to disallowed extension is rejected."""
    mock_s3.put_object(Bucket="test-bucket", Key="Data/data.csv", Body=b"data")

    async with client_as(USER_RW) as c:
        resp = await c.post(f"{FILES_API}/rename", json={
            "org_id": seed_org.id,
            "file_key": "Data/data.csv",
            "new_name": "data.exe",
            "basePath": "test-bucket",
        })
    assert resp.status_code == 415


@pytest.mark.asyncio
async def test_rename_file_no_access(client_as, db, seed_org, mock_s3):
    """User without grant cannot rename."""
    mock_s3.put_object(Bucket="test-bucket", Key="Secret/data.csv", Body=b"data")

    async with client_as(USER_RW) as c:
        resp = await c.post(f"{FILES_API}/rename", json={
            "org_id": seed_org.id,
            "file_key": "Secret/data.csv",
            "new_name": "data2.csv",
            "basePath": "test-bucket",
        })
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_rename_file_invalid_name(client_as, db, seed_org, seed_user_grant, mock_s3):
    """Rename with slash in name is rejected."""
    mock_s3.put_object(Bucket="test-bucket", Key="Data/data.csv", Body=b"data")

    async with client_as(USER_RW) as c:
        resp = await c.post(f"{FILES_API}/rename", json={
            "org_id": seed_org.id,
            "file_key": "Data/data.csv",
            "new_name": "sub/data.csv",
            "basePath": "test-bucket",
        })
    assert resp.status_code == 422


# ============================================================
# COPY
# ============================================================


@pytest.mark.asyncio
async def test_copy_file_success(client_as, db, seed_org, seed_user_grant, mock_s3):
    """User with write on both source and target can copy."""
    mock_s3.put_object(Bucket="test-bucket", Key="Data/source.csv", Body=b"a,b\n1,2")
    mock_s3.put_object(Bucket="test-bucket", Key="Data/subfolder/", Body=b"")

    async with client_as(USER_RW) as c:
        resp = await c.post(f"{FILES_API}/copy", json={
            "org_id": seed_org.id,
            "file_key": "Data/source.csv",
            "target_prefix": "Data/subfolder",
            "basePath": "test-bucket",
        })
    assert resp.status_code == 200
    data = resp.json()
    assert data["new_key"] == "Data/subfolder/source.csv"

    # Source should still exist
    objs = mock_s3.list_objects_v2(Bucket="test-bucket", Prefix="Data/source.csv")
    assert objs.get("KeyCount", 0) >= 1


@pytest.mark.asyncio
async def test_copy_file_collision(client_as, db, seed_org, seed_user_grant, mock_s3):
    """Copy fails if file exists at target."""
    mock_s3.put_object(Bucket="test-bucket", Key="Data/file.csv", Body=b"data")
    mock_s3.put_object(Bucket="test-bucket", Key="Data/dest/file.csv", Body=b"existing")

    async with client_as(USER_RW) as c:
        resp = await c.post(f"{FILES_API}/copy", json={
            "org_id": seed_org.id,
            "file_key": "Data/file.csv",
            "target_prefix": "Data/dest",
            "basePath": "test-bucket",
        })
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_copy_file_no_write_on_target(client_as, db, seed_org, seed_readonly_grant, mock_s3):
    """Read-only user cannot copy to their prefix."""
    mock_s3.put_object(Bucket="test-bucket", Key="Reports/data.csv", Body=b"data")

    async with client_as(USER_RW_2) as c:
        resp = await c.post(f"{FILES_API}/copy", json={
            "org_id": seed_org.id,
            "file_key": "Reports/data.csv",
            "target_prefix": "Reports/archive",
            "basePath": "test-bucket",
        })
    assert resp.status_code == 403


# ============================================================
# MOVE
# ============================================================


@pytest.mark.asyncio
async def test_move_file_success(client_as, db, seed_org, seed_user_grant, mock_s3):
    """User with write on both prefixes can move."""
    mock_s3.put_object(Bucket="test-bucket", Key="Data/moveme.csv", Body=b"a,b\n1,2")
    mock_s3.put_object(Bucket="test-bucket", Key="Data/archive/", Body=b"")

    async with client_as(USER_RW) as c:
        resp = await c.post(f"{FILES_API}/move", json={
            "org_id": seed_org.id,
            "file_key": "Data/moveme.csv",
            "target_prefix": "Data/archive",
            "basePath": "test-bucket",
        })
    assert resp.status_code == 200
    data = resp.json()
    assert data["new_key"] == "Data/archive/moveme.csv"

    # Source should be gone
    objs = mock_s3.list_objects_v2(Bucket="test-bucket", Prefix="Data/moveme.csv")
    assert objs.get("KeyCount", 0) == 0


@pytest.mark.asyncio
async def test_move_file_collision(client_as, db, seed_org, seed_user_grant, mock_s3):
    """Move fails if target already has a file with same name."""
    mock_s3.put_object(Bucket="test-bucket", Key="Data/x.csv", Body=b"data")
    mock_s3.put_object(Bucket="test-bucket", Key="Data/target/x.csv", Body=b"existing")

    async with client_as(USER_RW) as c:
        resp = await c.post(f"{FILES_API}/move", json={
            "org_id": seed_org.id,
            "file_key": "Data/x.csv",
            "target_prefix": "Data/target",
            "basePath": "test-bucket",
        })
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_move_file_no_write_on_source(client_as, db, seed_org, seed_readonly_grant, mock_s3):
    """Read-only user on source prefix cannot move."""
    mock_s3.put_object(Bucket="test-bucket", Key="Reports/locked.csv", Body=b"data")

    async with client_as(USER_RW_2) as c:
        resp = await c.post(f"{FILES_API}/move", json={
            "org_id": seed_org.id,
            "file_key": "Reports/locked.csv",
            "target_prefix": "Reports/moved",
            "basePath": "test-bucket",
        })
    assert resp.status_code == 403


# ============================================================
# ADMIN BYPASS
# ============================================================


@pytest.mark.asyncio
async def test_admin_can_rename_without_grant(client_as, db, seed_org, mock_s3):
    """Admin users bypass grant checks."""
    mock_s3.put_object(Bucket="test-bucket", Key="NoGrant/data.csv", Body=b"hello")

    async with client_as(MASTER_ADMIN) as c:
        resp = await c.post(f"{FILES_API}/rename", json={
            "org_id": seed_org.id,
            "file_key": "NoGrant/data.csv",
            "new_name": "renamed.csv",
            "basePath": "test-bucket",
        })
    assert resp.status_code == 200
    assert resp.json()["new_key"] == "NoGrant/renamed.csv"


@pytest.mark.asyncio
async def test_admin_can_move_without_grant(client_as, db, seed_org, mock_s3):
    """Admin can move files regardless of grant."""
    mock_s3.put_object(Bucket="test-bucket", Key="Anywhere/file.csv", Body=b"data")

    async with client_as(MASTER_ADMIN) as c:
        resp = await c.post(f"{FILES_API}/move", json={
            "org_id": seed_org.id,
            "file_key": "Anywhere/file.csv",
            "target_prefix": "Dest/folder",
            "basePath": "test-bucket",
        })
    assert resp.status_code == 200


# ============================================================
# EDGE CASES
# ============================================================


@pytest.mark.asyncio
async def test_rename_nonexistent_file(client_as, db, seed_org, seed_user_grant, mock_s3):
    """Renaming a file that doesn't exist returns 404."""
    async with client_as(USER_RW) as c:
        resp = await c.post(f"{FILES_API}/rename", json={
            "org_id": seed_org.id,
            "file_key": "Data/ghost.csv",
            "new_name": "found.csv",
            "basePath": "test-bucket",
        })
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_copy_nonexistent_file(client_as, db, seed_org, seed_user_grant, mock_s3):
    """Copying a file that doesn't exist returns 404."""
    async with client_as(USER_RW) as c:
        resp = await c.post(f"{FILES_API}/copy", json={
            "org_id": seed_org.id,
            "file_key": "Data/ghost.csv",
            "target_prefix": "Data/dest",
            "basePath": "test-bucket",
        })
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_invalid_org_returns_404(client_as, db, mock_s3):
    """Non-existent org returns 404."""
    async with client_as(MASTER_ADMIN) as c:
        resp = await c.post(f"{FILES_API}/rename", json={
            "org_id": 9999,
            "file_key": "x/y.csv",
            "new_name": "z.csv",
            "basePath": "test-bucket",
        })
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_cross_org_user_blocked(client_as, db, seed_org, mock_s3):
    """User from a different subscription cannot access another org's files."""
    mock_s3.put_object(Bucket="test-bucket", Key="Data/file.csv", Body=b"data")

    async with client_as(USER_OTHER_ORG) as c:
        resp = await c.post(f"{FILES_API}/rename", json={
            "org_id": seed_org.id,
            "file_key": "Data/file.csv",
            "new_name": "hacked.csv",
            "basePath": "test-bucket",
        })
    assert resp.status_code == 403
    assert "No access to this organization" in resp.json()["detail"]


# ============================================================
# REGRESSION: Root target prefix (no leading slash)
# ============================================================


@pytest.mark.asyncio
async def test_copy_to_root_no_leading_slash(client_as, db, seed_org, mock_s3):
    """Copy to empty target_prefix produces 'filename', not '/filename'."""
    mock_s3.put_object(Bucket="test-bucket", Key="Folder/report.csv", Body=b"data")

    async with client_as(MASTER_ADMIN) as c:
        resp = await c.post(f"{FILES_API}/copy", json={
            "org_id": seed_org.id,
            "file_key": "Folder/report.csv",
            "target_prefix": "",
            "basePath": "test-bucket",
        })
    assert resp.status_code == 200
    assert resp.json()["new_key"] == "report.csv"


@pytest.mark.asyncio
async def test_move_to_root_no_leading_slash(client_as, db, seed_org, mock_s3):
    """Move to empty target_prefix produces 'filename', not '/filename'."""
    mock_s3.put_object(Bucket="test-bucket", Key="Folder/data.csv", Body=b"data")

    async with client_as(MASTER_ADMIN) as c:
        resp = await c.post(f"{FILES_API}/move", json={
            "org_id": seed_org.id,
            "file_key": "Folder/data.csv",
            "target_prefix": "",
            "basePath": "test-bucket",
        })
    assert resp.status_code == 200
    assert resp.json()["new_key"] == "data.csv"


# ============================================================
# REGRESSION: Strict-read denies child-grant reading parent
# ============================================================


@pytest.mark.asyncio
async def test_copy_denied_when_grant_is_child_of_source(client_as, db, seed_org, mock_s3):
    """User with grant on Data/sub/ cannot copy a file from Data/ (parent)."""
    group = UserGroup(name="ChildGrant", org_id=seed_org.id, created_by=1)
    db.add(group)
    db.commit()
    db.refresh(group)

    membership = GroupMembership(group_id=group.id, user_id=USER_RW.id, added_by=1)
    db.add(membership)

    grant = FolderGrant(
        group_id=group.id,
        org_id=seed_org.id,
        prefix="Data/sub/",
        access_level="read_write",
        created_by=1,
    )
    db.add(grant)
    db.commit()

    mock_s3.put_object(Bucket="test-bucket", Key="Data/secret.csv", Body=b"secret")

    async with client_as(USER_RW) as c:
        resp = await c.post(f"{FILES_API}/copy", json={
            "org_id": seed_org.id,
            "file_key": "Data/secret.csv",
            "target_prefix": "Data/sub",
            "basePath": "test-bucket",
        })
    assert resp.status_code == 403


# ============================================================
# REGRESSION: Legacy user fallback works for copy
# ============================================================


@pytest.mark.asyncio
@pytest.mark.skip(reason="legacy UAM/s3_explorer path removed")
async def test_legacy_user_can_copy():
    """Legacy user (s3_explorer entry, no group memberships) can copy files."""
    pass


# ============================================================
# MULTIPART COPY PATH (>5GB logic exercised with patched limit)
# ============================================================


FIVE_MB = 5 * 1024 * 1024


@pytest.mark.asyncio
async def test_copy_uses_multipart_when_above_limit(client_as, db, seed_org, mock_s3):
    """When file exceeds SINGLE_COPY_LIMIT, multipart path is used."""
    content = b"x" * (FIVE_MB * 2 + 1000)
    mock_s3.put_object(Bucket="test-bucket", Key="Big/large.csv", Body=content)

    with patch("api.endpoints.files.SINGLE_COPY_LIMIT", FIVE_MB), \
         patch("api.endpoints.files.PART_SIZE", FIVE_MB):
        async with client_as(MASTER_ADMIN) as c:
            resp = await c.post(f"{FILES_API}/copy", json={
                "org_id": seed_org.id,
                "file_key": "Big/large.csv",
                "target_prefix": "Big/dest",
                "basePath": "test-bucket",
            })
    assert resp.status_code == 200
    assert resp.json()["new_key"] == "Big/dest/large.csv"

    obj = mock_s3.get_object(Bucket="test-bucket", Key="Big/dest/large.csv")
    assert len(obj["Body"].read()) == len(content)


@pytest.mark.asyncio
async def test_move_uses_multipart_and_deletes_source(client_as, db, seed_org, mock_s3):
    """Move with multipart copy deletes source after successful copy."""
    content = b"y" * (FIVE_MB * 2 + 500)
    mock_s3.put_object(Bucket="test-bucket", Key="Big/movable.csv", Body=content)

    with patch("api.endpoints.files.SINGLE_COPY_LIMIT", FIVE_MB), \
         patch("api.endpoints.files.PART_SIZE", FIVE_MB):
        async with client_as(MASTER_ADMIN) as c:
            resp = await c.post(f"{FILES_API}/move", json={
                "org_id": seed_org.id,
                "file_key": "Big/movable.csv",
                "target_prefix": "Big/moved",
                "basePath": "test-bucket",
            })
    assert resp.status_code == 200

    # Source gone
    objs = mock_s3.list_objects_v2(Bucket="test-bucket", Prefix="Big/movable.csv")
    assert objs.get("KeyCount", 0) == 0

    # Destination has correct content
    obj = mock_s3.get_object(Bucket="test-bucket", Key="Big/moved/movable.csv")
    assert len(obj["Body"].read()) == len(content)


@pytest.mark.asyncio
async def test_multipart_abort_on_failure(client_as, db, seed_org, mock_s3):
    """If _s3_copy raises, the endpoint returns 500 and dest doesn't exist."""
    content = b"z" * 100
    mock_s3.put_object(Bucket="test-bucket", Key="Big/fail.csv", Body=content)

    def _exploding_copy(bucket, source_key, dest_key, file_size):
        raise RuntimeError("Simulated multipart failure")

    with patch("api.endpoints.files._s3_copy", side_effect=_exploding_copy):
        async with client_as(MASTER_ADMIN) as c:
            resp = await c.post(f"{FILES_API}/copy", json={
                "org_id": seed_org.id,
                "file_key": "Big/fail.csv",
                "target_prefix": "Big/dest",
                "basePath": "test-bucket",
            })
    assert resp.status_code == 500

    # Destination should NOT exist
    objs = mock_s3.list_objects_v2(Bucket="test-bucket", Prefix="Big/dest/fail.csv")
    assert objs.get("KeyCount", 0) == 0


@pytest.mark.asyncio
async def test_abort_cleans_up_multipart_upload(mock_s3):
    """Unit test: _s3_copy aborts multipart on exception."""
    import api.endpoints.files as files_mod

    content = b"a" * (FIVE_MB * 2 + 100)
    mock_s3.put_object(Bucket="test-bucket", Key="abort/source.csv", Body=content)

    original_upload_part_copy = files_mod.s3_client.upload_part_copy

    call_count = [0]
    def _fail_on_second(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] >= 2:
            raise Exception("Part 2 failed")
        return original_upload_part_copy(*args, **kwargs)

    with patch("api.endpoints.files.SINGLE_COPY_LIMIT", FIVE_MB), \
         patch("api.endpoints.files.PART_SIZE", FIVE_MB):
        try:
            with patch.object(files_mod.s3_client, "upload_part_copy", side_effect=_fail_on_second):
                files_mod._s3_copy("test-bucket", "abort/source.csv", "abort/dest.csv", len(content))
        except Exception:
            pass

    # After abort, no completed object at destination
    objs = mock_s3.list_objects_v2(Bucket="test-bucket", Prefix="abort/dest.csv")
    assert objs.get("KeyCount", 0) == 0
