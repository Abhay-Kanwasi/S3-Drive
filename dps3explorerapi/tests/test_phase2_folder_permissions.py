"""
Phase 2 tests — Folder create/rename/delete permissions, trash, upload guards.

Role matrix under test:
- SUPER_ADMIN (role 4): global admin — can do everything
- ORG_ADMIN (role 1): org-scoped admin — can create root folders, manage folders
- USER_RW (role 2): regular user — can only create subfolders under admin folders
- USER_RW_2 (role 2): second user — verifies cross-user folder editing
- USER_OTHER_ORG: user from different subscription — should be denied org access
"""

import pytest
from tests.conftest import (
    SUPER_ADMIN, MASTER_ADMIN, ORG_ADMIN,
    USER_RW, USER_RW_2, USER_OTHER_ORG,
)

PREFIX = "/api/v2/explorer"
BROWSE = f"{PREFIX}/browse"

@pytest.fixture
def seed_user_rw_grant(db, seed_org, seed_admin_folder):
    """Grant USER_RW read_write on AdminFolder/ (replaces legacy seed_user_rw_grant)."""
    from db.models import UserGroup, GroupMembership, FolderGrant
    group = UserGroup(name="UserRWGrant", org_id=seed_org.id, created_by=1)
    db.add(group)
    db.flush()
    db.add(GroupMembership(group_id=group.id, user_id=USER_RW.id, added_by=1))
    db.add(FolderGrant(
        group_id=group.id, org_id=seed_org.id, prefix="AdminFolder/",
        access_level="read_write", created_by=1,
    ))
    db.commit()
    return group




# =========================================================================
# FOLDER CREATION
# =========================================================================

class TestFolderCreate:
    """Admin creates root folders; users create subfolders only."""

    @pytest.mark.asyncio
    async def test_admin_can_create_root_folder(self, client_as, mock_s3, seed_org):
        async with client_as(SUPER_ADMIN) as c:
            resp = await c.post(f"{BROWSE}/folders/create", json={
                "org_id": seed_org.id,
                "parent_prefix": "",
                "name": "RootFolder",
            })
            assert resp.status_code == 201
            data = resp.json()
            assert data["key"] == "RootFolder/"
            assert data["created_by_role"] == "admin"

    @pytest.mark.asyncio
    async def test_user_cannot_create_root_folder(self, client_as, mock_s3, seed_org):
        async with client_as(USER_RW) as c:
            resp = await c.post(f"{BROWSE}/folders/create", json={
                "org_id": seed_org.id,
                "parent_prefix": "",
                "name": "HackerFolder",
            })
            assert resp.status_code == 403
            assert "root" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_user_can_create_subfolder_under_admin_folder(
        self, client_as, mock_s3, seed_org, seed_admin_folder, seed_user_rw_grant,
    ):
        async with client_as(USER_RW) as c:
            resp = await c.post(f"{BROWSE}/folders/create", json={
                "org_id": seed_org.id,
                "parent_prefix": "AdminFolder/",
                "name": "MySub",
            })
            assert resp.status_code == 201
            data = resp.json()
            assert data["key"] == "AdminFolder/MySub/"
            assert data["created_by_role"] == "user"

    @pytest.mark.asyncio
    async def test_user_cannot_create_under_non_admin_root(
        self, client_as, mock_s3, seed_org, db,
    ):
        """If the root-level folder was created by a user (not admin), block."""
        from db.models import FolderMetadata
        meta = FolderMetadata(
            org_id=seed_org.id, key="UserRoot/",
            created_by=USER_RW.id, created_by_role="user",
        )
        db.add(meta)
        db.commit()
        mock_s3.put_object(Bucket="test-bucket", Key="UserRoot/", Body=b"")

        async with client_as(USER_RW) as c:
            resp = await c.post(f"{BROWSE}/folders/create", json={
                "org_id": seed_org.id,
                "parent_prefix": "UserRoot/",
                "name": "BadSub",
            })
            assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_user_can_nest_subfolders_deep(
        self, client_as, mock_s3, seed_org, seed_admin_folder, seed_user_rw_grant,
    ):
        """Users can create unlimited nesting under admin root."""
        async with client_as(USER_RW) as c:
            resp = await c.post(f"{BROWSE}/folders/create", json={
                "org_id": seed_org.id,
                "parent_prefix": "AdminFolder/",
                "name": "Level1",
            })
            assert resp.status_code == 201

            resp2 = await c.post(f"{BROWSE}/folders/create", json={
                "org_id": seed_org.id,
                "parent_prefix": "AdminFolder/Level1/",
                "name": "Level2",
            })
            assert resp2.status_code == 201
            assert resp2.json()["key"] == "AdminFolder/Level1/Level2/"

    @pytest.mark.asyncio
    async def test_duplicate_folder_rejected(
        self, client_as, mock_s3, seed_org, seed_admin_folder,
    ):
        async with client_as(SUPER_ADMIN) as c:
            await c.post(f"{BROWSE}/folders/create", json={
                "org_id": seed_org.id,
                "parent_prefix": "",
                "name": "AdminFolder",
            })
            resp = await c.post(f"{BROWSE}/folders/create", json={
                "org_id": seed_org.id,
                "parent_prefix": "",
                "name": "AdminFolder",
            })
            assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_folder_name_with_slash_rejected(self, client_as, mock_s3, seed_org):
        async with client_as(SUPER_ADMIN) as c:
            resp = await c.post(f"{BROWSE}/folders/create", json={
                "org_id": seed_org.id,
                "parent_prefix": "",
                "name": "bad/name",
            })
            assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_folder_name_with_percent_rejected(self, client_as, mock_s3, seed_org):
        """Percent char is rejected in folder names."""
        async with client_as(SUPER_ADMIN) as c:
            resp = await c.post(f"{BROWSE}/folders/create", json={
                "org_id": seed_org.id,
                "parent_prefix": "",
                "name": "bad%name",
            })
            assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_folder_name_with_underscore_allowed(self, client_as, mock_s3, seed_org):
        """Underscore is allowed in folder names."""
        async with client_as(SUPER_ADMIN) as c:
            resp = await c.post(f"{BROWSE}/folders/create", json={
                "org_id": seed_org.id,
                "parent_prefix": "",
                "name": "folder_name",
            })
            assert resp.status_code == 201


