"""
Audit Log read API — S3-backed.

- GET  /admin/audit        — paginated audit event listing (reads from S3)
- GET  /admin/audit/export — CSV export

Storage: s3://{TRASH_BUCKET}/audit/{YYYY}/{Month}/{DD}/{org_name}/audit.log
Lifecycle (DevOps): 30d hot, 31-365d cold (Glacier), 365d+ expired.
App restricts queries to last 30 days (hot tier only).
"""

import csv
import io
import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
from typing import Optional

from botocore.exceptions import ClientError

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from core.auth import (
    CurrentUser,
    GLOBAL_ADMIN_ROLE_IDS,
    require_role,
)
from core.config import settings
from core.s3 import get_s3_client
from db.postgresdb import get_db

logger = logging.getLogger(__name__)

router = APIRouter()

AUDIT_ROLES = ["admin", "master_admin", "super_admin"]
AUDIT_BUCKET = settings.AUDIT_BUCKET
AUDIT_PREFIX = "audit/"
HOT_DAYS = settings.AUDIT_HOT_DAYS
TOTAL_RETENTION_DAYS = settings.AUDIT_TOTAL_DAYS

_s3 = get_s3_client()
_read_pool = ThreadPoolExecutor(max_workers=20, thread_name_prefix="audit-read")

EVENT_TYPE_LABELS = {
    "FOLDER_CREATED": "Folder Created",
    "FOLDER_RENAMED": "Folder Renamed",
    "FOLDER_TRASHED": "Folder Trashed",
    "TRASH_RESTORED": "Trash Restored",
    "TRASH_PURGED": "Trash Purged",
    "FILE_UPLOAD_INITIATED": "Upload Started",
    "FILE_UPLOADED": "File Uploaded",
    "FILE_TRASHED": "File Trashed",
    "FILE_RENAMED": "File Renamed",
    "FILE_COPIED": "File Copied",
    "FILE_MOVED": "File Moved",
    "FILE_VIEWED": "File Viewed",
    "ORG_ONBOARDED": "Organization Onboarded",
    "GROUP_CREATED": "Group Created",
    "GROUP_RENAMED": "Group Renamed",
    "GROUP_DELETED": "Group Deleted",
    "ORG_UNONBOARD_OTP_SENT": "Organization Un-onboard OTP Sent",
    "ORG_UNONBOARD_INITIATED": "Organization Un-onboard Initiated",
    "ORG_UNONBOARD_APPROVED": "Organization Un-onboard Approved",
    "MEMBER_ADDED": "Member Added",
    "MEMBER_REMOVED": "Member Removed",
    "GRANT_CREATED": "Grant Created",
    "GRANT_REMOVED": "Grant Removed",
    "ALLOWLIST_UPDATED": "Platform Settings Updated",
    "FOLDER_ACCESS_NOTIFIED": "Folder Access Notified",
    "USERS_EXPORTED": "Users Exported",
    "USER_DEACTIVATED": "User Deactivated",
    "USER_REACTIVATED": "User Reactivated",
}


def _date_range(start: date, end: date, newest_first: bool = False):
    """Yield each date from start to end inclusive.
    If newest_first=True, yields from end down to start (for truncation that keeps recent events).
    """
    if newest_first:
        d = end
        while d >= start:
            yield d
            d -= timedelta(days=1)
    else:
        d = start
        while d <= end:
            yield d
            d += timedelta(days=1)


def _normalize_org_folder(org_name: Optional[str], org_id: Optional[int] = None) -> str:
    raw = (org_name or "").strip()
    if not raw:
        raw = "global"
    return raw.replace("/", "-").replace("\\", "-")


