"""
File preview endpoint — reads files from S3 and returns structured preview data.

Supports: CSV, XLSX, Parquet → tabular JSON; JSON → raw parsed JSON.
Backend-controlled pagination: only the requested page of rows is sent per response.

All endpoints require authentication and enforce folder grants for non-admin users.
"""

import io
import json
import time
import threading
from typing import Any

import numpy as np
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from core.audit import audit_log, audit_actor_fields
from core.auth import CurrentUser, get_current_user, ADMIN_ROLE_IDS
from core.permissions import check_prefix_access
from core.s3 import get_s3_client
from db.models import Organization
from db.postgresdb import get_db

router = APIRouter()

VIEWABLE_EXTENSIONS = {".csv", ".xlsx", ".parquet", ".json"}

s3_client = get_s3_client()

# Simple in-memory cache: avoids re-downloading + re-parsing on every page request.
# Key: (bucket, file_key) → { "df": DataFrame, "ts": timestamp }
_preview_cache: dict[tuple[str, str], dict] = {}
_sheet_names_cache: dict[tuple[str, str], dict] = {}
_cache_lock = threading.Lock()
_CACHE_TTL_SECONDS = 120
_MAX_PREVIEW_ROWS = 10000  # Hard cap: never parse/cache more than this many rows


def _get_cached_df(bucket: str, file_key: str) -> pd.DataFrame | None:
    """Return cached DataFrame if still fresh, else None."""
    key = (bucket, file_key)
    with _cache_lock:
        entry = _preview_cache.get(key)
        if entry and (time.time() - entry["ts"]) < _CACHE_TTL_SECONDS:
            return entry["df"]
        if entry:
            del _preview_cache[key]
    return None


def _set_cached_df(bucket: str, file_key: str, df: pd.DataFrame):
    """Store a parsed DataFrame in cache."""
    key = (bucket, file_key)
    with _cache_lock:
        # Evict old entries if cache grows too large (max 20 files)
        if len(_preview_cache) >= 20:
            oldest_key = min(_preview_cache, key=lambda k: _preview_cache[k]["ts"])
            del _preview_cache[oldest_key]
        _preview_cache[key] = {"df": df, "ts": time.time()}


