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
from db.models import Org, UserGroup, GroupMembership, FolderGrant, Explorer, TokenRepository


API = "/api/v2/explorer/services"


@pytest.fixture
def seed_org_for_upload(db):
    """Seed an org so initiate can resolve the bucket."""
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
def seed_user_grant(db, seed_org_for_upload):
    """Give USER_RW a write grant on 'Data/' prefix."""
    group = UserGroup(name="dp-TestGroup", org_id=seed_org_for_upload.id, created_by=1)
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


@pytest.fixture
def seed_legacy_explorer(db):
    """Seed a legacy explorer entry + token for /v2/upload tests."""
    entry = Explorer(
        user_id=USER_RW.id,
        bucket_name="test-bucket",
        folder_name="TestOrg",
        folder_path="dp-testorg",
        relative_path="/",
        is_admin=False,
    )
    db.add(entry)

    token = TokenRepository(
        user_id=USER_RW.id,
        token="valid-test-token",
        is_expired=False,
    )
    db.add(token)
    db.commit()
    return entry, token


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
# /services/v2/upload — Token auth + extension enforcement
# ============================================================

@pytest.mark.asyncio
async def test_v2_upload_invalid_token(client_as, mock_s3, seed_legacy_explorer):
    """Invalid token should return 401."""
    async with client_as(USER_RW) as c:
        file_content = b"data"
        resp = await c.post(
            f"{API}/v2/upload",
            data={
                "token": "invalid-token",
                "folderpath": "/",
                "year": "2026",
                "month": "05",
            },
            files={"file": ("data.csv", io.BytesIO(file_content), "text/csv")},
        )
        assert resp.status_code == 401
        assert "Invalid or expired token" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_v2_upload_disallowed_extension(client_as, mock_s3, seed_legacy_explorer):
    """Valid token but disallowed extension should return 415."""
    async with client_as(USER_RW) as c:
        file_content = b"data"
        resp = await c.post(
            f"{API}/v2/upload",
            data={
                "token": "valid-test-token",
                "folderpath": "/",
                "year": "2026",
                "month": "05",
            },
            files={"file": ("script.py", io.BytesIO(file_content), "text/plain")},
        )
        assert resp.status_code == 415


@pytest.mark.asyncio
async def test_v2_upload_allowed_extension_passes_validation(client_as, mock_s3, seed_legacy_explorer):
    """Valid token + allowed extension should pass auth and extension checks (not 401/415)."""
    async with client_as(USER_RW) as c:
        file_content = b"col1,col2\n1,2\n"
        resp = await c.post(
            f"{API}/v2/upload",
            data={
                "token": "valid-test-token",
                "folderpath": "/",
                "year": "2026",
                "month": "05",
            },
            files={"file": ("data.csv", io.BytesIO(file_content), "text/csv")},
        )
        # Should not be rejected by auth or extension check.
        # May be 200 or 500 depending on S3 mock availability for put_objects,
        # but must NOT be 401 or 415.
        assert resp.status_code not in (401, 415)