# =========================================================================
# FOLDER RENAME
# =========================================================================

class TestFolderRename:
    """Admin folders: only admin can rename. User folders: any user can rename."""

    @pytest.mark.asyncio
    async def test_admin_can_rename_admin_folder(
        self, client_as, mock_s3, seed_org, seed_admin_folder,
    ):
        async with client_as(SUPER_ADMIN) as c:
            resp = await c.post(f"{BROWSE}/folders/rename", json={
                "org_id": seed_org.id,
                "prefix": "AdminFolder/",
                "new_name": "RenamedAdmin",
            })
            assert resp.status_code == 200
            assert resp.json()["new_key"] == "RenamedAdmin/"

    @pytest.mark.asyncio
    async def test_user_cannot_rename_admin_folder(
        self, client_as, mock_s3, seed_org, seed_admin_folder,
    ):
        async with client_as(USER_RW) as c:
            resp = await c.post(f"{BROWSE}/folders/rename", json={
                "org_id": seed_org.id,
                "prefix": "AdminFolder/",
                "new_name": "HackerRename",
            })
            assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_user_can_rename_user_folder(
        self, client_as, mock_s3, seed_org, seed_admin_folder, seed_user_folder,
    ):
        mock_s3.put_object(Bucket="test-bucket", Key="AdminFolder/UserSub/", Body=b"")
        async with client_as(USER_RW) as c:
            resp = await c.post(f"{BROWSE}/folders/rename", json={
                "org_id": seed_org.id,
                "prefix": "AdminFolder/UserSub/",
                "new_name": "RenamedSub",
            })
            assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_other_user_can_rename_user_folder(
        self, client_as, mock_s3, seed_org, seed_admin_folder, seed_user_folder, db,
    ):
        """USER_RW_2 with write grant can rename USER_RW's folder."""
        from db.models import UserGroup, GroupMembership, FolderGrant
        group = UserGroup(name="RenameGroup", org_id=seed_org.id, created_by=1)
        db.add(group)
        db.commit()
        db.refresh(group)
        db.add(GroupMembership(group_id=group.id, user_id=USER_RW_2.id, added_by=1))
        db.add(FolderGrant(group_id=group.id, org_id=seed_org.id, prefix="AdminFolder/", access_level="read_write", created_by=1))
        db.commit()

        mock_s3.put_object(Bucket="test-bucket", Key="AdminFolder/UserSub/", Body=b"")
        async with client_as(USER_RW_2) as c:
            resp = await c.post(f"{BROWSE}/folders/rename", json={
                "org_id": seed_org.id,
                "prefix": "AdminFolder/UserSub/",
                "new_name": "CrossUserRename",
            })
            assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_user_cannot_rename_folder_without_metadata(
        self, client_as, mock_s3, seed_org,
    ):
        """Missing metadata treated as admin-owned — user blocked."""
        mock_s3.put_object(Bucket="test-bucket", Key="Mystery/", Body=b"")
        async with client_as(USER_RW) as c:
            resp = await c.post(f"{BROWSE}/folders/rename", json={
                "org_id": seed_org.id,
                "prefix": "Mystery/",
                "new_name": "Hacked",
            })
            assert resp.status_code == 403


