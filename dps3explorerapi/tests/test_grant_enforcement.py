"""
Tests for FolderGrant enforcement on browse, create, rename, delete,
and restore endpoints.

Covers:
- Admin bypass (always allowed regardless of grants)
- User with no group memberships + legacy row (fallback: allowed)
- User with no group memberships + no legacy row (denied)
- User with group + grant covering prefix (allowed)
- User with group + grant NOT covering prefix (denied)
- Nested prefix matching (grant on A/ covers A/B/C/)
- Read-only grant blocks write operations
- read_write grant allows write operations
- Parent-write overgrant regression: child grant must not authorize parent writes
- Restore flow respects grant checks
- Root browse access check consistency
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import pytest_asyncio

from tests.conftest import (
    SUPER_ADMIN,
    USER_RW,
    USER_RW_2,
    TestSession,
)
from db.models import Organization, FolderMetadata, UserGroup, GroupMembership, FolderGrant

API = "/api/v2/explorer/browse"


@pytest.fixture
def seed_full(db, mock_s3):
    """
    Seed org, S3 folder structure, folder metadata, a user group with USER_RW,
    and a FolderGrant on 'ProjectA/' with read_write.
    """
    from db.models import User
    from core.auth import ROLE_SUPER_ADMIN, ROLE_USER
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
    db.refresh(org)

    # S3 folder structure
    mock_s3.put_object(Bucket="test-bucket", Key="ProjectA/", Body=b"")
    mock_s3.put_object(Bucket="test-bucket", Key="ProjectA/sub1/", Body=b"")
    mock_s3.put_object(Bucket="test-bucket", Key="ProjectA/sub1/file.txt", Body=b"hello")
    mock_s3.put_object(Bucket="test-bucket", Key="ProjectB/", Body=b"")
    mock_s3.put_object(Bucket="test-bucket", Key="ProjectB/data.csv", Body=b"a,b")
    mock_s3.put_object(Bucket="test-bucket", Key="Secret/", Body=b"")

    # Folder metadata (admin-created roots)
    for key in ["ProjectA/", "ProjectB/", "Secret/"]:
        db.add(FolderMetadata(
            org_id=org.id, key=key, created_by=SUPER_ADMIN.id, created_by_role="admin",
        ))
    db.add(FolderMetadata(
        org_id=org.id, key="ProjectA/sub1/", created_by=USER_RW.id, created_by_role="user",
    ))
    db.commit()

    # Group with USER_RW as member
    group = UserGroup(org_id=org.id, name="team-alpha", created_by=SUPER_ADMIN.id)
    db.add(group)
    db.commit()
    db.refresh(group)

    db.add(GroupMembership(group_id=group.id, user_id=USER_RW.id, added_by=SUPER_ADMIN.id))
    db.commit()

    # Grant: read_write on ProjectA/
    db.add(FolderGrant(
        group_id=group.id, org_id=org.id, prefix="ProjectA/",
        access_level="read_write", created_by=SUPER_ADMIN.id,
    ))
    db.commit()

    return {"org": org, "group": group}


@pytest.fixture
def seed_read_only(db, seed_full):
    """Add a read-only grant on ProjectB/ for USER_RW."""
    org = seed_full["org"]
    group = seed_full["group"]
    db.add(FolderGrant(
        group_id=group.id, org_id=org.id, prefix="ProjectB/",
        access_level="read", created_by=SUPER_ADMIN.id,
    ))
    db.commit()
    return seed_full


# ---------- Browse Tests ----------

class TestBrowseEnforcement:
    """Grant enforcement on POST /browse/browse."""

    @pytest.mark.asyncio
    async def test_admin_sees_all_folders(self, client_as, seed_full):
        """Admin bypasses grant checks — sees all folders."""
        org = seed_full["org"]
        async with client_as(SUPER_ADMIN) as c:
            resp = await c.post(f"{API}/browse", json={"org_id": org.id, "prefix": ""})
        assert resp.status_code == 200
        folder_names = [f["name"] for f in resp.json()["folders"]]
        assert "ProjectA" in folder_names
        assert "ProjectB" in folder_names
        assert "Secret" in folder_names

    @pytest.mark.asyncio
    async def test_user_with_grant_sees_granted_folders(self, client_as, seed_full):
        """User with group membership sees only folders covered by grants."""
        org = seed_full["org"]
        async with client_as(USER_RW) as c:
            resp = await c.post(f"{API}/browse", json={"org_id": org.id, "prefix": ""})
        assert resp.status_code == 200
        folder_names = [f["name"] for f in resp.json()["folders"]]
        assert "ProjectA" in folder_names
        assert "Secret" not in folder_names

    @pytest.mark.asyncio
    async def test_user_can_browse_nested_granted_prefix(self, client_as, seed_full):
        """Grant on ProjectA/ allows browsing ProjectA/sub1/."""
        org = seed_full["org"]
        async with client_as(USER_RW) as c:
            resp = await c.post(f"{API}/browse", json={"org_id": org.id, "prefix": "ProjectA/sub1/"})
        assert resp.status_code == 200
        files = resp.json()["files"]
        assert any(f["name"] == "file.txt" for f in files)

    @pytest.mark.asyncio
    async def test_user_blocked_from_non_granted_prefix(self, client_as, seed_full):
        """User cannot browse a prefix they have no grant for."""
        org = seed_full["org"]
        async with client_as(USER_RW) as c:
            resp = await c.post(f"{API}/browse", json={"org_id": org.id, "prefix": "Secret/"})
        assert resp.status_code == 403

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="legacy UAM/s3_explorer path removed")
    async def test_ungrouped_user_with_legacy_sees_all(self):
        """User with no group membership but a legacy row sees everything."""
        pass


# ---------- Create Folder Tests ----------

class TestCreateEnforcement:
    """Grant enforcement on POST /browse/folders/create."""

    @pytest.mark.asyncio
    async def test_user_can_create_in_granted_write_prefix(self, client_as, seed_full, mock_s3):
        """User with read_write grant on ProjectA/ can create subfolders."""
        org = seed_full["org"]
        async with client_as(USER_RW) as c:
            resp = await c.post(f"{API}/folders/create", json={
                "org_id": org.id,
                "parent_prefix": "ProjectA/",
                "name": "NewSub",
            })
        assert resp.status_code == 201
        assert resp.json()["key"] == "ProjectA/NewSub/"

    @pytest.mark.asyncio
    async def test_user_blocked_create_in_non_granted_prefix(self, client_as, seed_full, mock_s3):
        """User without grant on Secret/ cannot create folders there."""
        org = seed_full["org"]
        # Need to add admin folder metadata for Secret so the root-check passes
        async with client_as(USER_RW) as c:
            resp = await c.post(f"{API}/folders/create", json={
                "org_id": org.id,
                "parent_prefix": "Secret/",
                "name": "Hacked",
            })
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_read_only_grant_blocks_create(self, client_as, seed_read_only, mock_s3):
        """User with read-only grant on ProjectB/ cannot create subfolders."""
        org = seed_read_only["org"]
        async with client_as(USER_RW) as c:
            resp = await c.post(f"{API}/folders/create", json={
                "org_id": org.id,
                "parent_prefix": "ProjectB/",
                "name": "Attempt",
            })
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_admin_can_create_anywhere(self, client_as, seed_full, mock_s3):
        """Admin can create folders regardless of grants."""
        org = seed_full["org"]
        async with client_as(SUPER_ADMIN) as c:
            resp = await c.post(f"{API}/folders/create", json={
                "org_id": org.id,
                "parent_prefix": "Secret/",
                "name": "AdminCreated",
            })
        assert resp.status_code == 201


# ---------- Rename Folder Tests ----------

class TestRenameEnforcement:
    """Grant enforcement on POST /browse/folders/rename."""

    @pytest.mark.asyncio
    async def test_user_can_rename_in_granted_prefix(self, client_as, seed_full, mock_s3):
        """User with read_write on ProjectA/ can rename sub1."""
        org = seed_full["org"]
        async with client_as(USER_RW) as c:
            resp = await c.post(f"{API}/folders/rename", json={
                "org_id": org.id,
                "prefix": "ProjectA/sub1/",
                "new_name": "sub1renamed",
            })
        assert resp.status_code == 200
        assert resp.json()["new_key"] == "ProjectA/sub1renamed/"

    @pytest.mark.asyncio
    async def test_user_blocked_rename_non_granted_prefix(self, client_as, seed_full, mock_s3):
        """User cannot rename another user's folder in a non-granted prefix."""
        org = seed_full["org"]
        # Folder created by USER_RW_2 in Secret/ — USER_RW has no grant on Secret/
        db = TestSession()
        db.add(FolderMetadata(
            org_id=org.id, key="Secret/userfolder/", created_by=USER_RW_2.id, created_by_role="user",
        ))
        db.commit()
        db.close()
        mock_s3.put_object(Bucket="test-bucket", Key="Secret/userfolder/file.txt", Body=b"x")

        async with client_as(USER_RW) as c:
            resp = await c.post(f"{API}/folders/rename", json={
                "org_id": org.id,
                "prefix": "Secret/userfolder/",
                "new_name": "hacked",
            })
        assert resp.status_code == 403