def _sanitize_rows(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Convert DataFrame rows to JSON-safe dicts, handling NaN/NaT/Inf."""
    raw_rows = df.astype(object).to_dict(orient="records")
    rows: list[dict[str, Any]] = []
    for raw in raw_rows:
        clean: dict[str, Any] = {}
        for k, v in raw.items():
            if v is None:
                clean[k] = None
            elif isinstance(v, float):
                clean[k] = v if np.isfinite(v) else None
            elif pd.isna(v):
                clean[k] = None
            else:
                clean[k] = v
        rows.append(clean)
    return rows


def _read_bytes_to_df(raw: bytes, filename: str, sheet_name=None) -> pd.DataFrame:
    """Read raw bytes into a DataFrame, capped at _MAX_PREVIEW_ROWS."""
    import pyarrow.parquet as pq
    import pyarrow as pa

    suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if suffix == "parquet":
        pf = pq.ParquetFile(io.BytesIO(raw))
        batches = []
        rows_read = 0
        for batch in pf.iter_batches(batch_size=min(_MAX_PREVIEW_ROWS, 5000)):
            batches.append(batch)
            rows_read += len(batch)
            if rows_read >= _MAX_PREVIEW_ROWS:
                break
        table = pa.Table.from_batches(batches)
        df = table.to_pandas().head(_MAX_PREVIEW_ROWS)
    elif suffix == "xlsx":
        target_sheet = sheet_name if sheet_name else 0
        df = pd.read_excel(io.BytesIO(raw), sheet_name=target_sheet, nrows=_MAX_PREVIEW_ROWS)
    else:
        df = pd.read_csv(io.BytesIO(raw), nrows=_MAX_PREVIEW_ROWS)
    return df


def _get_xlsx_sheet_names(raw: bytes) -> list[str]:
    """Return list of sheet names from an xlsx file without parsing all data."""
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    names = wb.sheetnames
    wb.close()
    return names


def _cache_sheet_names(bucket: str, file_key: str, names: list[str]):
    """Store sheet names in cache with size cap (max 50 entries)."""
    key = (bucket, file_key)
    with _cache_lock:
        if len(_sheet_names_cache) >= 50:
            oldest_key = min(_sheet_names_cache, key=lambda k: _sheet_names_cache[k]["ts"])
            del _sheet_names_cache[oldest_key]
        _sheet_names_cache[key] = {"names": names, "ts": time.time()}


def _resolve_bucket_for_preview(user: CurrentUser, base_path: str, db: Session) -> str:
    """Resolve bucket from org table for the given basePath."""
    from core.utils import get_all_folders_from_user_id
    folders = get_all_folders_from_user_id(user.id)
    matches = [f for f in folders if f.folder_path == base_path]
    if matches:
        return matches[0].bucket_name
    matches = [f for f in folders if f.bucket_name == base_path]
    if matches:
        return matches[0].bucket_name
    if base_path:
        org = db.query(Organization).filter(Organization.bucket_name == base_path, Organization.is_active == True).first()
        if org:
            return org.bucket_name
    raise HTTPException(status_code=404, detail="Bucket not found")


def _audit_file_viewed(
    user: CurrentUser,
    bucket_name: str,
    file_key: str,
    filename: str,
    page: int,
    db: Session,
    request: Request,
) -> None:
    """Log FILE_VIEWED once per open (first page only) to avoid pagination spam."""
    if page != 1:
        return
    org = db.query(Organization).filter(Organization.bucket_name == bucket_name, Organization.is_active == True).first()
    audit_log(
        event_type="FILE_VIEWED",
        target_key=file_key,
        org_id=org.id if org else None,
        org_name=org.org_name if org else None,
        details={
            "summary": f"{user.user_name or 'User'} viewed '{file_key}'",
            "file_path": file_key,
            "filename": filename,
            "bucket": bucket_name,
        },
        request=request,
        **audit_actor_fields(user),
    )


@router.get("/preview")
async def preview_file(
    request: Request,
    file_key: str = Query(..., description="Full S3 key of the file"),
    basePath: str = Query(..., description="Base path / bucket identifier"),
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(50, ge=1, le=500, description="Rows per page"),
    sheet: str = Query(None, description="Sheet name for xlsx files (default: first sheet)"),
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Preview a file from S3 with backend-controlled pagination.

    Returns:
    - CSV/Parquet/XLSX → { format: "table", columns, rows, total_rows, page, page_size, total_pages, filename }
    - JSON → { format: "json", data, filename }
    """
    bucket_name = _resolve_bucket_for_preview(user, basePath, db)

    # Enforce grants for non-admin users
    if user.role_id not in ADMIN_ROLE_IDS:
        org = db.query(Organization).filter(
            Organization.bucket_name == bucket_name, Organization.is_active == True
        ).first()
        if not org:
            raise HTTPException(status_code=403, detail="Organization not found")
        check_prefix_access(user, org.id, file_key, db, require_write=False)

    # Validate file extension
    filename = file_key.rsplit("/", 1)[-1] if "/" in file_key else file_key
    suffix = ""
    if "." in filename:
        suffix = "." + filename.rsplit(".", 1)[-1].lower()
    if suffix not in VIEWABLE_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail=f"File type '{suffix}' is not supported for preview. Supported: {', '.join(sorted(VIEWABLE_EXTENSIONS))}",
        )

    # JSON files → return raw parsed (no pagination needed)
    if suffix == ".json":
        try:
            response = s3_client.get_object(Bucket=bucket_name, Key=file_key)
            raw_bytes = response["Body"].read()
            data = json.loads(raw_bytes.decode("utf-8"))
        except s3_client.exceptions.NoSuchKey:
            raise HTTPException(status_code=404, detail="File not found in S3")
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            raise HTTPException(status_code=422, detail=f"Cannot parse JSON: {e}")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to read file: {str(e)}")
        _audit_file_viewed(user, bucket_name, file_key, filename, page, db, request)
        return {"format": "json", "data": data, "filename": filename}

    # Tabular files → check cache, else download + parse
    sheet_names = None
    raw_bytes = None

    # For xlsx, resolve sheet names first (from cache or S3) to normalize cache key
    if suffix == ".xlsx":
        with _cache_lock:
            cached_sheets = _sheet_names_cache.get((bucket_name, file_key))
            if cached_sheets and (time.time() - cached_sheets["ts"]) < _CACHE_TTL_SECONDS:
                sheet_names = cached_sheets["names"]

    # Normalize sheet for cache key: if no sheet specified, use actual first sheet name
    resolved_sheet = sheet
    if suffix == ".xlsx" and not sheet and sheet_names:
        resolved_sheet = sheet_names[0]

    cache_key_suffix = f"::sheet={resolved_sheet}" if resolved_sheet and suffix == ".xlsx" else ""
    cache_file_key = file_key + cache_key_suffix

    df = _get_cached_df(bucket_name, cache_file_key)

    if df is None:
        try:
            response = s3_client.get_object(Bucket=bucket_name, Key=file_key)
            raw_bytes = response["Body"].read()
        except s3_client.exceptions.NoSuchKey:
            raise HTTPException(status_code=404, detail="File not found in S3")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to read file from S3: {str(e)}")

        if suffix == ".xlsx" and sheet_names is None:
            try:
                sheet_names = _get_xlsx_sheet_names(raw_bytes)
                _cache_sheet_names(bucket_name, file_key, sheet_names)
            except Exception:
                sheet_names = []
            # Now that we know actual sheet names, normalize the cache key
            if not sheet and sheet_names:
                resolved_sheet = sheet_names[0]
                cache_file_key = file_key + f"::sheet={resolved_sheet}"
                # Check if this normalized key is already cached
                df = _get_cached_df(bucket_name, cache_file_key)

        if df is None:
            try:
                df = _read_bytes_to_df(raw_bytes, filename, sheet_name=resolved_sheet)
            except Exception as e:
                raise HTTPException(status_code=422, detail=f"Cannot read file: {e}")
            _set_cached_df(bucket_name, cache_file_key, df)

    # If we still need sheet_names (df was cached but names weren't fetched this request)
    if suffix == ".xlsx" and sheet_names is None:
        with _cache_lock:
            cached_sheets = _sheet_names_cache.get((bucket_name, file_key))
            if cached_sheets and (time.time() - cached_sheets["ts"]) < _CACHE_TTL_SECONDS:
                sheet_names = cached_sheets["names"]
        if sheet_names is None:
            try:
                response = s3_client.get_object(Bucket=bucket_name, Key=file_key)
                raw_bytes = response["Body"].read()
                sheet_names = _get_xlsx_sheet_names(raw_bytes)
                _cache_sheet_names(bucket_name, file_key, sheet_names)
            except Exception:
                sheet_names = []

    total_rows = len(df)
    total_pages = max(1, -(-total_rows // page_size))  # ceil division

    # Clamp page
    if page > total_pages:
        page = total_pages

    # Slice to requested page
    offset = (page - 1) * page_size
    page_df = df.iloc[offset:offset + page_size]
    columns = list(df.columns)
    rows = _sanitize_rows(page_df)

    result = {
        "format": "table",
        "columns": columns,
        "rows": rows,
        "total_rows": total_rows,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "filename": filename,
    }
    if sheet_names is not None:
        result["sheets"] = sheet_names
        result["active_sheet"] = resolved_sheet if resolved_sheet else (sheet_names[0] if sheet_names else None)

    _audit_file_viewed(user, bucket_name, file_key, filename, page, db, request)
    return result