# =========================================================================
# FOLDER DELETE (MOVE TO TRASH)
# =========================================================================

class TestFolderDelete:
    """Admin folders: only admin can trash. User folders: any user can trash."""

    @pytest.mark.asyncio
    async def test_admin_can_trash_admin_folder(
        self, client_as, mock_s3, seed_org, seed_admin_folder,
    ):
        async with client_as(SUPER_ADMIN) as c:
            resp = await c.post(f"{BROWSE}/folders/delete", json={
                "org_id": seed_org.id,
                "prefix": "AdminFolder/",
            })
            assert resp.status_code == 200
            assert resp.json()["trashed"] == "AdminFolder/"

    @pytest.mark.asyncio
    async def test_user_cannot_trash_admin_folder(
        self, client_as, mock_s3, seed_org, seed_admin_folder,
    ):
        async with client_as(USER_RW) as c:
            resp = await c.post(f"{BROWSE}/folders/delete", json={
                "org_id": seed_org.id,
                "prefix": "AdminFolder/",
            })
            assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_user_can_trash_user_folder(
        self, client_as, mock_s3, seed_org, seed_admin_folder, seed_user_folder,
    ):
        mock_s3.put_object(Bucket="test-bucket", Key="AdminFolder/UserSub/", Body=b"")
        async with client_as(USER_RW) as c:
            resp = await c.post(f"{BROWSE}/folders/delete", json={
                "org_id": seed_org.id,
                "prefix": "AdminFolder/UserSub/",
            })
            assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_other_user_can_trash_user_folder(
        self, client_as, mock_s3, seed_org, seed_admin_folder, seed_user_folder, db,
    ):
        """USER_RW_2 with write grant can trash USER_RW's folder."""
        from db.models import UserGroup, GroupMembership, FolderGrant
        group = UserGroup(name="TrashGroup", org_id=seed_org.id, created_by=1)
        db.add(group)
        db.commit()
        db.refresh(group)
        db.add(GroupMembership(group_id=group.id, user_id=USER_RW_2.id, added_by=1))
        db.add(FolderGrant(group_id=group.id, org_id=seed_org.id, prefix="AdminFolder/", access_level="read_write", created_by=1))
        db.commit()

        mock_s3.put_object(Bucket="test-bucket", Key="AdminFolder/UserSub/", Body=b"")
        async with client_as(USER_RW_2) as c:
            resp = await c.post(f"{BROWSE}/folders/delete", json={
                "org_id": seed_org.id,
                "prefix": "AdminFolder/UserSub/",
            })
            assert resp.status_code == 200


# =========================================================================
# BROWSE — ADMIN SKELETON VIEW
# =========================================================================

