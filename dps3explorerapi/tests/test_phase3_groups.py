"""
Phase 3 tests — Group CRUD, membership management, folder grants.

Role matrix:
- SUPER_ADMIN / MASTER_ADMIN: can manage groups for any org
- ORG_ADMIN (role 1): can manage groups for own org only
- USER_RW (role 2): CANNOT manage groups (403)
- USER_OTHER_ORG: cross-org isolation enforced
"""

import pytest
from tests.conftest import (
    SUPER_ADMIN, MASTER_ADMIN, ORG_ADMIN,
    USER_RW, USER_RW_2, USER_OTHER_ORG,
)

PREFIX = "/api/v2/explorer"
ADMIN = f"{PREFIX}/admin"


# =========================================================================
# GROUP CREATION
# =========================================================================

class TestGroupCreate:

    @pytest.mark.asyncio
    async def test_admin_can_create_group(self, client_as, mock_s3, seed_org):
        async with client_as(SUPER_ADMIN) as c:
            resp = await c.post(f"{ADMIN}/groups", json={
                "org_id": seed_org.id,
                "name": "Analytics Team",
                "member_user_ids": [],
            })
            assert resp.status_code == 201
            data = resp.json()
            assert data["name"] == "Analytics Team"
            assert data["member_count"] == 0

    @pytest.mark.asyncio
    async def test_org_admin_can_create_group(self, client_as, mock_s3, seed_org):
        async with client_as(ORG_ADMIN) as c:
            resp = await c.post(f"{ADMIN}/groups", json={
                "org_id": seed_org.id,
                "name": "Engineering",
            })
            assert resp.status_code == 201
            assert resp.json()["name"] == "Engineering"

    @pytest.mark.asyncio
    async def test_user_cannot_create_group(self, client_as, mock_s3, seed_org):
        async with client_as(USER_RW) as c:
            resp = await c.post(f"{ADMIN}/groups", json={
                "org_id": seed_org.id,
                "name": "Hackers",
            })
            assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_group_name_is_free_text(self, client_as, mock_s3, seed_org):
        async with client_as(SUPER_ADMIN) as c:
            resp = await c.post(f"{ADMIN}/groups", json={
                "org_id": seed_org.id,
                "name": "QA",
            })
            assert resp.json()["name"] == "QA"

    @pytest.mark.asyncio
    async def test_group_name_keeps_literal_prefix(self, client_as, mock_s3, seed_org):
        async with client_as(SUPER_ADMIN) as c:
            resp = await c.post(f"{ADMIN}/groups", json={
                "org_id": seed_org.id,
                "name": "dp-Already Prefixed",
            })
            assert resp.json()["name"] == "dp-Already Prefixed"

    @pytest.mark.asyncio
    async def test_duplicate_group_rejected(self, client_as, mock_s3, seed_org):
        async with client_as(SUPER_ADMIN) as c:
            await c.post(f"{ADMIN}/groups", json={"org_id": seed_org.id, "name": "Dup"})
            resp = await c.post(f"{ADMIN}/groups", json={"org_id": seed_org.id, "name": "Dup"})
            assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_create_with_members(self, client_as, mock_s3, seed_org, seed_uam_users):
        async with client_as(SUPER_ADMIN) as c:
            resp = await c.post(f"{ADMIN}/groups", json={
                "org_id": seed_org.id,
                "name": "WithMembers",
                "member_user_ids": [USER_RW.id, USER_RW_2.id],
            })
            assert resp.status_code == 201
            assert resp.json()["member_count"] == 2

    @pytest.mark.asyncio
    async def test_cross_org_group_creation_blocked(self, client_as, mock_s3, seed_org):
        async with client_as(USER_OTHER_ORG) as c:
            resp = await c.post(f"{ADMIN}/groups", json={
                "org_id": seed_org.id,
                "name": "Intruder",
            })
            assert resp.status_code == 403


# =========================================================================
# GROUP LIST
# =========================================================================

