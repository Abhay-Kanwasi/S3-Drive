"""
Centralized audit logging — S3-only.

All audit events are appended into one daily log object per org:
Path: audit/{YYYY}/{Month}/{DD}/{org_name}/audit.log
Example: audit/2026/May/18/Infosys/audit.log
Bucket: settings.AUDIT_BUCKET (defaults to TRASH_BUCKET, override via AUDIT_BUCKET env var)

Lifecycle (DevOps-managed, prefix-scoped to audit/):
  Day 0-30:   Standard (hot, readable)
  Day 31-365: Glacier (cold, not readable by app)
  Day 365+:   Expired/deleted
"""

import json
import logging
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Lock
from typing import Optional

from botocore.exceptions import ClientError

from fastapi import Request

from core.config import settings
from core.s3 import get_s3_client

logger = logging.getLogger(__name__)

_s3 = get_s3_client()
_executor = ThreadPoolExecutor(max_workers=5, thread_name_prefix="audit")
_write_lock = Lock()

AUDIT_BUCKET = settings.AUDIT_BUCKET
MAX_AUDIT_LOG_BYTES = 5 * 1024 * 1024


def _normalize_org_folder(org_name: Optional[str], org_id: Optional[int]) -> str:
    raw = (org_name or "").strip()
    if not raw:
        raw = "global"
    # Prevent accidental nested prefixes from org names.
    return raw.replace("/", "-").replace("\\", "-")


def _build_key(org_name: Optional[str], org_id: Optional[int], ts: datetime) -> str:
    org_part = _normalize_org_folder(org_name, org_id)
    month = ts.strftime("%B")
    day = str(ts.day)
    return f"audit/{ts.year}/{month}/{day}/{org_part}/audit.log"


def _append_event_line(key: str, line: str, event_id: str) -> None:
    try:
        with _write_lock:
            existing = ""
            existing_bytes = b""
            try:
                resp = _s3.get_object(Bucket=AUDIT_BUCKET, Key=key)
                body = resp["Body"].read()
                if isinstance(body, bytes):
                    existing_bytes = body
                    existing = body.decode("utf-8")
                elif isinstance(body, str):
                    existing = body
                    existing_bytes = body.encode("utf-8")
            except ClientError as e:
                if e.response["Error"]["Code"] != "NoSuchKey":
                    logger.warning("get_object failed for %s: %s", key, e)
                existing = ""
                existing_bytes = b""

            line_with_newline = f"{line}\n"
            line_bytes = line_with_newline.encode("utf-8")

            # Rotate when the current log would exceed 5 MB after append.
            if existing_bytes and (len(existing_bytes) + len(line_bytes) > MAX_AUDIT_LOG_BYTES):
                rotated_key = f"{key}.1"
                _s3.put_object(
                    Bucket=AUDIT_BUCKET,
                    Key=rotated_key,
                    Body=existing_bytes,
                    ContentType="text/plain",
                )
                existing = ""

            if existing and not existing.endswith("\n"):
                existing += "\n"
            merged = f"{existing}{line_with_newline}"

            _s3.put_object(
                Bucket=AUDIT_BUCKET,
                Key=key,
                Body=merged.encode("utf-8"),
                ContentType="text/plain",
            )
    except Exception:
        # Fallback: write as individual sidecar file so the event is never lost.
        logger.warning("Append failed for %s, writing sidecar for event %s", key, event_id)
        try:
            sidecar_key = f"{key}.orphan.{event_id}"
            _s3.put_object(
                Bucket=AUDIT_BUCKET,
                Key=sidecar_key,
                Body=f"{line}\n".encode("utf-8"),
                ContentType="text/plain",
            )
        except Exception:
            logger.exception("Failed to write sidecar audit event: %s", event_id)


def audit_actor_fields(user) -> dict:
    """Actor identity to pass into audit_log (name stored at write time)."""
    return {
        "user_id": user.id,
        "user_name": user.user_name or "",
        "user_email": user.email or "",
    }


def file_transfer_details(
    action: str,
    user_name: str,
    source_path: str,
    destination_path: str,
    **extra,
) -> dict:
    """Human-readable from/to paths for copy, move, rename audit rows."""
    actor = user_name or "User"
    return {
        "summary": f"{actor} {action} '{source_path}' → '{destination_path}'",
        "source_path": source_path,
        "destination_path": destination_path,
        **extra,
    }


def audit_log(
    *,
    user_id: int,
    event_type: str,
    target_key: str,
    org_id: Optional[int] = None,
    org_name: Optional[str] = None,
    user_name: Optional[str] = None,
    user_email: Optional[str] = None,
    details: Optional[dict] = None,
    request: Optional[Request] = None,
) -> None:
    """Write an audit event to S3. Fire-and-forget via background thread.

    Never raises. Called after business logic completes.
    Store user_name at write time; use details.summary for human-readable target text.
    """
    try:
        event_id = uuid.uuid4().hex[:12]
        ts = datetime.now(timezone.utc)

        ip = None
        if request and request.client:
            ip = request.client.host

        display_target = target_key
        if details and details.get("summary"):
            display_target = details["summary"]

        event = {
            "event_id": event_id,
            "timestamp": ts.isoformat(),
            "org_id": org_id,
            "org_name": org_name,
            "user_id": user_id,
            "user_name": user_name,
            "user_email": user_email,
            "event_type": event_type,
            "target_key": target_key,
            "display_target": display_target,
            "details": details,
            "ip_address": ip,
        }

        key = _build_key(org_name, org_id, ts)
        line = json.dumps(event, default=str)

        _executor.submit(_append_event_line, key, line, event_id)
    except Exception:
        logger.exception("audit_log() failed to enqueue event: %s", event_type)