class TestBrowseSkeleton:
    """Admin sees folder structure but not files inside user-created folders."""

    @pytest.mark.asyncio
    async def test_admin_sees_folders_but_not_user_files(
        self, client_as, mock_s3, seed_org, seed_admin_folder, seed_user_folder,
    ):
        mock_s3.put_object(Bucket="test-bucket", Key="AdminFolder/UserSub/", Body=b"")
        mock_s3.put_object(Bucket="test-bucket", Key="AdminFolder/UserSub/secret.csv", Body=b"data")

        async with client_as(SUPER_ADMIN) as c:
            resp = await c.post(f"{BROWSE}/browse", json={
                "org_id": seed_org.id,
                "prefix": "AdminFolder/UserSub/",
            })
            assert resp.status_code == 200
            data = resp.json()
            assert len(data["files"]) == 0, "Admin should not see files in user folders"

    @pytest.mark.asyncio
    async def test_user_sees_files_in_user_folder(
        self, client_as, mock_s3, seed_org, seed_admin_folder, seed_user_folder, seed_user_rw_grant,
    ):
        mock_s3.put_object(Bucket="test-bucket", Key="AdminFolder/UserSub/", Body=b"")
        mock_s3.put_object(Bucket="test-bucket", Key="AdminFolder/UserSub/report.csv", Body=b"data")

        async with client_as(USER_RW) as c:
            resp = await c.post(f"{BROWSE}/browse", json={
                "org_id": seed_org.id,
                "prefix": "AdminFolder/UserSub/",
            })
            assert resp.status_code == 200
            data = resp.json()
            assert len(data["files"]) == 1
            assert data["files"][0]["name"] == "report.csv"

    @pytest.mark.asyncio
    async def test_user_sees_files_in_admin_folder(
        self, client_as, mock_s3, seed_org, seed_admin_folder, seed_user_rw_grant,
    ):
        mock_s3.put_object(Bucket="test-bucket", Key="AdminFolder/shared.csv", Body=b"data")

        async with client_as(USER_RW) as c:
            resp = await c.post(f"{BROWSE}/browse", json={
                "org_id": seed_org.id,
                "prefix": "AdminFolder/",
            })
            assert resp.status_code == 200
            data = resp.json()
            assert len(data["files"]) == 1


# =========================================================================
# TRASH — LIST / RESTORE / PURGE
# =========================================================================