def _list_keys_for_day(day: date, org_folder: Optional[str], newest_first: bool = False) -> list[str]:
    """List daily audit log objects for a given day, optionally scoped to one org folder.
    Expected object names are .../audit.log and rotated .../audit.log.1.
    """
    prefix = f"{AUDIT_PREFIX}{day.year}/{day.strftime('%B')}/{day.day}/"
    if org_folder:
        prefix += f"{org_folder}/"

    keys = []
    params = {"Bucket": AUDIT_BUCKET, "Prefix": prefix, "MaxKeys": 1000}
    while True:
        try:
            resp = _s3.list_objects_v2(**params)
        except Exception:
            logger.exception("Failed to list audit objects for prefix: %s", prefix)
            break
        for obj in resp.get("Contents", []):
            key = obj["Key"]
            file_name = key.rsplit("/", 1)[-1]
            if file_name == "audit.log" or file_name.startswith("audit.log."):
                keys.append(key)
        if resp.get("IsTruncated"):
            params["ContinuationToken"] = resp["NextContinuationToken"]
        else:
            break
    if newest_first:
        keys.reverse()
    return keys


def _get_events_from_key(key: str) -> list[dict]:
    """Download and parse events from one audit log object.
    Supports newline-delimited JSON (current) and single JSON object/list (backward compatible).
    """
    try:
        resp = _s3.get_object(Bucket=AUDIT_BUCKET, Key=key)
        raw = resp["Body"].read()
        text = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
    except ClientError as e:
        code = e.response["Error"]["Code"]
        if code == "NoSuchKey":
            return []
        if code == "InvalidObjectState" or "Glacier" in str(e):
            return []
        logger.warning("Failed to read audit object %s: %s", key, e)
        return []

    text = text.strip()
    if not text:
        return []

    # First try whole-body JSON (single object or array).
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return [parsed]
        if isinstance(parsed, list):
            return [item for item in parsed if isinstance(item, dict)]
    except json.JSONDecodeError:
        pass

    # Fallback: newline-delimited JSON.
    events = []
    for line in text.splitlines():
        item = line.strip()
        if not item or item.startswith("#"):
            continue
        try:
            parsed = json.loads(item)
            if isinstance(parsed, dict):
                events.append(parsed)
        except json.JSONDecodeError:
            logger.warning("Skipping malformed audit line in %s", key)
    return events


def _fetch_events_parallel(keys: list[str]) -> list[dict]:
    """Download multiple audit log files in parallel."""
    if not keys:
        return []
    events = []
    futures = {_read_pool.submit(_get_events_from_key, k): k for k in keys}
    for future in as_completed(futures):
        try:
            result = future.result()
        except Exception as e:
            logger.warning("Failed to fetch audit events from %s: %s", futures[future], e)
            continue
        if result:
            events.extend(result)
    return events


def _clamp_dates(date_from: Optional[str], date_to: Optional[str]):
    """
    Clamp requested date range to the hot window (last 30 days).
    Returns (start_date, end_date, warning_dict_or_None).
    Raises ValueError on malformed date strings.
    """
    today = date.today()
    earliest_available = today - timedelta(days=HOT_DAYS)
    warning = None

    # Parse end date
    if date_to:
        end = min(date.fromisoformat(date_to), today)
    else:
        end = today

    # Parse start date
    if date_from:
        start = date.fromisoformat(date_from)
    else:
        start = end  # default to same day as end (not today) if only date_to is given

    # Clamp both start and end to hot window
    if end < earliest_available:
        warning = {
            "code": "RETENTION_WINDOW_EXCEEDED",
            "message": f"Logs older than {HOT_DAYS} days are archived and not available for real-time query. Showing from {earliest_available.isoformat()}.",
        }
        start = earliest_available
        end = earliest_available
    elif start < earliest_available:
        warning = {
            "code": "RETENTION_WINDOW_EXCEEDED",
            "message": f"Logs older than {HOT_DAYS} days are archived and not available for real-time query. Showing from {earliest_available.isoformat()}.",
        }
        start = earliest_available

    if start > end:
        start = end

    return start, end, warning


