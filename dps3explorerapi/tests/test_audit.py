"""
Tests for S3-backed audit logging.

Covers:
- Write path: audit_log() puts JSON objects to S3
- Read path: GET /admin/audit lists and filters events from S3
- Retention warning when date range exceeds hot window
"""

import json
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch, MagicMock

import pytest
import pytest_asyncio

from tests.conftest import SUPER_ADMIN, ORG_ADMIN


class TestAuditWrite:
    """Tests for core/audit.py — writing events to S3."""

    @patch("core.audit._s3")
    def test_audit_log_puts_object_to_s3(self, mock_s3):
        """audit_log() should put a JSON object to the correct S3 path."""
        from core.audit import audit_log, AUDIT_BUCKET

        audit_log(
            user_id=1,
            event_type="FOLDER_CREATED",
            target_key="Reports/Q1/",
            org_id=42,
            org_name="Infosys",
            details={"name": "Q1"},
        )

        # Wait for background thread
        from core.audit import _executor
        _executor.shutdown(wait=True)
        from concurrent.futures import ThreadPoolExecutor
        import core.audit
        core.audit._executor = ThreadPoolExecutor(max_workers=5, thread_name_prefix="audit")

        mock_s3.put_object.assert_called_once()
        call_kwargs = mock_s3.put_object.call_args[1]
        assert call_kwargs["Bucket"] == AUDIT_BUCKET
        assert call_kwargs["Key"].startswith("audit/")
        assert "/Infosys/" in call_kwargs["Key"]
        assert call_kwargs["Key"].endswith("/audit.log")
        assert call_kwargs["ContentType"] == "text/plain"

        body = json.loads(call_kwargs["Body"])
        assert body["event_type"] == "FOLDER_CREATED"
        assert body["user_id"] == 1
        assert body["org_id"] == 42
        assert body["org_name"] == "Infosys"
        assert body["target_key"] == "Reports/Q1/"
        assert body["details"] == {"name": "Q1"}
        assert body["event_id"]
        assert body["timestamp"]

    @patch("core.audit._s3")
    def test_audit_log_extracts_ip(self, mock_s3):
        """audit_log() should extract IP from request."""
        from core.audit import audit_log, _executor

        mock_request = MagicMock()
        mock_request.client.host = "192.168.1.100"

        audit_log(
            user_id=1,
            event_type="FILE_TRASHED",
            target_key="file.txt",
            request=mock_request,
        )

        _executor.shutdown(wait=True)
        from concurrent.futures import ThreadPoolExecutor
        import core.audit
        core.audit._executor = ThreadPoolExecutor(max_workers=5, thread_name_prefix="audit")

        body = json.loads(mock_s3.put_object.call_args[1]["Body"])
        assert body["ip_address"] == "192.168.1.100"

    @patch("core.audit._s3")
    def test_audit_log_no_org(self, mock_s3):
        """audit_log() without org info uses 'global' folder in path."""
        from core.audit import audit_log, _executor

        audit_log(
            user_id=5,
            event_type="ORG_ONBOARDED",
            target_key="new-bucket",
        )

        _executor.shutdown(wait=True)
        from concurrent.futures import ThreadPoolExecutor
        import core.audit
        core.audit._executor = ThreadPoolExecutor(max_workers=5, thread_name_prefix="audit")

        key = mock_s3.put_object.call_args[1]["Key"]
        assert "/global/" in key

    @patch("core.audit._s3")
    def test_audit_log_silently_handles_s3_error(self, mock_s3):
        """audit_log() should not raise even if S3 put fails."""
        from core.audit import audit_log, _executor

        mock_s3.put_object.side_effect = Exception("S3 unavailable")

        audit_log(
            user_id=1,
            event_type="FOLDER_CREATED",
            target_key="test/",
        )

        _executor.shutdown(wait=True)
        from concurrent.futures import ThreadPoolExecutor
        import core.audit
        core.audit._executor = ThreadPoolExecutor(max_workers=5, thread_name_prefix="audit")

    @patch("core.audit._s3")
    def test_audit_log_rotates_when_size_exceeds_limit(self, mock_s3):
        """audit.log should rotate to audit.log.1 when size exceeds configured limit."""
        from core.audit import audit_log, _executor
        from concurrent.futures import ThreadPoolExecutor
        import core.audit

        existing_text = '{"event_id":"old"}\n'
        mock_s3.get_object.return_value = {
            "Body": MagicMock(read=lambda: existing_text.encode("utf-8"))
        }

        with patch("core.audit.MAX_AUDIT_LOG_BYTES", 1):
            audit_log(
                user_id=7,
                event_type="GROUP_CREATED",
                target_key="root/",
                org_id=42,
                org_name="Infosys",
            )
            _executor.shutdown(wait=True)

        core.audit._executor = ThreadPoolExecutor(max_workers=5, thread_name_prefix="audit")

        assert mock_s3.put_object.call_count == 2
        rotated = mock_s3.put_object.call_args_list[0].kwargs
        current = mock_s3.put_object.call_args_list[1].kwargs

        assert rotated["Key"].endswith("/Infosys/audit.log.1")
        assert rotated["Body"] == existing_text.encode("utf-8")
        assert current["Key"].endswith("/Infosys/audit.log")