class TestTrash:

    @pytest.mark.asyncio
    async def test_trash_list_scoped_to_user(
        self, client_as, mock_s3, seed_org, seed_admin_folder, seed_user_folder,
    ):
        """Regular user only sees their own trashed items."""
        mock_s3.put_object(
            Bucket="test-trash-bucket",
            Key=f"trash/{seed_org.id}/{USER_RW.id}/AdminFolder/UserSub/file.csv",
            Body=b"trashed",
            Metadata={"path": "AdminFolder/UserSub/file.csv", "bucket": "test-bucket",
                       "org_id": str(seed_org.id), "deleted_by": str(USER_RW.id)},
        )
        mock_s3.put_object(
            Bucket="test-trash-bucket",
            Key=f"trash/{seed_org.id}/{USER_RW_2.id}/AdminFolder/other.csv",
            Body=b"other",
            Metadata={"path": "AdminFolder/other.csv", "bucket": "test-bucket",
                       "org_id": str(seed_org.id), "deleted_by": str(USER_RW_2.id)},
        )

        async with client_as(USER_RW) as c:
            resp = await c.post(f"{BROWSE}/trash", json={"org_id": seed_org.id, "prefix": ""})
            data = resp.json()
            assert len(data["items"]) == 1
            assert "file.csv" in data["items"][0]["name"]

    @pytest.mark.asyncio
    async def test_admin_sees_all_org_trash(
        self, client_as, mock_s3, seed_org,
    ):
        mock_s3.put_object(
            Bucket="test-trash-bucket",
            Key=f"trash/{seed_org.id}/{USER_RW.id}/a.csv",
            Body=b"a",
            Metadata={"path": "a.csv", "bucket": "test-bucket",
                       "org_id": str(seed_org.id), "deleted_by": str(USER_RW.id)},
        )
        mock_s3.put_object(
            Bucket="test-trash-bucket",
            Key=f"trash/{seed_org.id}/{USER_RW_2.id}/b.csv",
            Body=b"b",
            Metadata={"path": "b.csv", "bucket": "test-bucket",
                       "org_id": str(seed_org.id), "deleted_by": str(USER_RW_2.id)},
        )

        async with client_as(SUPER_ADMIN) as c:
            resp = await c.post(f"{BROWSE}/trash", json={"org_id": seed_org.id, "prefix": ""})
            data = resp.json()
            assert len(data["items"]) == 2

    @pytest.mark.asyncio
    async def test_restore_single_file(
        self, client_as, mock_s3, seed_org, seed_user_rw_grant,
    ):
        trash_key = f"trash/{seed_org.id}/{USER_RW.id}/AdminFolder/restore-me.csv"
        mock_s3.put_object(
            Bucket="test-trash-bucket", Key=trash_key, Body=b"content",
            Metadata={"path": "AdminFolder/restore-me.csv", "bucket": "test-bucket",
                       "org_id": str(seed_org.id), "deleted_by": str(USER_RW.id)},
        )

        async with client_as(USER_RW) as c:
            resp = await c.post(f"{BROWSE}/trash/restore", json={
                "org_id": seed_org.id,
                "trash_key": trash_key,
            })
            assert resp.status_code == 200
            data = resp.json()
            assert data["objects_restored"] == 1

        obj = mock_s3.get_object(Bucket="test-bucket", Key="AdminFolder/restore-me.csv")
        assert obj["Body"].read() == b"content"

    @pytest.mark.asyncio
    async def test_user_cannot_restore_other_users_trash(
        self, client_as, mock_s3, seed_org,
    ):
        trash_key = f"trash/{seed_org.id}/{USER_RW_2.id}/stolen.csv"
        mock_s3.put_object(
            Bucket="test-trash-bucket", Key=trash_key, Body=b"x",
            Metadata={"path": "stolen.csv", "bucket": "test-bucket",
                       "org_id": str(seed_org.id), "deleted_by": str(USER_RW_2.id)},
        )

        async with client_as(USER_RW) as c:
            resp = await c.post(f"{BROWSE}/trash/restore", json={
                "org_id": seed_org.id,
                "trash_key": trash_key,
            })
            assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_purge_single_file(
        self, client_as, mock_s3, seed_org,
    ):
        trash_key = f"trash/{seed_org.id}/{USER_RW.id}/gone.csv"
        mock_s3.put_object(
            Bucket="test-trash-bucket", Key=trash_key, Body=b"bye",
            Metadata={"path": "gone.csv", "bucket": "test-bucket",
                       "org_id": str(seed_org.id), "deleted_by": str(USER_RW.id)},
        )

        async with client_as(USER_RW) as c:
            resp = await c.post(f"{BROWSE}/trash/purge", json={
                "org_id": seed_org.id,
                "trash_key": trash_key,
            })
            assert resp.status_code == 200
            assert resp.json()["objects_purged"] == 1

    @pytest.mark.asyncio
    async def test_user_cannot_purge_other_users_trash(
        self, client_as, mock_s3, seed_org,
    ):
        trash_key = f"trash/{seed_org.id}/{USER_RW_2.id}/not-yours.csv"
        mock_s3.put_object(
            Bucket="test-trash-bucket", Key=trash_key, Body=b"x",
            Metadata={"path": "not-yours.csv", "bucket": "test-bucket",
                       "org_id": str(seed_org.id), "deleted_by": str(USER_RW_2.id)},
        )

        async with client_as(USER_RW) as c:
            resp = await c.post(f"{BROWSE}/trash/purge", json={
                "org_id": seed_org.id,
                "trash_key": trash_key,
            })
            assert resp.status_code == 403


# =========================================================================
# CROSS-ORG ISOLATION
# =========================================================================

class TestCrossOrgIsolation:

    @pytest.mark.asyncio
    async def test_other_org_user_cannot_browse(
        self, client_as, mock_s3, seed_org,
    ):
        async with client_as(USER_OTHER_ORG) as c:
            resp = await c.post(f"{BROWSE}/browse", json={
                "org_id": seed_org.id,
                "prefix": "",
            })
            assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_other_org_user_cannot_create_folder(
        self, client_as, mock_s3, seed_org,
    ):
        async with client_as(USER_OTHER_ORG) as c:
            resp = await c.post(f"{BROWSE}/folders/create", json={
                "org_id": seed_org.id,
                "parent_prefix": "",
                "name": "Intruder",
            })
            assert resp.status_code == 403