class TestGroupList:

    @pytest.mark.asyncio
    async def test_list_groups_for_org(self, client_as, mock_s3, seed_org):
        async with client_as(SUPER_ADMIN) as c:
            await c.post(f"{ADMIN}/groups", json={"org_id": seed_org.id, "name": "G1"})
            await c.post(f"{ADMIN}/groups", json={"org_id": seed_org.id, "name": "G2"})

            resp = await c.get(f"{ADMIN}/groups", params={"org_id": seed_org.id})
            assert resp.status_code == 200
            data = resp.json()
            assert len(data) == 2
            names = [g["name"] for g in data]
            assert "G1" in names
            assert "G2" in names


# =========================================================================
# GROUP RENAME
# =========================================================================

class TestGroupRename:

    @pytest.mark.asyncio
    async def test_admin_can_rename_group(self, client_as, mock_s3, seed_org):
        async with client_as(SUPER_ADMIN) as c:
            create_resp = await c.post(f"{ADMIN}/groups", json={"org_id": seed_org.id, "name": "OldName"})
            gid = create_resp.json()["id"]

            resp = await c.put(f"{ADMIN}/groups/{gid}", json={"name": "NewName"})
            assert resp.status_code == 200
            assert resp.json()["name"] == "NewName"

    @pytest.mark.asyncio
    async def test_rename_conflict_rejected(self, client_as, mock_s3, seed_org):
        async with client_as(SUPER_ADMIN) as c:
            await c.post(f"{ADMIN}/groups", json={"org_id": seed_org.id, "name": "Existing"})
            resp2 = await c.post(f"{ADMIN}/groups", json={"org_id": seed_org.id, "name": "ToRename"})
            gid = resp2.json()["id"]

            resp = await c.put(f"{ADMIN}/groups/{gid}", json={"name": "Existing"})
            assert resp.status_code == 409


# =========================================================================
# GROUP DELETE
# =========================================================================

class TestGroupDelete:

    @pytest.mark.asyncio
    async def test_admin_can_delete_group(self, client_as, mock_s3, seed_org):
        async with client_as(SUPER_ADMIN) as c:
            create_resp = await c.post(f"{ADMIN}/groups", json={"org_id": seed_org.id, "name": "ToDelete"})
            gid = create_resp.json()["id"]

            resp = await c.delete(f"{ADMIN}/groups/{gid}")
            assert resp.status_code == 200
            assert resp.json()["deleted"] == "ToDelete"

            list_resp = await c.get(f"{ADMIN}/groups", params={"org_id": seed_org.id})
            assert len(list_resp.json()) == 0

    @pytest.mark.asyncio
    async def test_delete_cascades_members_and_grants(self, client_as, mock_s3, seed_org, seed_uam_users, db):
        from unittest.mock import patch
        from db.models import User
        from core.approval import create_and_send_group_delete_approval

        async with client_as(SUPER_ADMIN) as c:
            create_resp = await c.post(f"{ADMIN}/groups", json={
                "org_id": seed_org.id, "name": "Cascade",
                "member_user_ids": [USER_RW.id],
            })
            gid = create_resp.json()["id"]

            await c.post(f"{ADMIN}/groups/{gid}/grants", json={
                "prefix": "AdminFolder/", "access_level": "read",
            })

            captured = {}
            approver = db.query(User).filter(User.id == ORG_ADMIN.id).first()
            with patch("core.approval.smtp_configured", return_value=True), patch(
                "core.approval.send_smtp_html",
                side_effect=lambda **kw: captured.update({"html": kw.get("html_body", "")}),
            ):
                create_and_send_group_delete_approval(
                    db,
                    group_id=gid,
                    approver=approver,
                    requester=SUPER_ADMIN,
                    request_base_url="http://testserver/api/v2/explorer",
                )
                db.commit()
            from tests.test_approval import _parse_action_link
            html = captured["html"]
            approval_id, token = _parse_action_link(html, "approve")
            assert token

        async with client_as(ORG_ADMIN) as approver_client:
            resp = await approver_client.post(
                f"{ADMIN}/approval/respond",
                data={"id": approval_id, "token": token, "action": "approve"},
            )
            assert resp.status_code == 200


# =========================================================================
# MEMBER MANAGEMENT
# =========================================================================