def _resolve_names(events: list[dict], db) -> list[dict]:
    """Enrich events with user_name and org_name from DB."""
    user_ids = list({e.get("user_id") for e in events if e.get("user_id")})
    org_ids = list({e.get("org_id") for e in events if e.get("org_id")})

    user_map = {}
    org_map = {}

    if user_ids or org_ids:
        from db.models import Organization
        from db.models import User
        if user_ids:
            rows = db.query(User.id, User.username, User.email).filter(
                User.id.in_(user_ids)
            ).all()
            user_map = {r.id: r.username or r.email or str(r.id) for r in rows}
        if org_ids:
            rows = db.query(Organization.id, Organization.org_name).filter(Organization.id.in_(org_ids)).all()
            org_map = {r.id: r.org_name for r in rows}

    for ev in events:
        if not ev.get("user_name"):
            ev["user_name"] = user_map.get(ev.get("user_id"), str(ev.get("user_id", "")))
        ev["org_name"] = ev.get("org_name") or org_map.get(ev.get("org_id"), "")
        if not ev.get("display_target"):
            details = ev.get("details") or {}
            ev["display_target"] = details.get("summary") or ev.get("target_key", "")
    return events


def _resolve_org_scope(user: CurrentUser, requested_org_id: Optional[int], db):
    """Return (is_global_admin, scoped_org_id, scoped_org_folder_name)."""
    from db.models import Organization

    is_global = user.role_id in GLOBAL_ADMIN_ROLE_IDS
    scoped_org_id = requested_org_id
    scoped_org_folder = None

    if not is_global:
        own_org = None
        if user.organization_id:
            own_org = db.query(Organization).filter(
                Organization.id == user.organization_id,
                Organization.is_active == True,
            ).first()
        elif user.org_key:
            own_org = db.query(Organization).filter(
                Organization.org_key == user.org_key,
                Organization.is_active == True,
            ).first()
        if not own_org:
            return is_global, -1, "__missing_org__"
        return is_global, own_org.id, _normalize_org_folder(own_org.org_name, own_org.id)

    if requested_org_id:
        target_org = db.query(Organization).filter(
            Organization.id == requested_org_id,
            Organization.is_active == True,
        ).first()
        if not target_org:
            return is_global, requested_org_id, "__missing_org__"
        scoped_org_folder = _normalize_org_folder(target_org.org_name, target_org.id)

    return is_global, scoped_org_id, scoped_org_folder


@router.get("/audit")
async def list_audit_events(
    date_from: Optional[str] = Query(None, description="YYYY-MM-DD, max 30 days ago"),
    date_to: Optional[str] = Query(None, description="YYYY-MM-DD, max today"),
    org_id: Optional[int] = Query(None),
    event_type: Optional[str] = Query(None),
    user_id: Optional[int] = Query(None),
    page_size: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: CurrentUser = Depends(require_role(AUDIT_ROLES)),
    db: Session = Depends(get_db),
):
    """Paginated audit event listing. Reads from S3 hot tier (last 30 days)."""

    try:
        start, end, warning = _clamp_dates(date_from, date_to)
    except (ValueError, TypeError):
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail="Invalid date format. Use YYYY-MM-DD.")

    is_global, scoped_org_id, scoped_org_folder = _resolve_org_scope(user, org_id, db)

    # Collect daily audit files (audit.log and rotated files) newest-day-first.
    # Cap at 5000 files to prevent memory spikes.
    MAX_KEYS = 5000
    all_keys = []
    truncated = False
    for day in _date_range(start, end, newest_first=True):
        all_keys.extend(_list_keys_for_day(day, scoped_org_folder, newest_first=True))
        if len(all_keys) > MAX_KEYS:
            all_keys = all_keys[:MAX_KEYS]
            truncated = True
            break

    # Download events in parallel
    events = _fetch_events_parallel(all_keys)

    # Apply in-memory filters
    if event_type:
        events = [e for e in events if e.get("event_type") == event_type]
    if user_id:
        events = [e for e in events if e.get("user_id") == user_id]
    if org_id and is_global:
        events = [e for e in events if e.get("org_id") == org_id]

    # Sort by timestamp descending
    events.sort(key=lambda e: e.get("timestamp", ""), reverse=True)

    total = len(events)
    page_events = events[offset:offset + page_size]

    # Enrich with user/org names
    page_events = _resolve_names(page_events, db)

    if truncated and not warning:
        warning = {
            "code": "RESULTS_TRUNCATED",
            "message": f"Too many audit files in this range. Showing first {MAX_KEYS}. Narrow your date range for complete results.",
        }

    return {
        "events": [
            {
                **ev,
                "event_label": EVENT_TYPE_LABELS.get(ev.get("event_type", ""), ev.get("event_type", "")),
            }
            for ev in page_events
        ],
        "total": total,
        "offset": offset,
        "page_size": page_size,
        "has_more": (offset + page_size) < total,
        "truncated": truncated,
        "retention": {
            "hot_days": HOT_DAYS,
            "total_days": TOTAL_RETENTION_DAYS,
            "available_from": (date.today() - timedelta(days=HOT_DAYS)).isoformat(),
            "available_to": date.today().isoformat(),
        },
        "warning": warning,
        "event_types": list(EVENT_TYPE_LABELS.keys()),
    }