# ---------- Delete Folder Tests ----------

class TestDeleteEnforcement:
    """Grant enforcement on POST /browse/folders/delete."""

    @pytest.mark.asyncio
    async def test_user_can_delete_in_granted_prefix(self, client_as, seed_full, mock_s3):
        """User with read_write on ProjectA/ can delete sub1."""
        org = seed_full["org"]
        async with client_as(USER_RW) as c:
            resp = await c.post(f"{API}/folders/delete", json={
                "org_id": org.id,
                "prefix": "ProjectA/sub1/",
            })
        assert resp.status_code == 200
        assert resp.json()["trashed"] == "ProjectA/sub1/"

    @pytest.mark.asyncio
    async def test_user_blocked_delete_non_granted_prefix(self, client_as, seed_full, mock_s3):
        """User cannot delete folders in non-granted prefix."""
        org = seed_full["org"]
        async with client_as(USER_RW) as c:
            resp = await c.post(f"{API}/folders/delete", json={
                "org_id": org.id,
                "prefix": "Secret/",
            })
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_read_only_blocks_delete(self, client_as, seed_read_only, mock_s3):
        """Read-only grant does not permit delete."""
        org = seed_read_only["org"]
        async with client_as(USER_RW) as c:
            resp = await c.post(f"{API}/folders/delete", json={
                "org_id": org.id,
                "prefix": "ProjectB/",
            })
        assert resp.status_code == 403


