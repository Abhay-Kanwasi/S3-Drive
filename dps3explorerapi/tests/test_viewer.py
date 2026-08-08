"""
Tests for the file viewer/preview endpoint.

Covers:
- Auth enforcement (unauthenticated users cannot preview)
- Grant enforcement (non-admin users can only preview within granted prefixes)
- Extension validation (only .csv, .xlsx, .parquet, .json are previewable)
- CSV preview returns correct table format
- JSON preview returns correct json format
- Admin can preview any file without grants
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import io
import json
import pytest
import pytest_asyncio

from tests.conftest import (
    SUPER_ADMIN,
    MASTER_ADMIN,
    USER_RW,
    USER_OTHER_ORG,
    TestSession,
)
from db.models import Org, UserGroup, GroupMembership, FolderGrant


API = "/api/v2/explorer/viewer"


@pytest.fixture
def seed_org_for_viewer(db):
    """Seed an org for viewer tests."""
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
def seed_user_grant(db, seed_org_for_viewer):
    """Give USER_RW a read grant on 'Data/' prefix."""
    group = UserGroup(name="dp-ViewerGroup", org_id=seed_org_for_viewer.id, created_by=1)
    db.add(group)
    db.commit()
    db.refresh(group)

    membership = GroupMembership(group_id=group.id, user_id=USER_RW.id, added_by=1)
    db.add(membership)

    grant = FolderGrant(
        group_id=group.id,
        org_id=seed_org_for_viewer.id,
        prefix="Data/",
        access_level="read",
        created_by=1,
    )
    db.add(grant)
    db.commit()
    return grant


# ============================================================
# Extension validation
# ============================================================

@pytest.mark.asyncio
@pytest.mark.parametrize("filename", [
    "report.txt", "image.png", "script.py", "archive.zip", "video.mp4",
])
async def test_preview_rejects_non_viewable_extensions(client_as, mock_s3, seed_org_for_viewer, filename):
    """Non-viewable extensions should get 415."""
    mock_s3.put_object(Bucket="test-bucket", Key=f"Data/{filename}", Body=b"content")
    async with client_as(MASTER_ADMIN) as c:
        resp = await c.get(f"{API}/preview", params={
            "file_key": f"Data/{filename}",
            "basePath": "test-bucket",
        })
        assert resp.status_code == 415, f"{filename} should be rejected but got {resp.status_code}"


@pytest.mark.asyncio
@pytest.mark.parametrize("filename,ext", [
    ("data.csv", ".csv"),
    ("data.xlsx", ".xlsx"),
    ("data.parquet", ".parquet"),
    ("data.json", ".json"),
])
async def test_preview_accepts_viewable_extensions(client_as, mock_s3, seed_org_for_viewer, filename, ext):
    """Viewable extensions should not get 415 (may get other errors if content is invalid)."""
    if ext == ".json":
        content = json.dumps({"key": "value"}).encode()
    elif ext == ".csv":
        content = b"col1,col2\n1,2\n3,4\n"
    else:
        content = b"dummy"

    mock_s3.put_object(Bucket="test-bucket", Key=f"Data/{filename}", Body=content)
    async with client_as(MASTER_ADMIN) as c:
        resp = await c.get(f"{API}/preview", params={
            "file_key": f"Data/{filename}",
            "basePath": "test-bucket",
        })
        assert resp.status_code != 415, f"{filename} should be accepted but got 415"


# ============================================================
# CSV preview
# ============================================================

@pytest.mark.asyncio
async def test_csv_preview_returns_table_format(client_as, mock_s3, seed_org_for_viewer):
    """CSV file should return format='table' with columns and rows."""
    csv_content = b"name,age,city\nAlice,30,NYC\nBob,25,LA\n"
    mock_s3.put_object(Bucket="test-bucket", Key="Data/people.csv", Body=csv_content)

    async with client_as(MASTER_ADMIN) as c:
        resp = await c.get(f"{API}/preview", params={
            "file_key": "Data/people.csv",
            "basePath": "test-bucket",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["format"] == "table"
        assert data["columns"] == ["name", "age", "city"]
        assert data["total_rows"] == 2
        assert len(data["rows"]) == 2
        assert data["rows"][0]["name"] == "Alice"
        assert data["filename"] == "people.csv"


# ============================================================
# JSON preview
# ============================================================

@pytest.mark.asyncio
async def test_json_preview_returns_json_format(client_as, mock_s3, seed_org_for_viewer):
    """JSON file should return format='json' with parsed data."""
    json_content = json.dumps({"users": [{"id": 1}]}).encode()
    mock_s3.put_object(Bucket="test-bucket", Key="Data/config.json", Body=json_content)

    async with client_as(MASTER_ADMIN) as c:
        resp = await c.get(f"{API}/preview", params={
            "file_key": "Data/config.json",
            "basePath": "test-bucket",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["format"] == "json"
        assert data["data"] == {"users": [{"id": 1}]}
        assert data["filename"] == "config.json"


# ============================================================
# Grant enforcement
# ============================================================

@pytest.mark.asyncio
async def test_user_can_preview_within_granted_prefix(client_as, mock_s3, seed_org_for_viewer, seed_user_grant):
    """USER_RW with read grant on 'Data/' should be able to preview files there."""
    csv_content = b"x,y\n1,2\n"
    mock_s3.put_object(Bucket="test-bucket", Key="Data/report.csv", Body=csv_content)

    async with client_as(USER_RW) as c:
        resp = await c.get(f"{API}/preview", params={
            "file_key": "Data/report.csv",
            "basePath": "test-bucket",
        })
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_user_blocked_outside_granted_prefix(client_as, mock_s3, seed_org_for_viewer, seed_user_grant):
    """USER_RW should NOT be able to preview files outside their granted prefix."""
    csv_content = b"x,y\n1,2\n"
    mock_s3.put_object(Bucket="test-bucket", Key="Secret/internal.csv", Body=csv_content)

    async with client_as(USER_RW) as c:
        resp = await c.get(f"{API}/preview", params={
            "file_key": "Secret/internal.csv",
            "basePath": "test-bucket",
        })
        assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_can_preview_any_file(client_as, mock_s3, seed_org_for_viewer):
    """Admin should be able to preview any file regardless of grants."""
    csv_content = b"a,b\n1,2\n"
    mock_s3.put_object(Bucket="test-bucket", Key="Secret/admin-only.csv", Body=csv_content)

    async with client_as(MASTER_ADMIN) as c:
        resp = await c.get(f"{API}/preview", params={
            "file_key": "Secret/admin-only.csv",
            "basePath": "test-bucket",
        })
        assert resp.status_code == 200


# ============================================================
# max_rows enforcement
# ============================================================

@pytest.mark.asyncio
async def test_page_size_limits_output(client_as, mock_s3, seed_org_for_viewer):
    """page_size parameter should limit the returned rows per page."""
    lines = "id\n" + "\n".join(str(i) for i in range(100))
    mock_s3.put_object(Bucket="test-bucket", Key="Data/big.csv", Body=lines.encode())

    async with client_as(MASTER_ADMIN) as c:
        resp = await c.get(f"{API}/preview", params={
            "file_key": "Data/big.csv",
            "basePath": "test-bucket",
            "page": 1,
            "page_size": 10,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_rows"] == 100
        assert len(data["rows"]) == 10
        assert data["page"] == 1
        assert data["page_size"] == 10
        assert data["total_pages"] == 10


@pytest.mark.asyncio
async def test_pagination_page_2(client_as, mock_s3, seed_org_for_viewer):
    """Page 2 should return the next slice of rows."""
    lines = "id\n" + "\n".join(str(i) for i in range(50))
    mock_s3.put_object(Bucket="test-bucket", Key="Data/paged.csv", Body=lines.encode())

    async with client_as(MASTER_ADMIN) as c:
        resp = await c.get(f"{API}/preview", params={
            "file_key": "Data/paged.csv",
            "basePath": "test-bucket",
            "page": 2,
            "page_size": 20,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_rows"] == 50
        assert len(data["rows"]) == 20
        assert data["page"] == 2
        assert data["rows"][0]["id"] == 20


# ============================================================
# File not found
# ============================================================

@pytest.mark.asyncio
async def test_preview_returns_404_for_missing_file(client_as, mock_s3, seed_org_for_viewer):
    """Requesting a non-existent file should return an error."""
    async with client_as(MASTER_ADMIN) as c:
        resp = await c.get(f"{API}/preview", params={
            "file_key": "Data/nonexistent.csv",
            "basePath": "test-bucket",
        })
        assert resp.status_code in (404, 500)


# ============================================================
# XLSX multi-sheet support
# ============================================================

def _make_xlsx_bytes(sheets_data: dict) -> bytes:
    """Helper: create an xlsx file with multiple sheets. sheets_data = {"SheetName": [rows]}."""
    import openpyxl
    wb = openpyxl.Workbook()
    first = True
    for name, rows in sheets_data.items():
        if first:
            ws = wb.active
            ws.title = name
            first = False
        else:
            ws = wb.create_sheet(title=name)
        for row in rows:
            ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest.mark.asyncio
async def test_xlsx_returns_sheet_names(client_as, mock_s3, seed_org_for_viewer):
    """XLSX preview should return sheets list and active_sheet."""
    xlsx_bytes = _make_xlsx_bytes({
        "Sales": [["Month", "Revenue"], ["Jan", 100], ["Feb", 200]],
        "Costs": [["Month", "Expense"], ["Jan", 50], ["Feb", 60]],
        "Summary": [["Total", 300]],
    })
    mock_s3.put_object(Bucket="test-bucket", Key="Data/multi.xlsx", Body=xlsx_bytes)

    async with client_as(MASTER_ADMIN) as c:
        resp = await c.get(f"{API}/preview", params={
            "file_key": "Data/multi.xlsx",
            "basePath": "test-bucket",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["format"] == "table"
        assert data["sheets"] == ["Sales", "Costs", "Summary"]
        assert data["active_sheet"] == "Sales"
        assert "Month" in data["columns"]


@pytest.mark.asyncio
async def test_xlsx_switch_sheet(client_as, mock_s3, seed_org_for_viewer):
    """Passing sheet param should return data from that sheet."""
    xlsx_bytes = _make_xlsx_bytes({
        "Sales": [["Month", "Revenue"], ["Jan", 100]],
        "Costs": [["Month", "Expense"], ["Jan", 50], ["Feb", 60]],
    })
    mock_s3.put_object(Bucket="test-bucket", Key="Data/sheets.xlsx", Body=xlsx_bytes)

    async with client_as(MASTER_ADMIN) as c:
        resp = await c.get(f"{API}/preview", params={
            "file_key": "Data/sheets.xlsx",
            "basePath": "test-bucket",
            "sheet": "Costs",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["active_sheet"] == "Costs"
        assert "Expense" in data["columns"]
        assert data["total_rows"] == 2


@pytest.mark.asyncio
async def test_xlsx_single_sheet_no_tabs(client_as, mock_s3, seed_org_for_viewer):
    """XLSX with single sheet should still return sheets array (length 1)."""
    xlsx_bytes = _make_xlsx_bytes({
        "Sheet1": [["A", "B"], [1, 2], [3, 4]],
    })
    mock_s3.put_object(Bucket="test-bucket", Key="Data/single.xlsx", Body=xlsx_bytes)

    async with client_as(MASTER_ADMIN) as c:
        resp = await c.get(f"{API}/preview", params={
            "file_key": "Data/single.xlsx",
            "basePath": "test-bucket",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["sheets"] == ["Sheet1"]
        assert data["active_sheet"] == "Sheet1"


@pytest.mark.asyncio
async def test_xlsx_pagination_per_sheet(client_as, mock_s3, seed_org_for_viewer):
    """Pagination should work correctly within a specific sheet."""
    rows = [["id", "value"]] + [[i, i * 10] for i in range(30)]
    xlsx_bytes = _make_xlsx_bytes({"BigSheet": rows, "Small": [["x"], [1]]})
    mock_s3.put_object(Bucket="test-bucket", Key="Data/paged.xlsx", Body=xlsx_bytes)

    async with client_as(MASTER_ADMIN) as c:
        resp = await c.get(f"{API}/preview", params={
            "file_key": "Data/paged.xlsx",
            "basePath": "test-bucket",
            "sheet": "BigSheet",
            "page": 2,
            "page_size": 10,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["active_sheet"] == "BigSheet"
        assert len(data["rows"]) == 10
        assert data["page"] == 2
        assert data["total_rows"] == 30