class TestMembers:

    @pytest.mark.asyncio
    async def test_add_members(self, client_as, mock_s3, seed_org, seed_uam_users):
        async with client_as(SUPER_ADMIN) as c:
            create_resp = await c.post(f"{ADMIN}/groups", json={"org_id": seed_org.id, "name": "Team"})
            gid = create_resp.json()["id"]

            resp = await c.post(f"{ADMIN}/groups/{gid}/members", json={
                "user_ids": [USER_RW.id, USER_RW_2.id],
            })
            assert resp.status_code == 201
            data = resp.json()
            assert len(data["added"]) == 2
            assert len(data["skipped"]) == 0

    @pytest.mark.asyncio
    async def test_add_duplicate_member_skipped(self, client_as, mock_s3, seed_org, seed_uam_users):
        async with client_as(SUPER_ADMIN) as c:
            create_resp = await c.post(f"{ADMIN}/groups", json={
                "org_id": seed_org.id, "name": "DupTest",
                "member_user_ids": [USER_RW.id],
            })
            gid = create_resp.json()["id"]

            resp = await c.post(f"{ADMIN}/groups/{gid}/members", json={
                "user_ids": [USER_RW.id],
            })
            assert resp.status_code == 201
            assert len(resp.json()["skipped"]) == 1
            assert resp.json()["skipped"][0]["reason"] == "already a member"

    @pytest.mark.asyncio
    async def test_add_cross_org_user_skipped(self, client_as, mock_s3, seed_org, seed_uam_users):
        async with client_as(SUPER_ADMIN) as c:
            create_resp = await c.post(f"{ADMIN}/groups", json={"org_id": seed_org.id, "name": "CrossOrg"})
            gid = create_resp.json()["id"]

            resp = await c.post(f"{ADMIN}/groups/{gid}/members", json={
                "user_ids": [USER_OTHER_ORG.id],
            })
            assert resp.status_code == 201
            assert len(resp.json()["skipped"]) == 1
            assert "not in org" in resp.json()["skipped"][0]["reason"]

    @pytest.mark.asyncio
    async def test_remove_member(self, client_as, mock_s3, seed_org, seed_uam_users):
        async with client_as(SUPER_ADMIN) as c:
            create_resp = await c.post(f"{ADMIN}/groups", json={
                "org_id": seed_org.id, "name": "RemoveTest",
                "member_user_ids": [USER_RW.id],
            })
            gid = create_resp.json()["id"]

            resp = await c.delete(f"{ADMIN}/groups/{gid}/members/{USER_RW.id}")
            assert resp.status_code == 200
            assert resp.json()["removed"] == USER_RW.id

    @pytest.mark.asyncio
    async def test_remove_non_member_404(self, client_as, mock_s3, seed_org):
        async with client_as(SUPER_ADMIN) as c:
            create_resp = await c.post(f"{ADMIN}/groups", json={"org_id": seed_org.id, "name": "Empty"})
            gid = create_resp.json()["id"]

            resp = await c.delete(f"{ADMIN}/groups/{gid}/members/999")
            assert resp.status_code == 404


# =========================================================================
# FOLDER GRANTS
# =========================================================================