# ---------- Parent-Write Overgrant Regression Tests ----------

@pytest.fixture
def seed_child_grant(db, seed_full, mock_s3):
    """
    Add a read_write grant on a DEEP child prefix only (ProjectA/sub1/).
    Remove the broad ProjectA/ grant to isolate the child-only scenario.
    """
    org = seed_full["org"]
    group = seed_full["group"]

    db.query(FolderGrant).filter(
        FolderGrant.group_id == group.id,
        FolderGrant.prefix == "ProjectA/",
    ).delete()
    db.commit()

    db.add(FolderGrant(
        group_id=group.id, org_id=org.id, prefix="ProjectA/sub1/",
        access_level="read_write", created_by=SUPER_ADMIN.id,
    ))
    db.commit()
    return seed_full


class TestParentWriteOvergrant:
    """Verify that a child grant does NOT authorize writes to the parent."""

    @pytest.mark.asyncio
    async def test_child_grant_cannot_write_to_parent(self, client_as, seed_child_grant, mock_s3):
        """Grant on ProjectA/sub1/ must NOT allow creating folders in ProjectA/."""
        org = seed_child_grant["org"]
        async with client_as(USER_RW) as c:
            resp = await c.post(f"{API}/folders/create", json={
                "org_id": org.id,
                "parent_prefix": "ProjectA/",
                "name": "HackedViaParent",
            })
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_child_grant_can_write_within_child(self, client_as, seed_child_grant, mock_s3):
        """Grant on ProjectA/sub1/ SHOULD allow creating folders in ProjectA/sub1/."""
        org = seed_child_grant["org"]
        async with client_as(USER_RW) as c:
            resp = await c.post(f"{API}/folders/create", json={
                "org_id": org.id,
                "parent_prefix": "ProjectA/sub1/",
                "name": "Allowed",
            })
        assert resp.status_code == 201

    @pytest.mark.asyncio
    async def test_child_grant_can_read_parent_for_navigation(self, client_as, seed_child_grant, mock_s3):
        """Grant on ProjectA/sub1/ should still let user browse ProjectA/ (read navigation)."""
        org = seed_child_grant["org"]
        async with client_as(USER_RW) as c:
            resp = await c.post(f"{API}/browse", json={
                "org_id": org.id,
                "prefix": "ProjectA/",
            })
        assert resp.status_code == 200


# ---------- Restore Flow Tests ----------

