"""
Tests for upload file-type allowlist enforcement.

Covers:
- Allowed extensions pass on /services/initiate (200/UploadId returned)
- Disallowed extensions rejected with 415 on /services/initiate
- Allowed extensions pass on /services/upload/v2 (no 415)
- Disallowed extensions rejected with 415 on /services/upload/v2
- Compound extension .csv.gz is allowed
- Case-insensitive matching (e.g. .CSV, .Parquet)
- /services/v2/upload rejects invalid token with 401
- /services/v2/upload rejects disallowed extension with 415
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import io
import pytest
import pytest_asyncio

from tests.conftest import (
    SUPER_ADMIN,
    MASTER_ADMIN,
    USER_RW,
    TestSession,
)
from db.models import Organization, UserGroup, GroupMembership, FolderGrant


API = "/api/v2/explorer/services"


@pytest.fixture
def seed_org_for_upload(db):
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
def seed_user_grant(db, seed_org_for_upload):
    """Give USER_RW a write grant on 'Data/' prefix."""
    group = UserGroup(name="TestGroup", org_id=seed_org_for_upload.id, created_by=1)
    db.add(group)
    db.commit()
    db.refresh(group)

    membership = GroupMembership(group_id=group.id, user_id=USER_RW.id, added_by=1)
    db.add(membership)

    grant = FolderGrant(
        group_id=group.id,
        org_id=seed_org_for_upload.id,
        prefix="Data/",
        access_level="read_write",
        created_by=1,
    )
    db.add(grant)
    db.commit()
    return grant


# ============================================================
# /services/initiate — Allowed extensions
# ============================================================

ALLOWED_FILES = [
    "report.parquet",
    "data.orc",
    "sales.csv",
    "config.json",
    "archive.zip",
    "compressed.gz",
    "logs.csv.gz",
    "sheet.xlsx",
    "notes.txt",
    "document.pdf",
    "proposal.docx",
    "screenshot.png",
]

DISALLOWED_FILES = [
    "presentation.pptx",
    "video.mp4",
    "script.py",
    "binary.exe",
    "image.bmp",
    "archive.rar",
    "noextension",
]


@pytest.mark.asyncio
@pytest.mark.parametrize("filename", ALLOWED_FILES)
async def test_initiate_allowed_extensions(client_as, mock_s3, seed_org_for_upload, filename):
    """Allowed file types should not get 415 on /services/initiate."""
    async with client_as(MASTER_ADMIN) as c:
        resp = await c.post(f"{API}/initiate", json={
            "userid": 0,
            "name": f"Data/{filename}",
            "author": "TestUser",
            "basePath": "/test-bucket",
        })
        assert resp.status_code != 415, f"{filename} should be allowed but got 415"


@pytest.mark.asyncio
@pytest.mark.parametrize("filename", DISALLOWED_FILES)
async def test_initiate_disallowed_extensions(client_as, mock_s3, seed_org_for_upload, filename):
    """Disallowed file types should get 415 on /services/initiate."""
    async with client_as(MASTER_ADMIN) as c:
        resp = await c.post(f"{API}/initiate", json={
            "userid": 0,
            "name": f"Data/{filename}",
            "author": "TestUser",
            "basePath": "/test-bucket",
        })
        assert resp.status_code == 415, f"{filename} should be rejected but got {resp.status_code}"
        assert "not allowed" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_initiate_case_insensitive(client_as, mock_s3, seed_org_for_upload):
    """Extension check should be case-insensitive."""
    async with client_as(MASTER_ADMIN) as c:
        for filename in ["Report.CSV", "DATA.PARQUET", "file.Json", "pic.PNG"]:
            resp = await c.post(f"{API}/initiate", json={
                "userid": 0,
                "name": f"Data/{filename}",
                "author": "TestUser",
                "basePath": "/test-bucket",
            })
            assert resp.status_code != 415, f"{filename} should be allowed (case-insensitive)"


# ============================================================
# /services/upload/v2 — Extension enforcement
# ============================================================

@pytest.mark.asyncio
async def test_upload_v2_allowed_extension(client_as, mock_s3, seed_org_for_upload, seed_user_grant):
    """Allowed extension should not get 415 on /services/upload/v2."""
    async with client_as(USER_RW) as c:
        file_content = b"col1,col2\n1,2\n"
        resp = await c.post(
            f"{API}/upload/v2",
            data={"path": "Data/report.csv", "basePath": "/test-bucket"},
            files={"file": ("report.csv", io.BytesIO(file_content), "text/csv")},
        )
        assert resp.status_code != 415


@pytest.mark.asyncio
async def test_upload_v2_disallowed_extension(client_as, mock_s3, seed_org_for_upload, seed_user_grant):
    """Disallowed extension should get 415 on /services/upload/v2."""
    async with client_as(USER_RW) as c:
        file_content = b"binary data"
        resp = await c.post(
            f"{API}/upload/v2",
            data={"path": "Data/malware.exe", "basePath": "/test-bucket"},
            files={"file": ("malware.exe", io.BytesIO(file_content), "application/octet-stream")},
        )
        assert resp.status_code == 415


# ============================================================
# /services/v2/upload — Token auth (legacy removed)
# ============================================================

@pytest.mark.asyncio
@pytest.mark.skip(reason="legacy v2 removed")
async def test_v2_upload_invalid_token():
    pass


@pytest.mark.asyncio
@pytest.mark.skip(reason="legacy v2 removed")
async def test_v2_upload_disallowed_extension():
    pass


@pytest.mark.asyncio
@pytest.mark.skip(reason="legacy v2 removed")
async def test_v2_upload_allowed_extension_passes_validation():
    pass
