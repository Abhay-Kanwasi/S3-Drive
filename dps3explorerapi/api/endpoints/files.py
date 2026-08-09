"""
File Operations endpoints (Phase 2.6).

- POST /files/rename  — rename a file (same folder, new name)
- POST /files/copy    — copy a file to a target folder
- POST /files/move    — move a file to a target folder (copy + delete source)
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.audit import audit_log, audit_actor_fields, file_transfer_details
from core.auth import CurrentUser, get_current_user, ADMIN_ROLE_IDS, GLOBAL_ADMIN_ROLE_IDS
from core.permissions import check_prefix_access, get_user_granted_prefixes
from core.s3 import get_s3_client
from db.postgresdb import get_db
from db.models import Organization

router = APIRouter()

s3_client = get_s3_client()

PART_SIZE = 100 * 1024 * 1024  # 100 MB
SINGLE_COPY_LIMIT = 5 * 1024 * 1024 * 1024  # 5 GB


# ----------------------------- Schemas ----------------------------------

class RenameRequest(BaseModel):
    org_id: int
    file_key: str
    new_name: str
    basePath: str


class CopyMoveRequest(BaseModel):
    org_id: int
    file_key: str
    target_prefix: str
    basePath: str


# ----------------------------- Helpers ----------------------------------

def _get_org_and_bucket(org_id: int, user: CurrentUser, db: Session) -> tuple:
    """Resolve org and verify user has access (same org guard as browse)."""
    org = db.query(Organization).filter(Organization.id == org_id, Organization.is_active == True).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    if user.role_id not in GLOBAL_ADMIN_ROLE_IDS:
        if user.organization_id != org.id and user.subscription_id != org.org_key:
            raise HTTPException(status_code=403, detail="No access to this organization")
    return org, org.bucket_name


def _check_strict_read(user: CurrentUser, org_id: int, prefix: str, db: Session):
    """Strict read check for file operations — the grant must directly cover
    the file's prefix (no navigation pass-through)."""
    from core.permissions import _user_has_any_memberships

    if not _user_has_any_memberships(user.id, org_id, db):
        raise HTTPException(
            status_code=403,
            detail="No folder access granted for this organization",
        )

    grants = get_user_granted_prefixes(user.id, org_id, db)
    norm_prefix = prefix if prefix.endswith("/") or prefix == "" else prefix + "/"
    for grant_prefix, _access_level in grants:
        if norm_prefix.startswith(grant_prefix):
            return
    raise HTTPException(
        status_code=403,
        detail=f"No grant covers this path. You do not have permission to access '{prefix}'",
    )


def _get_prefix(file_key: str) -> str:
    """Extract the folder prefix from a full file key."""
    parts = file_key.rsplit("/", 1)
    return parts[0] + "/" if len(parts) > 1 else ""


def _get_filename(file_key: str) -> str:
    """Extract filename from a full file key."""
    return file_key.rsplit("/", 1)[-1]


def _check_extension_allowed(filename: str, db: Session):
    """Reuse the extension check from boto_services."""
    from api.endpoints.boto_services import _check_file_extension
    _check_file_extension(filename, db)


def _file_exists(bucket: str, key: str) -> bool:
    """Check if a file already exists at the given key."""
    try:
        s3_client.head_object(Bucket=bucket, Key=key)
        return True
    except s3_client.exceptions.ClientError as e:
        if e.response["Error"]["Code"] == "404":
            return False
        raise


def _get_file_size(bucket: str, key: str) -> int:
    """Get the size of a file in bytes."""
    try:
        resp = s3_client.head_object(Bucket=bucket, Key=key)
        return resp["ContentLength"]
    except s3_client.exceptions.ClientError as e:
        if e.response["Error"]["Code"] == "404":
            raise HTTPException(status_code=404, detail="Source file not found")
        raise


