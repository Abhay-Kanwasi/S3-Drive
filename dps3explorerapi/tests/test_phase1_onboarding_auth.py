"""
Phase 1 tests — Organization onboarding & auth/role enforcement.

Covers:
- Only super_admin / master_admin can onboard orgs
- org_admin (role 1) and regular users are denied
- Duplicate onboarding is rejected
- List orgs is role-gated
- UAM endpoints require auth
"""

import pytest
from tests.conftest import (
    SUPER_ADMIN, MASTER_ADMIN, ORG_ADMIN, USER_RW, USER_OTHER_ORG,
)

PREFIX = "/api/v2/explorer"


def _onboard_payload(org_key="org-new", org_name="NewOrg", bucket_name="test-bucket"):
    return {
        "org_key": org_key,
        "org_name": org_name,
        "bucket_name": bucket_name,
    }


# ---------- Onboarding role enforcement ----------

@pytest.mark.asyncio
async def test_super_admin_can_onboard(client_as, mock_s3, seed_org):
    mock_s3.create_bucket(Bucket="onboard-bucket")
    async with client_as(SUPER_ADMIN) as c:
        resp = await c.post(
            f"{PREFIX}/admin/orgs/onboard",
            json=_onboard_payload(org_key="org-new", bucket_name="onboard-bucket"),
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["bucket_name"] == "onboard-bucket"
        assert data["org_name"] is not None
        assert data.get("org_key") == "org-new" or data.get("subscription_id") == "org-new"


@pytest.mark.asyncio
async def test_master_admin_can_onboard(client_as, mock_s3, seed_org):
    mock_s3.create_bucket(Bucket="another-bucket")
    async with client_as(MASTER_ADMIN) as c:
        resp = await c.post(
            f"{PREFIX}/admin/orgs/onboard",
            json=_onboard_payload(org_key="org-master", bucket_name="another-bucket"),
        )
        assert resp.status_code == 201


@pytest.mark.asyncio
async def test_org_admin_cannot_onboard(client_as, mock_s3):
    async with client_as(ORG_ADMIN) as c:
        resp = await c.post(
            f"{PREFIX}/admin/orgs/onboard",
            json=_onboard_payload(),
        )
        assert resp.status_code == 403


@pytest.mark.asyncio
async def test_regular_user_cannot_onboard(client_as, mock_s3):
    async with client_as(USER_RW) as c:
        resp = await c.post(
            f"{PREFIX}/admin/orgs/onboard",
            json=_onboard_payload(),
        )
        assert resp.status_code == 403


# ---------- Duplicate onboarding ----------

@pytest.mark.asyncio
async def test_duplicate_subscription_rejected(client_as, mock_s3, seed_org):
    mock_s3.create_bucket(Bucket="new-bucket")
    async with client_as(SUPER_ADMIN) as c:
        resp = await c.post(
            f"{PREFIX}/admin/orgs/onboard",
            json=_onboard_payload(org_key="org-001", bucket_name="new-bucket"),
        )
        assert resp.status_code == 409


@pytest.mark.asyncio
async def test_legacy_inactive_binding_rejected(client_as, mock_s3, seed_org, db):
    from db.models import Organization

    db.add(
        Organization(
            org_key="org-ghost",
            org_name="LegacyGhost",
            bucket_name="ghost-bucket",
            region="us-east-1",
            onboarded_by=1,
            is_active=False,
        )
    )
    db.commit()
    mock_s3.create_bucket(Bucket="new-bucket")
    async with client_as(SUPER_ADMIN) as c:
        resp = await c.post(
            f"{PREFIX}/admin/orgs/onboard",
            json=_onboard_payload(org_key="org-ghost", bucket_name="new-bucket"),
        )
    assert resp.status_code == 409
    detail = resp.json()["detail"].lower()
    assert "inactive" in detail and ("org_key" in detail or "bucket" in detail)


# ---------- List orgs role enforcement ----------

@pytest.mark.asyncio
async def test_super_admin_can_list_orgs(client_as, seed_org):
    async with client_as(SUPER_ADMIN) as c:
        resp = await c.get(f"{PREFIX}/admin/orgs")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        assert data[0]["bucket_name"] == "test-bucket"
        row = data[0]
        assert row.get("org_key") == "org-001" or row.get("subscription_id") == "org-001"


@pytest.mark.asyncio
async def test_regular_user_cannot_list_orgs(client_as, seed_org):
    async with client_as(USER_RW) as c:
        resp = await c.get(f"{PREFIX}/admin/orgs")
        assert resp.status_code == 403


# ---------- UAM endpoints require auth ----------

@pytest.mark.asyncio
async def test_uam_folders_returns_data(client_as):
    async with client_as(USER_RW) as c:
        resp = await c.get(f"{PREFIX}/uam/folders")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_download_is_disabled(client_as):
    async with client_as(USER_RW) as c:
        resp = await c.get(f"{PREFIX}/services/download", params={
            "basePath": "dp-testorg/",
            "filename": "test.csv",
            "file_key": "AdminFolder/test.csv",
        })
        assert resp.status_code == 410