class TestRestoreEnforcement:
    """Grant enforcement on POST /browse/trash/restore."""

    @pytest.mark.asyncio
    async def test_user_can_restore_to_granted_prefix(self, client_as, seed_full, mock_s3):
        """User with read_write on ProjectA/ can restore an item there."""
        org = seed_full["org"]

        mock_s3.put_object(
            Bucket="test-trash-bucket",
            Key=f"trash/{org.id}/{USER_RW.id}/ProjectA/sub1/restored.txt",
            Body=b"data",
            Metadata={
                "path": "ProjectA/sub1/restored.txt",
                "bucket": "test-bucket",
                "org_id": str(org.id),
                "deleted_by": str(USER_RW.id),
            },
        )

        async with client_as(USER_RW) as c:
            resp = await c.post(f"{API}/trash/restore", json={
                "org_id": org.id,
                "trash_key": f"trash/{org.id}/{USER_RW.id}/ProjectA/sub1/restored.txt",
            })
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_user_blocked_restore_to_non_granted_prefix(self, client_as, seed_full, mock_s3):
        """User cannot restore to a prefix they have no write grant for."""
        org = seed_full["org"]

        mock_s3.put_object(
            Bucket="test-trash-bucket",
            Key=f"trash/{org.id}/{USER_RW.id}/Secret/leaked.csv",
            Body=b"data",
            Metadata={
                "path": "Secret/leaked.csv",
                "bucket": "test-bucket",
                "org_id": str(org.id),
                "deleted_by": str(USER_RW.id),
            },
        )

        async with client_as(USER_RW) as c:
            resp = await c.post(f"{API}/trash/restore", json={
                "org_id": org.id,
                "trash_key": f"trash/{org.id}/{USER_RW.id}/Secret/leaked.csv",
            })
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_folder_restore_mixed_prefixes_partial(self, client_as, seed_full, seed_read_only, mock_s3):
        """Folder restore with objects from granted and non-granted prefixes.
        Granted objects are restored; non-granted ones are skipped (failed_count)."""
        org = seed_full["org"]

        trash_folder = f"trash/{org.id}/{USER_RW.id}/mixed/"
        mock_s3.put_object(
            Bucket="test-trash-bucket",
            Key=f"{trash_folder}granted.txt",
            Body=b"ok",
            Metadata={
                "path": "ProjectA/sub1/granted.txt",
                "bucket": "test-bucket",
                "org_id": str(org.id),
                "deleted_by": str(USER_RW.id),
            },
        )
        mock_s3.put_object(
            Bucket="test-trash-bucket",
            Key=f"{trash_folder}denied.txt",
            Body=b"nope",
            Metadata={
                "path": "Secret/denied.txt",
                "bucket": "test-bucket",
                "org_id": str(org.id),
                "deleted_by": str(USER_RW.id),
            },
        )

        async with client_as(USER_RW) as c:
            resp = await c.post(f"{API}/trash/restore", json={
                "org_id": org.id,
                "trash_key": trash_folder,
            })
        assert resp.status_code == 200
        data = resp.json()
        assert data["objects_restored"] == 1
        assert data["failed_count"] == 1


# ---------- Legacy Fallback Conditional Tests ----------

class TestLegacyFallback:
    """Verify that ungrouped users are only allowed if they have legacy s3_explorer rows."""

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="legacy UAM/s3_explorer path removed")
    async def test_ungrouped_user_with_legacy_row_sees_all(self):
        """Ungrouped user WITH a legacy Explorer row gets full access (backward compat)."""
        pass

    @pytest.mark.asyncio
    async def test_ungrouped_user_without_legacy_row_denied(self, client_as, seed_full, mock_s3):
        """Ungrouped user WITHOUT a legacy Explorer row is denied access."""
        org = seed_full["org"]
        async with client_as(USER_RW_2) as c:
            resp = await c.post(f"{API}/browse", json={"org_id": org.id, "prefix": ""})
        assert resp.status_code == 403


# ---------- Root Browse Consistency Tests ----------

class TestRootBrowseConsistency:
    """Verify root browse (`prefix=""`) goes through access checks."""

    @pytest.mark.asyncio
    async def test_member_with_grants_can_browse_root(self, client_as, seed_full, mock_s3):
        """User with at least one grant can browse root (to navigate)."""
        org = seed_full["org"]
        async with client_as(USER_RW) as c:
            resp = await c.post(f"{API}/browse", json={"org_id": org.id, "prefix": ""})
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_member_with_no_grants_blocked_at_root(self, client_as, seed_full, db, mock_s3):
        """User who is a group member but has zero grants is blocked even at root."""
        org = seed_full["org"]
        group = seed_full["group"]

        db.query(FolderGrant).filter(FolderGrant.group_id == group.id).delete()
        db.commit()

        async with client_as(USER_RW) as c:
            resp = await c.post(f"{API}/browse", json={"org_id": org.id, "prefix": ""})
        assert resp.status_code == 403