@router.get("/audit/export")
async def export_audit_csv(
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    org_id: Optional[int] = Query(None),
    event_type: Optional[str] = Query(None),
    user_id: Optional[int] = Query(None),
    user: CurrentUser = Depends(require_role(AUDIT_ROLES)),
    db: Session = Depends(get_db),
):
    """Export filtered audit events as CSV."""

    try:
        start, end, _ = _clamp_dates(date_from, date_to)
    except (ValueError, TypeError):
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail="Invalid date format. Use YYYY-MM-DD.")

    is_global, scoped_org_id, scoped_org_folder = _resolve_org_scope(user, org_id, db)

    MAX_EXPORT_KEYS = 10000
    all_keys = []
    export_truncated = False
    for day in _date_range(start, end, newest_first=True):
        all_keys.extend(_list_keys_for_day(day, scoped_org_folder, newest_first=True))
        if len(all_keys) > MAX_EXPORT_KEYS:
            all_keys = all_keys[:MAX_EXPORT_KEYS]
            export_truncated = True
            break

    events = _fetch_events_parallel(all_keys)

    if event_type:
        events = [e for e in events if e.get("event_type") == event_type]
    if user_id:
        events = [e for e in events if e.get("user_id") == user_id]

    events.sort(key=lambda e: e.get("timestamp", ""), reverse=True)
    events = _resolve_names(events, db)

    output = io.StringIO()
    writer = csv.writer(output)
    if export_truncated:
        writer.writerow([f"# WARNING: Results capped at {MAX_EXPORT_KEYS} files. Narrow date range for complete export."])
    writer.writerow([
        "Timestamp", "User", "User ID", "Event Type", "Description",
        "Source Path", "Destination Path", "Organization", "Organization ID", "IP", "Details JSON",
    ])
    for ev in events:
        details = ev.get("details") or {}
        writer.writerow([
            ev.get("timestamp", ""),
            ev.get("user_name", ""),
            ev.get("user_id", ""),
            ev.get("event_type", ""),
            ev.get("display_target") or details.get("summary") or ev.get("target_key", ""),
            details.get("source_path", ""),
            details.get("destination_path", ""),
            ev.get("org_name", ""),
            ev.get("org_id", ""),
            ev.get("ip_address", ""),
            json.dumps(details, default=str) if details else "",
        ])

    output.seek(0)
    resp_headers = {"Content-Disposition": "attachment; filename=audit_log.csv"}
    if export_truncated:
        resp_headers["X-Audit-Truncated"] = "true"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers=resp_headers,
    )