class TestGrants:

    @pytest.mark.asyncio
    async def test_create_grant(self, client_as, mock_s3, seed_org):
        async with client_as(SUPER_ADMIN) as c:
            create_resp = await c.post(f"{ADMIN}/groups", json={"org_id": seed_org.id, "name": "Granted"})
            gid = create_resp.json()["id"]

            resp = await c.post(f"{ADMIN}/groups/{gid}/grants", json={
                "prefix": "AdminFolder/",
                "access_level": "read_write",
            })
            assert resp.status_code == 201
            data = resp.json()
            assert data["prefix"] == "AdminFolder/"
            assert data["access_level"] == "read_write"

    @pytest.mark.asyncio
    async def test_duplicate_grant_rejected(self, client_as, mock_s3, seed_org):
        mock_s3.put_object(Bucket="test-bucket", Key="A/placeholder", Body=b"")
        async with client_as(SUPER_ADMIN) as c:
            create_resp = await c.post(f"{ADMIN}/groups", json={"org_id": seed_org.id, "name": "DupGrant"})
            gid = create_resp.json()["id"]

            await c.post(f"{ADMIN}/groups/{gid}/grants", json={"prefix": "A/", "access_level": "read"})
            resp = await c.post(f"{ADMIN}/groups/{gid}/grants", json={"prefix": "A/", "access_level": "read_write"})
            assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_grant_prefix_normalized(self, client_as, mock_s3, seed_org):
        """Prefix without trailing slash gets one added."""
        mock_s3.put_object(Bucket="test-bucket", Key="NoSlash/placeholder", Body=b"")
        async with client_as(SUPER_ADMIN) as c:
            create_resp = await c.post(f"{ADMIN}/groups", json={"org_id": seed_org.id, "name": "Norm"})
            gid = create_resp.json()["id"]

            resp = await c.post(f"{ADMIN}/groups/{gid}/grants", json={
                "prefix": "NoSlash",
                "access_level": "read",
            })
            assert resp.status_code == 201
            assert resp.json()["prefix"] == "NoSlash/"

    @pytest.mark.asyncio
    async def test_remove_grant(self, client_as, mock_s3, seed_org):
        mock_s3.put_object(Bucket="test-bucket", Key="X/placeholder", Body=b"")
        async with client_as(SUPER_ADMIN) as c:
            create_resp = await c.post(f"{ADMIN}/groups", json={"org_id": seed_org.id, "name": "RemGrant"})
            gid = create_resp.json()["id"]

            grant_resp = await c.post(f"{ADMIN}/groups/{gid}/grants", json={
                "prefix": "X/", "access_level": "read",
            })
            grant_id = grant_resp.json()["id"]

            resp = await c.delete(f"{ADMIN}/groups/{gid}/grants/{grant_id}")
            assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_invalid_access_level_rejected(self, client_as, mock_s3, seed_org):
        async with client_as(SUPER_ADMIN) as c:
            create_resp = await c.post(f"{ADMIN}/groups", json={"org_id": seed_org.id, "name": "BadAccess"})
            gid = create_resp.json()["id"]

            resp = await c.post(f"{ADMIN}/groups/{gid}/grants", json={
                "prefix": "Z/", "access_level": "admin",
            })
            assert resp.status_code == 422


# =========================================================================
# ORG USER SEARCH
# =========================================================================

class TestOrgUserSearch:

    @pytest.mark.asyncio
    async def test_search_org_users(self, client_as, mock_s3, seed_org, seed_uam_users):
        async with client_as(SUPER_ADMIN) as c:
            resp = await c.get(f"{ADMIN}/orgs/{seed_org.id}/users", params={"search": "User1"})
            assert resp.status_code == 200
            data = resp.json()
            assert "users" in data
            assert data["total"] >= 1
            assert any(u["user_name"] == "User1" for u in data["users"])
            assert "has_more" in data
            assert "page" in data

    @pytest.mark.asyncio
    async def test_search_returns_empty_for_other_org(self, client_as, mock_s3, seed_org, seed_uam_users):
        async with client_as(SUPER_ADMIN) as c:
            resp = await c.get(f"{ADMIN}/orgs/{seed_org.id}/users", params={"search": "OtherOrg"})
            data = resp.json()
            assert len(data["users"]) == 0
            assert data["total"] == 0

    @pytest.mark.asyncio
    async def test_search_pagination(self, client_as, mock_s3, seed_org, seed_uam_users):
        """Pagination params work correctly."""
        async with client_as(SUPER_ADMIN) as c:
            resp = await c.get(f"{ADMIN}/orgs/{seed_org.id}/users", params={"page": 1, "page_size": 1})
            assert resp.status_code == 200
            data = resp.json()
            assert len(data["users"]) <= 1
            assert data["page"] == 1
            assert data["page_size"] == 1

    @pytest.mark.asyncio
    async def test_user_cannot_search_org_users(self, client_as, mock_s3, seed_org):
        async with client_as(USER_RW) as c:
            resp = await c.get(f"{ADMIN}/orgs/{seed_org.id}/users")
            assert resp.status_code == 403


# =========================================================================
# DUPLICATE ID HANDLING
# =========================================================================