def _s3_copy(bucket: str, source_key: str, dest_key: str, file_size: int):
    """Copy a file within the same bucket. Uses sequential multipart copy
    for files larger than 5 GB."""
    copy_source = {"Bucket": bucket, "Key": source_key}

    if file_size <= SINGLE_COPY_LIMIT:
        s3_client.copy_object(Bucket=bucket, CopySource=copy_source, Key=dest_key)
        return

    upload = s3_client.create_multipart_upload(Bucket=bucket, Key=dest_key)
    upload_id = upload["UploadId"]

    try:
        part_count = -(-file_size // PART_SIZE)
        parts = []

        for i in range(part_count):
            start = i * PART_SIZE
            end = min(start + PART_SIZE - 1, file_size - 1)
            resp = s3_client.upload_part_copy(
                Bucket=bucket,
                Key=dest_key,
                CopySource=copy_source,
                UploadId=upload_id,
                PartNumber=i + 1,
                CopySourceRange=f"bytes={start}-{end}",
            )
            parts.append({"PartNumber": i + 1, "ETag": resp["CopyPartResult"]["ETag"]})

        s3_client.complete_multipart_upload(
            Bucket=bucket,
            Key=dest_key,
            UploadId=upload_id,
            MultipartUpload={"Parts": parts},
        )
    except Exception:
        s3_client.abort_multipart_upload(Bucket=bucket, Key=dest_key, UploadId=upload_id)
        raise


# ----------------------------- Endpoints ----------------------------------

@router.post("/rename")
async def rename_file(
    payload: RenameRequest,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Rename a file (same folder, new name)."""
    org, bucket = _get_org_and_bucket(payload.org_id, user, db)

    # Grant check: write access on the file's prefix
    prefix = _get_prefix(payload.file_key)
    if user.role_id not in ADMIN_ROLE_IDS:
        check_prefix_access(user, org.id, prefix, db, require_write=True)

    # Validate new filename extension
    new_name = payload.new_name.strip()
    if not new_name or "/" in new_name:
        raise HTTPException(status_code=422, detail="Invalid filename")
    _check_extension_allowed(new_name, db)

    # Build new key
    new_key = prefix + new_name

    # Collision check
    if _file_exists(bucket, new_key):
        raise HTTPException(status_code=409, detail=f"A file named '{new_name}' already exists in this folder")

    # Check source exists and get size
    file_size = _get_file_size(bucket, payload.file_key)

    # Copy + delete
    try:
        _s3_copy(bucket, payload.file_key, new_key, file_size)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="File rename failed. Please try again.")
    s3_client.delete_object(Bucket=bucket, Key=payload.file_key)

    audit_log(
        event_type="FILE_RENAMED",
        org_id=org.id,
        org_name=org.org_name,
        target_key=new_key,
        details=file_transfer_details(
            "renamed",
            user.user_name,
            payload.file_key,
            new_key,
            new_name=new_name,
            size_bytes=file_size,
            bucket=bucket,
        ),
        request=request,
        **audit_actor_fields(user),
    )

    return {"message": "File renamed successfully", "new_key": new_key}


@router.post("/copy")
async def copy_file(
    payload: CopyMoveRequest,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Copy a file to a target folder."""
    org, bucket = _get_org_and_bucket(payload.org_id, user, db)

    # Grant check: strict read on source, write on target
    source_prefix = _get_prefix(payload.file_key)
    target_prefix = payload.target_prefix if payload.target_prefix else ""
    if target_prefix:
        target_prefix = target_prefix.rstrip("/") + "/"

    if user.role_id not in ADMIN_ROLE_IDS:
        _check_strict_read(user, org.id, source_prefix, db)
        check_prefix_access(user, org.id, target_prefix, db, require_write=True)

    # Build destination key
    filename = _get_filename(payload.file_key)
    dest_key = target_prefix + filename

    # Collision check
    if _file_exists(bucket, dest_key):
        raise HTTPException(status_code=409, detail=f"A file named '{filename}' already exists in the target folder")

    # Get source size
    file_size = _get_file_size(bucket, payload.file_key)

    # Copy
    try:
        _s3_copy(bucket, payload.file_key, dest_key, file_size)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="File copy failed. Please try again.")

    audit_log(
        event_type="FILE_COPIED",
        org_id=org.id,
        org_name=org.org_name,
        target_key=dest_key,
        details=file_transfer_details(
            "copied",
            user.user_name,
            payload.file_key,
            dest_key,
            filename=filename,
            size_bytes=file_size,
            bucket=bucket,
        ),
        request=request,
        **audit_actor_fields(user),
    )

    return {"message": "File copied successfully", "new_key": dest_key}


@router.post("/move")
async def move_file(
    payload: CopyMoveRequest,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Move a file to a target folder (copy + delete source)."""
    org, bucket = _get_org_and_bucket(payload.org_id, user, db)

    # Grant check: write on both source and target
    source_prefix = _get_prefix(payload.file_key)
    target_prefix = payload.target_prefix if payload.target_prefix else ""
    if target_prefix:
        target_prefix = target_prefix.rstrip("/") + "/"

    if user.role_id not in ADMIN_ROLE_IDS:
        check_prefix_access(user, org.id, source_prefix, db, require_write=True)
        check_prefix_access(user, org.id, target_prefix, db, require_write=True)

    # Build destination key
    filename = _get_filename(payload.file_key)
    dest_key = target_prefix + filename

    # Collision check
    if _file_exists(bucket, dest_key):
        raise HTTPException(status_code=409, detail=f"A file named '{filename}' already exists in the target folder")

    # Get source size
    file_size = _get_file_size(bucket, payload.file_key)

    # Copy then delete source
    try:
        _s3_copy(bucket, payload.file_key, dest_key, file_size)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="File move failed. Please try again.")
    s3_client.delete_object(Bucket=bucket, Key=payload.file_key)

    audit_log(
        event_type="FILE_MOVED",
        org_id=org.id,
        org_name=org.org_name,
        target_key=dest_key,
        details=file_transfer_details(
            "moved",
            user.user_name,
            payload.file_key,
            dest_key,
            filename=filename,
            size_bytes=file_size,
            bucket=bucket,
        ),
        request=request,
        **audit_actor_fields(user),
    )

    return {"message": "File moved successfully", "new_key": dest_key}
