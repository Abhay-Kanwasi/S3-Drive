"""
Tests for MASTER_ADMIN Platform Settings (dynamic file formats + max upload size).

Covers:
- GET /admin/settings returns object-format extensions with colors
- PUT /admin/settings — add new extension with color
- PUT /admin/settings — remove an extension, upload then rejected
- PUT /admin/settings — invalid hex color normalized to default gray
- PUT /admin/settings — max_upload_bytes enforcement on /services/initiate
- PUT /admin/settings — max_upload_bytes below minimum rejected (422)
- GET /services/upload-constraints returns extension_colors
- Non-MASTER_ADMIN cannot access /admin/settings (403)
- After MASTER_ADMIN adds .avro, upload of .avro file is accepted
- After MASTER_ADMIN removes .csv, upload of .csv file is rejected
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
    ORG_ADMIN,
    USER_RW,
    TestSession,
)
from db.models import Org, UserGroup, GroupMembership, FolderGrant, PlatformSettings


ADMIN_API = "/api/v2/explorer/admin"
SERVICES_API = "/api/v2/explorer/services"


@pytest.fixture
def seed_org(db):
    """Seed org for upload tests."""
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
def seed_user_grant(db, seed_org):
    """Give USER_RW write access on Data/ prefix."""
    group = UserGroup(name="dp-TestGroup", org_id=seed_org.id, created_by=1)
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


# ============================================================
# GET /admin/settings — Returns object format with colors
# ============================================================

@pytest.mark.asyncio
async def test_get_settings_returns_objects_with_colors(client_as):
    """GET /admin/settings should return allowed_extensions as objects with ext and color."""
    async with client_as(MASTER_ADMIN) as c:
        resp = await c.get(f"{ADMIN_API}/settings")
        assert resp.status_code == 200
        data = resp.json()
        assert "allowed_extensions" in data
        assert "max_upload_bytes" in data
        exts = data["allowed_extensions"]
        assert len(exts) > 0
        for entry in exts:
            assert "ext" in entry
            assert "color" in entry
            assert entry["ext"].startswith(".")
            assert entry["color"].startswith("#")


@pytest.mark.asyncio
async def test_get_settings_has_default_formats(client_as):
    """Default formats should be present in settings."""
    async with client_as(MASTER_ADMIN) as c:
        resp = await c.get(f"{ADMIN_API}/settings")
        data = resp.json()
        ext_list = [e["ext"] for e in data["allowed_extensions"]]
        for expected in [".csv", ".json", ".parquet", ".xlsx", ".pdf", ".png"]:
            assert expected in ext_list, f"{expected} should be in defaults"


# ============================================================
# PUT /admin/settings — Add new extension
# ============================================================

@pytest.mark.asyncio
async def test_add_extension_with_color(client_as):
    """MASTER_ADMIN can add a new extension with a chosen color."""
    async with client_as(MASTER_ADMIN) as c:
        # Get current settings
        resp = await c.get(f"{ADMIN_API}/settings")
        current = resp.json()["allowed_extensions"]

        # Add .avro with a teal color
        new_exts = current + [{"ext": ".avro", "color": "#14b8a6"}]
        resp = await c.put(f"{ADMIN_API}/settings", json={
            "allowed_extensions": new_exts,
        })
        assert resp.status_code == 200
        data = resp.json()
        ext_list = [e["ext"] for e in data["allowed_extensions"]]
        assert ".avro" in ext_list

        avro_entry = next(e for e in data["allowed_extensions"] if e["ext"] == ".avro")
        assert avro_entry["color"] == "#14b8a6"


@pytest.mark.asyncio
async def test_remove_extension(client_as):
    """MASTER_ADMIN can remove an extension."""
    async with client_as(MASTER_ADMIN) as c:
        resp = await c.get(f"{ADMIN_API}/settings")
        current = resp.json()["allowed_extensions"]

        # Remove .png
        without_png = [e for e in current if e["ext"] != ".png"]
        resp = await c.put(f"{ADMIN_API}/settings", json={
            "allowed_extensions": without_png,
        })
        assert resp.status_code == 200
        ext_list = [e["ext"] for e in resp.json()["allowed_extensions"]]
        assert ".png" not in ext_list


# ============================================================
# PUT /admin/settings — Color validation
# ============================================================

@pytest.mark.asyncio
async def test_invalid_hex_color_normalized(client_as):
    """Invalid hex colors should be normalized to default gray."""
    async with client_as(MASTER_ADMIN) as c:
        resp = await c.put(f"{ADMIN_API}/settings", json={
            "allowed_extensions": [
                {"ext": ".csv", "color": "#zzzzzz"},
                {"ext": ".json", "color": "not-a-color"},
                {"ext": ".txt", "color": "#abc"},  # valid shorthand
            ],
        })
        assert resp.status_code == 200
        data = resp.json()
        colors = {e["ext"]: e["color"] for e in data["allowed_extensions"]}
        assert colors[".csv"] == "#6b7280"  # normalized
        assert colors[".json"] == "#6b7280"  # normalized
        assert colors[".txt"] == "#abc"  # valid, preserved


# ============================================================
# PUT /admin/settings — Max upload size
# ============================================================

@pytest.mark.asyncio
async def test_update_max_upload_bytes(client_as):
    """MASTER_ADMIN can update max upload size."""
    async with client_as(MASTER_ADMIN) as c:
        new_size = 10 * 1024 * 1024 * 1024  # 10 GB
        resp = await c.put(f"{ADMIN_API}/settings", json={
            "max_upload_bytes": new_size,
        })
        assert resp.status_code == 200
        assert resp.json()["max_upload_bytes"] == new_size


@pytest.mark.asyncio
async def test_max_upload_bytes_minimum_enforced(client_as):
    """Max upload size below 1 MB should be rejected."""
    async with client_as(MASTER_ADMIN) as c:
        resp = await c.put(f"{ADMIN_API}/settings", json={
            "max_upload_bytes": 500 * 1024,  # 500 KB — below minimum
        })
        assert resp.status_code == 422
        assert "at least 1 MB" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_max_upload_bytes_maximum_enforced(client_as):
    """Max upload size above 50 GB should be rejected."""
    async with client_as(MASTER_ADMIN) as c:
        resp = await c.put(f"{ADMIN_API}/settings", json={
            "max_upload_bytes": 100 * 1024 * 1024 * 1024,  # 100 GB
        })
        assert resp.status_code == 422
        assert "cannot exceed 50 GB" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_empty_extensions_rejected(client_as):
    """Cannot save an empty extensions list."""
    async with client_as(MASTER_ADMIN) as c:
        resp = await c.put(f"{ADMIN_API}/settings", json={
            "allowed_extensions": [],
        })
        assert resp.status_code == 422
        assert "At least one extension" in resp.json()["detail"]


# ============================================================
# Max file size enforcement on initiate
# ============================================================

@pytest.mark.asyncio
async def test_file_size_enforced_on_initiate(client_as, mock_s3, seed_org):
    """Initiate should reject files exceeding max_upload_bytes."""
    async with client_as(MASTER_ADMIN) as c:
        # Set max to 1 MB
        resp = await c.put(f"{ADMIN_API}/settings", json={
            "max_upload_bytes": 1 * 1024 * 1024,
        })
        assert resp.status_code == 200

        # Try to initiate upload with file_size larger than limit
        resp = await c.post(f"{SERVICES_API}/initiate", json={
            "userid": 0,
            "name": "Data/big_file.csv",
            "author": "TestUser",
            "basePath": "/test-bucket",
            "file_size": 5 * 1024 * 1024,  # 5 MB > 1 MB limit
        })
        assert resp.status_code == 413, f"Expected 413 but got {resp.status_code}"


@pytest.mark.asyncio
async def test_file_size_within_limit_accepted(client_as, mock_s3, seed_org):
    """Initiate should accept files within max_upload_bytes."""
    async with client_as(MASTER_ADMIN) as c:
        # Set max to 10 MB
        resp = await c.put(f"{ADMIN_API}/settings", json={
            "max_upload_bytes": 10 * 1024 * 1024,
        })
        assert resp.status_code == 200

        # Initiate with file_size under limit
        resp = await c.post(f"{SERVICES_API}/initiate", json={
            "userid": 0,
            "name": "Data/small_file.csv",
            "author": "TestUser",
            "basePath": "/test-bucket",
            "file_size": 5 * 1024 * 1024,  # 5 MB < 10 MB limit
        })
        assert resp.status_code != 413


# ============================================================
# Dynamic allowlist enforcement on upload
# ============================================================

@pytest.mark.asyncio
async def test_new_format_allowed_after_admin_adds_it(client_as, mock_s3, seed_org):
    """After MASTER_ADMIN adds .avro, upload of .avro should not get 415."""
    async with client_as(MASTER_ADMIN) as c:
        # .avro is NOT in defaults — should be rejected initially
        resp = await c.post(f"{SERVICES_API}/initiate", json={
            "userid": 0,
            "name": "Data/file.avro",
            "author": "TestUser",
            "basePath": "/test-bucket",
        })
        assert resp.status_code == 415

        # Now add .avro via settings
        get_resp = await c.get(f"{ADMIN_API}/settings")
        current = get_resp.json()["allowed_extensions"]
        current.append({"ext": ".avro", "color": "#14b8a6"})
        await c.put(f"{ADMIN_API}/settings", json={"allowed_extensions": current})

        # Now .avro should be allowed
        resp = await c.post(f"{SERVICES_API}/initiate", json={
            "userid": 0,
            "name": "Data/file.avro",
            "author": "TestUser",
            "basePath": "/test-bucket",
        })
        assert resp.status_code != 415, ".avro should be allowed after admin adds it"


@pytest.mark.asyncio
async def test_removed_format_rejected_after_admin_removes_it(client_as, mock_s3, seed_org):
    """After MASTER_ADMIN removes .csv, upload of .csv should get 415."""
    async with client_as(MASTER_ADMIN) as c:
        # .csv should work initially
        resp = await c.post(f"{SERVICES_API}/initiate", json={
            "userid": 0,
            "name": "Data/file.csv",
            "author": "TestUser",
            "basePath": "/test-bucket",
        })
        assert resp.status_code != 415

        # Remove .csv from settings
        get_resp = await c.get(f"{ADMIN_API}/settings")
        without_csv = [e for e in get_resp.json()["allowed_extensions"] if e["ext"] != ".csv"]
        await c.put(f"{ADMIN_API}/settings", json={"allowed_extensions": without_csv})

        # Now .csv should be rejected
        resp = await c.post(f"{SERVICES_API}/initiate", json={
            "userid": 0,
            "name": "Data/file.csv",
            "author": "TestUser",
            "basePath": "/test-bucket",
        })
        assert resp.status_code == 415, ".csv should be rejected after admin removes it"


# ============================================================
# GET /services/upload-constraints — Returns colors
# ============================================================

@pytest.mark.asyncio
async def test_upload_constraints_returns_extension_colors(client_as):
    """GET /services/upload-constraints should include extension_colors."""
    async with client_as(USER_RW) as c:
        resp = await c.get(f"{SERVICES_API}/upload-constraints")
        assert resp.status_code == 200
        data = resp.json()
        assert "extension_colors" in data
        assert "allowed_extensions" in data
        assert "max_upload_bytes" in data

        for entry in data["extension_colors"]:
            assert "ext" in entry
            assert "color" in entry
            assert entry["color"].startswith("#")


@pytest.mark.asyncio
async def test_upload_constraints_reflects_admin_changes(client_as):
    """upload-constraints should reflect changes made by MASTER_ADMIN."""
    # First set a custom config as admin
    async with client_as(MASTER_ADMIN) as c:
        await c.put(f"{ADMIN_API}/settings", json={
            "allowed_extensions": [
                {"ext": ".csv", "color": "#ff0000"},
                {"ext": ".json", "color": "#00ff00"},
            ],
        })

    # Now check as a normal user
    async with client_as(USER_RW) as c:
        resp = await c.get(f"{SERVICES_API}/upload-constraints")
        assert resp.status_code == 200
        data = resp.json()

        colors = {e["ext"]: e["color"] for e in data["extension_colors"]}
        assert colors[".csv"] == "#ff0000"
        assert colors[".json"] == "#00ff00"
        assert len(data["extension_colors"]) == 2


# ============================================================
# Access control — Non-MASTER cannot modify settings
# ============================================================

@pytest.mark.asyncio
async def test_org_admin_cannot_get_settings(client_as):
    """ORG_ADMIN should be rejected from /admin/settings."""
    async with client_as(ORG_ADMIN) as c:
        resp = await c.get(f"{ADMIN_API}/settings")
        assert resp.status_code == 403


@pytest.mark.asyncio
async def test_org_admin_cannot_put_settings(client_as):
    """ORG_ADMIN should not be able to update platform settings."""
    async with client_as(ORG_ADMIN) as c:
        resp = await c.put(f"{ADMIN_API}/settings", json={
            "allowed_extensions": [{"ext": ".csv", "color": "#000000"}],
        })
        assert resp.status_code == 403


@pytest.mark.asyncio
async def test_normal_user_cannot_access_settings(client_as):
    """Normal USER should be rejected from /admin/settings."""
    async with client_as(USER_RW) as c:
        resp = await c.get(f"{ADMIN_API}/settings")
        assert resp.status_code == 403

        resp = await c.put(f"{ADMIN_API}/settings", json={
            "max_upload_bytes": 1024 * 1024,
        })
        assert resp.status_code == 403