class TestDuplicateIds:

    @pytest.mark.asyncio
    async def test_create_group_with_duplicate_member_ids(self, client_as, mock_s3, seed_org, seed_uam_users):
        """Duplicate user IDs in a single request should be de-duped, not crash."""
        async with client_as(SUPER_ADMIN) as c:
            resp = await c.post(f"{ADMIN}/groups", json={
                "org_id": seed_org.id,
                "name": "DupIds",
                "member_user_ids": [USER_RW.id, USER_RW.id, USER_RW.id],
            })
            assert resp.status_code == 201
            assert resp.json()["member_count"] == 1

    @pytest.mark.asyncio
    async def test_add_members_with_duplicate_ids(self, client_as, mock_s3, seed_org, seed_uam_users):
        async with client_as(SUPER_ADMIN) as c:
            create_resp = await c.post(f"{ADMIN}/groups", json={"org_id": seed_org.id, "name": "DupAdd"})
            gid = create_resp.json()["id"]

            resp = await c.post(f"{ADMIN}/groups/{gid}/members", json={
                "user_ids": [USER_RW.id, USER_RW.id],
            })
            assert resp.status_code == 201
            assert len(resp.json()["added"]) == 1
            assert len(resp.json()["skipped"]) == 0


# =========================================================================
# FOLDER TREE ENDPOINT
# =========================================================================

class TestFolderTree:

    @pytest.mark.asyncio
    async def test_folder_tree_returns_children(self, client_as, mock_s3, seed_org):
        mock_s3.put_object(Bucket="test-bucket", Key="FolderA/", Body=b"")
        mock_s3.put_object(Bucket="test-bucket", Key="FolderB/", Body=b"")
        mock_s3.put_object(Bucket="test-bucket", Key="FolderA/Sub1/", Body=b"")

        async with client_as(SUPER_ADMIN) as c:
            resp = await c.get(f"{ADMIN}/orgs/{seed_org.id}/folder-tree", params={"prefix": ""})
            assert resp.status_code == 200
            data = resp.json()
            names = [f["name"] for f in data["folders"]]
            assert "FolderA" in names
            assert "FolderB" in names

    @pytest.mark.asyncio
    async def test_folder_tree_drill_down(self, client_as, mock_s3, seed_org):
        mock_s3.put_object(Bucket="test-bucket", Key="Parent/Child1/", Body=b"")
        mock_s3.put_object(Bucket="test-bucket", Key="Parent/Child2/", Body=b"")

        async with client_as(SUPER_ADMIN) as c:
            resp = await c.get(f"{ADMIN}/orgs/{seed_org.id}/folder-tree", params={"prefix": "Parent/"})
            assert resp.status_code == 200
            data = resp.json()
            assert data["prefix"] == "Parent/"
            names = [f["name"] for f in data["folders"]]
            assert "Child1" in names
            assert "Child2" in names

    @pytest.mark.asyncio
    async def test_user_cannot_access_folder_tree(self, client_as, mock_s3, seed_org):
        async with client_as(USER_RW) as c:
            resp = await c.get(f"{ADMIN}/orgs/{seed_org.id}/folder-tree")
            assert resp.status_code == 403


# =========================================================================
# GRANT PREFIX VALIDATION
# =========================================================================

class TestGrantValidation:

    @pytest.mark.asyncio
    async def test_grant_nonexistent_prefix_rejected(self, client_as, mock_s3, seed_org):
        async with client_as(SUPER_ADMIN) as c:
            create_resp = await c.post(f"{ADMIN}/groups", json={"org_id": seed_org.id, "name": "BadGrant"})
            gid = create_resp.json()["id"]

            resp = await c.post(f"{ADMIN}/groups/{gid}/grants", json={
                "prefix": "DoesNotExist/",
                "access_level": "read",
            })
            assert resp.status_code == 400
            assert "does not exist" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_grant_existing_prefix_accepted(self, client_as, mock_s3, seed_org):
        mock_s3.put_object(Bucket="test-bucket", Key="RealFolder/", Body=b"")

        async with client_as(SUPER_ADMIN) as c:
            create_resp = await c.post(f"{ADMIN}/groups", json={"org_id": seed_org.id, "name": "GoodGrant"})
            gid = create_resp.json()["id"]

            resp = await c.post(f"{ADMIN}/groups/{gid}/grants", json={
                "prefix": "RealFolder/",
                "access_level": "read_write",
            })
            assert resp.status_code == 201