class TestAuditRead:
    """Tests for api/endpoints/audit.py — reading events from S3."""

    @patch("api.endpoints.audit._s3")
    @pytest.mark.asyncio
    async def test_list_empty(self, mock_s3, client_as):
        """GET /admin/audit returns empty events when no S3 objects exist."""
        mock_s3.list_objects_v2.return_value = {"Contents": [], "IsTruncated": False}

        async with client_as(SUPER_ADMIN) as c:
            resp = await c.get(
                "/api/v2/explorer/admin/audit",
                params={"date_from": date.today().isoformat(), "date_to": date.today().isoformat()},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["events"] == []
        assert data["total"] == 0
        assert data["retention"]["hot_days"] == 30
        assert data["warning"] is None

    @patch("api.endpoints.audit._s3")
    @pytest.mark.asyncio
    async def test_list_with_events(self, mock_s3, client_as, db, seed_org):
        """GET /admin/audit returns parsed events from S3."""
        today_d = date.today()
        today = today_d.isoformat()
        test_event = {
            "event_id": "abc123",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "org_id": seed_org.id,
            "org_name": seed_org.org_name,
            "user_id": 1,
            "event_type": "FOLDER_CREATED",
            "target_key": "Reports/",
            "details": {"name": "Reports"},
            "ip_address": "10.0.0.1",
        }

        mock_s3.list_objects_v2.return_value = {
            "Contents": [{"Key": f"audit/{today_d.year}/{today_d.strftime('%B')}/{today_d.day}/{seed_org.org_name}/audit.log"}],
            "IsTruncated": False,
        }
        mock_s3.get_object.return_value = {
            "Body": MagicMock(read=lambda: (json.dumps(test_event) + "\n").encode())
        }

        async with client_as(SUPER_ADMIN) as c:
            resp = await c.get(
                "/api/v2/explorer/admin/audit",
                params={"date_from": today, "date_to": today},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["events"][0]["event_type"] == "FOLDER_CREATED"
        assert data["events"][0]["event_label"] == "Folder Created"
        assert data["events"][0]["target_key"] == "Reports/"

    @patch("api.endpoints.audit._s3")
    @pytest.mark.asyncio
    async def test_retention_warning(self, mock_s3, client_as):
        """GET /admin/audit with date > 30 days ago returns warning."""
        mock_s3.list_objects_v2.return_value = {"Contents": [], "IsTruncated": False}

        old_date = (date.today() - timedelta(days=60)).isoformat()
        async with client_as(SUPER_ADMIN) as c:
            resp = await c.get(
                "/api/v2/explorer/admin/audit",
                params={"date_from": old_date, "date_to": date.today().isoformat()},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["warning"] is not None
        assert data["warning"]["code"] == "RETENTION_WINDOW_EXCEEDED"

    @patch("api.endpoints.audit._s3")
    @pytest.mark.asyncio
    async def test_event_type_filter(self, mock_s3, client_as, db, seed_org):
        """GET /admin/audit filters by event_type in-memory."""
        today_d = date.today()
        today = today_d.isoformat()
        events_data = [
            {"event_id": "a1", "timestamp": "2026-05-18T10:00:00Z", "org_id": seed_org.id,
             "org_name": seed_org.org_name, "user_id": 1, "event_type": "FOLDER_CREATED", "target_key": "A/", "details": None, "ip_address": None},
            {"event_id": "a2", "timestamp": "2026-05-18T11:00:00Z", "org_id": seed_org.id,
             "org_name": seed_org.org_name, "user_id": 1, "event_type": "FILE_TRASHED", "target_key": "B.txt", "details": None, "ip_address": None},
        ]

        mock_s3.list_objects_v2.return_value = {
            "Contents": [
                {"Key": f"audit/{today_d.year}/{today_d.strftime('%B')}/{today_d.day}/{seed_org.org_name}/audit.log"},
            ],
            "IsTruncated": False,
        }

        body = "\n".join(json.dumps(e) for e in events_data) + "\n"
        mock_s3.get_object.return_value = {"Body": MagicMock(read=lambda: body.encode())}

        async with client_as(SUPER_ADMIN) as c:
            resp = await c.get(
                "/api/v2/explorer/admin/audit",
                params={"date_from": today, "date_to": today, "event_type": "FOLDER_CREATED"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["events"][0]["event_type"] == "FOLDER_CREATED"

    @patch("api.endpoints.audit._s3")
    @pytest.mark.asyncio
    async def test_list_reads_rotated_audit_logs(self, mock_s3, client_as, db, seed_org):
        """GET /admin/audit should include events from audit.log and audit.log.1."""
        today_d = date.today()
        today = today_d.isoformat()

        event_from_current = {
            "event_id": "c1",
            "timestamp": "2026-05-18T12:00:00Z",
            "org_id": seed_org.id,
            "org_name": seed_org.org_name,
            "user_id": 1,
            "event_type": "FOLDER_CREATED",
            "target_key": "Current/",
            "details": None,
            "ip_address": None,
        }
        event_from_rotated = {
            "event_id": "r1",
            "timestamp": "2026-05-18T11:00:00Z",
            "org_id": seed_org.id,
            "org_name": seed_org.org_name,
            "user_id": 1,
            "event_type": "GROUP_CREATED",
            "target_key": "Rotated/",
            "details": None,
            "ip_address": None,
        }

        base = f"audit/{today_d.year}/{today_d.strftime('%B')}/{today_d.day}/{seed_org.org_name}"
        mock_s3.list_objects_v2.return_value = {
            "Contents": [
                {"Key": f"{base}/audit.log.1"},
                {"Key": f"{base}/audit.log"},
            ],
            "IsTruncated": False,
        }

        def mock_get(Bucket, Key):
            if Key.endswith("audit.log.1"):
                body = json.dumps(event_from_rotated) + "\n"
            else:
                body = json.dumps(event_from_current) + "\n"
            return {"Body": MagicMock(read=lambda: body.encode("utf-8"))}

        mock_s3.get_object.side_effect = mock_get

        async with client_as(SUPER_ADMIN) as c:
            resp = await c.get(
                "/api/v2/explorer/admin/audit",
                params={"date_from": today, "date_to": today},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        returned_types = {ev["event_type"] for ev in data["events"]}
        assert returned_types == {"FOLDER_CREATED", "GROUP_CREATED"}
