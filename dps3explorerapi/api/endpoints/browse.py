"""
Browse & Folder Management endpoints (Phase 2).

- GET  /browse            — list folder contents (org-aware, ownership metadata)
- POST /folders/create    — create folder with ownership tracking
- POST /folders/rename    — rename folder (ownership-gated)
- POST /folders/delete    — delete folder (ownership-gated)
"""

from typing import List, Optional

import boto3
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from fastapi import Header

from core.audit import audit_log
from core.auth import CurrentUser, get_current_user, ADMIN_ROLE_IDS, GLOBAL_ADMIN_ROLE_IDS
from core.user_access import effective_s3_access, is_s3_deactivated
from core.config import settings
from core.permissions import check_prefix_access, filter_folders_by_grants, filter_files_by_grants
from db.postgresdb import get_db
from db.models import Organization, FolderMetadata, User, GroupMembership, UserGroup

router = APIRouter()


def _accessible_orgs_for_user(user: CurrentUser, db: Session) -> list:
    """Orgs visible in the explorer sidebar (grants + admin scope)."""
    response = []
    grant_org_ids = [
        row[0]
        for row in (
            db.query(UserGroup.org_id)
            .join(GroupMembership, GroupMembership.group_id == UserGroup.id)
            .filter(GroupMembership.user_id == user.id)
            .distinct()
            .all()
        )
    ]
    seen_org_ids = set()

    if grant_org_ids:
        grant_orgs = db.query(Organization).filter(
            Organization.id.in_(grant_org_ids), Organization.is_active == True
        ).all()
        for org in grant_orgs:
            seen_org_ids.add(org.id)
            response.append({
                "folder_name": org.org_name,
                "folder_path": "",
                "bucket_name": org.bucket_name,
                "org_id": org.id,
                "org_name": org.org_name,
                "org_key": org.org_key,
            })

    if user.role_id in ADMIN_ROLE_IDS:
        if user.role_id in GLOBAL_ADMIN_ROLE_IDS:
            admin_orgs = db.query(Organization).filter(Organization.is_active == True).all()
            for org in admin_orgs:
                if org.id in seen_org_ids:
                    continue
                seen_org_ids.add(org.id)
                response.append({
                    "folder_name": org.org_name,
                    "folder_path": "",
                    "bucket_name": org.bucket_name,
                    "org_id": org.id,
                    "org_name": org.org_name,
                    "org_key": org.org_key,
                })
        else:
            q = db.query(Organization).filter(Organization.is_active == True)
            if user.organization_id:
                q = q.filter(Organization.id == user.organization_id)
            elif user.org_key:
                q = q.filter(Organization.org_key == user.org_key)
            else:
                q = q.filter(False)
            for org in q.all():
                if org.id in seen_org_ids:
                    continue
                seen_org_ids.add(org.id)
                response.append({
                    "folder_name": org.org_name,
                    "folder_path": "",
                    "bucket_name": org.bucket_name,
                    "org_id": org.id,
                    "org_name": org.org_name,
                    "org_key": org.org_key,
                })

    return response


@router.get("/me")
async def explorer_access_status(
    db: Session = Depends(get_db),
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
):
    """
    Return S3 Explorer access status without blocking deactivated users.
    Used by the UI to show a clear message before other API calls fail with 403.
    Does not use get_current_user so deactivated accounts can still see why.
    """
    if not settings.DEV_AUTH_MODE:
        raise HTTPException(status_code=501, detail="DEV_AUTH_MODE is disabled; real auth is not configured yet")
    if not x_user_id or not str(x_user_id).strip().isdigit():
        raise HTTPException(status_code=401, detail="Missing or invalid X-User-Id header")

    user = db.query(User).filter(User.id == int(str(x_user_id).strip())).first()
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")

    account_active = bool(user.active)
    s3_deactivated = is_s3_deactivated(db, user.id)
    can_access = effective_s3_access(account_active, s3_deactivated)

    block_reason = None
    if not account_active:
        block_reason = "account"
    elif s3_deactivated:
        block_reason = "s3_explorer"

    return {
        "id": user.id,
        "user_name": user.username or "",
        "email": user.email or "",
        "can_access": can_access,
        "account_active": account_active,
        "s3_deactivated": s3_deactivated,
        "block_reason": block_reason,
    }


@router.get("/orgs")
async def list_accessible_orgs(
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List organizations the current user can open in the explorer sidebar."""
    return _accessible_orgs_for_user(user, db)


# ----------------------------- Schemas ----------------------------------

class BrowseRequest(BaseModel):
    org_id: int
    prefix: str = ""


class FolderItem(BaseModel):
    name: str
    key: str
    type: str = "folder"
    created_by: Optional[str] = None
    created_by_role: Optional[str] = None
    is_own: bool = False


class FileItem(BaseModel):
    name: str
    key: str
    type: str = "file"
    size: str
    last_modified: str


class BrowseResponse(BaseModel):
    folders: List[FolderItem]
    files: List[FileItem]
    path: str
    breadcrumb: List[str]


class FolderCreateRequest(BaseModel):
    org_id: int
    parent_prefix: str
    name: str

    @field_validator("name")
    @classmethod
    def validate_name(cls, v):
        return _validate_folder_name(v)


class FolderRenameRequest(BaseModel):
    org_id: int
    prefix: str
    new_name: str

    @field_validator("new_name")
    @classmethod
    def validate_new_name(cls, v):
        return _validate_folder_name(v)


def _validate_folder_name(v: str) -> str:
    v = v.strip()
    if not v:
        raise ValueError("Folder name cannot be empty")
    if "/" in v or "\\" in v:
        raise ValueError("Folder name cannot contain path separators")
    if "%" in v:
        raise ValueError("Folder name cannot contain '%' character")
    if v in (".", "..", "..."):
        raise ValueError("Reserved folder name")
    if len(v) > 255:
        raise ValueError("Folder name too long (max 255)")
    return v


class FolderDeleteRequest(BaseModel):
    org_id: int
    prefix: str


# ----------------------------- Helpers ----------------------------------

def _get_org_for_user(org_id: int, user: CurrentUser, db: Session) -> Organization:
    """Fetch org and verify user has access to it.
    Global admins (master_admin, super_admin) can access any org.
    Organization admins (role 1) and users must belong to the same org.
    """
    org = db.query(Organization).filter(Organization.id == org_id, Organization.is_active == True).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    if user.role_id not in GLOBAL_ADMIN_ROLE_IDS:
        if user.organization_id != org.id and user.subscription_id != org.org_key:
            raise HTTPException(status_code=403, detail="No access to this organization")

    return org


def _convert_size(number: int) -> str:
    if number < 1024:
        return f"{number} B"
    elif number < 1048576:
        return f"{number / 1024:.2f} KB"
    elif number < 1073741824:
        return f"{number / 1048576:.2f} MB"
    else:
        return f"{number / 1073741824:.2f} GB"


def _is_admin_user(user: CurrentUser) -> bool:
    return user.role_id in ADMIN_ROLE_IDS




# ----------------------------- Endpoints --------------------------------

@router.post("/browse", response_model=BrowseResponse)
async def browse_folder(
    payload: BrowseRequest,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    List contents of a folder within an org's bucket.
    Returns folders with ownership metadata and files with size/date.
    Admin users see all folders; regular users see all but files in
    user-created folders are hidden from admins (skeleton view).
    """
    org = _get_org_for_user(payload.org_id, user, db)

    s3 = boto3.client("s3", region_name=org.region)
    prefix = payload.prefix

    if prefix and not prefix.endswith("/"):
        prefix += "/"

    try:
        all_common_prefixes = []
        all_contents = []
        continuation_token = None

        while True:
            params = {
                "Bucket": org.bucket_name,
                "Prefix": prefix,
                "Delimiter": "/",
            }
            if continuation_token:
                params["ContinuationToken"] = continuation_token

            response = s3.list_objects_v2(**params)
            all_common_prefixes.extend(response.get("CommonPrefixes", []))
            all_contents.extend(response.get("Contents", []))

            if response.get("IsTruncated"):
                continuation_token = response.get("NextContinuationToken")
            else:
                break
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"S3 error: {str(e)}")

    folder_metadata_map = {}
    folder_keys_in_prefix = []

    common_prefixes = all_common_prefixes
    for cp in common_prefixes:
        folder_keys_in_prefix.append(cp["Prefix"])

    if folder_keys_in_prefix:
        metadata_rows = (
            db.query(FolderMetadata)
            .filter(
                FolderMetadata.org_id == org.id,
                FolderMetadata.key.in_(folder_keys_in_prefix),
            )
            .all()
        )
        for row in metadata_rows:
            folder_metadata_map[row.key] = row

    folders = []
    for cp in common_prefixes:
        folder_key = cp["Prefix"]
        folder_name = folder_key[len(prefix):].rstrip("/")
        if not folder_name:
            continue

        meta = folder_metadata_map.get(folder_key)
        is_own = False

        if meta:
            created_by_role = meta.created_by_role
            created_by = str(meta.created_by)
            is_own = meta.created_by == user.id
        else:
            created_by_role = "admin"
            created_by = None

        folders.append(FolderItem(
            name=folder_name,
            key=folder_key,
            created_by=created_by,
            created_by_role=created_by_role,
            is_own=is_own,
        ))

    # Grant-based folder filtering for non-admin users
    folders = filter_folders_by_grants(user, org.id, folders, prefix, db)

    # Block users who have no access to this prefix (applies to root and subfolders alike)
    check_prefix_access(user, org.id, prefix, db, require_write=False)

    files = []
    is_admin = _is_admin_user(user)

    current_folder_meta = None
    if prefix:
        current_folder_meta = (
            db.query(FolderMetadata)
            .filter(
                FolderMetadata.org_id == org.id,
                FolderMetadata.key == prefix,
            )
            .first()
        )
    is_user_created_folder = (
        current_folder_meta is not None
        and current_folder_meta.created_by_role == "user"
    )

    show_files = True
    is_global_admin = user.role_id in GLOBAL_ADMIN_ROLE_IDS
    if is_global_admin and is_user_created_folder:
        show_files = False

    if show_files:
        for obj in all_contents:
            name = obj["Key"][len(prefix):]
            if not name:
                continue
            files.append(FileItem(
                name=name,
                key=obj["Key"],
                size=_convert_size(obj["Size"]),
                last_modified=obj["LastModified"].strftime("%B %d, %Y"),
            ))

    # Grant-based file filtering for non-admin users
    files = filter_files_by_grants(user, org.id, files, prefix, db)

    breadcrumb = [part for part in prefix.split("/") if part]

    return BrowseResponse(
        folders=folders,
        files=files,
        path=prefix,
        breadcrumb=breadcrumb,
    )


@router.post("/folders/create", status_code=201)
async def create_folder(
    payload: FolderCreateRequest,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Create a new folder in S3 and track ownership.
    - Admins can create anywhere in the org bucket.
    - Read-write users can create within their granted prefixes.
    """
    org = _get_org_for_user(payload.org_id, user, db)
    is_admin = _is_admin_user(user)

    parent = payload.parent_prefix
    if parent and not parent.endswith("/"):
        parent += "/"

    if not is_admin:
        if not parent:
            raise HTTPException(
                status_code=403,
                detail="Users cannot create folders at the organization root",
            )

    new_key = f"{parent}{payload.name}/"

    # Enforce write grant for non-admin users (replaces legacy admin-folder check)
    check_prefix_access(user, org.id, parent or new_key, db, require_write=True)

    s3 = boto3.client("s3", region_name=org.region)

    existing = s3.list_objects_v2(
        Bucket=org.bucket_name, Prefix=new_key, MaxKeys=1
    )
    if existing.get("KeyCount", 0) > 0:
        raise HTTPException(
            status_code=409,
            detail="A folder with this name already exists at this location",
        )

    s3.put_object(Bucket=org.bucket_name, Key=new_key)

    role_label = "admin" if is_admin else "user"
    metadata = FolderMetadata(
        org_id=org.id,
        key=new_key,
        created_by=user.id,
        created_by_role=role_label,
    )
    db.add(metadata)
    db.commit()

    audit_log(
        user_id=user.id, event_type="FOLDER_CREATED",
        target_key=new_key, org_id=org.id, org_name=org.org_name,
        details={"name": payload.name}, request=request,
    )

    return {
        "key": new_key,
        "name": payload.name,
        "created_by_role": role_label,
    }


@router.post("/folders/rename")
async def rename_folder(
    payload: FolderRenameRequest,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Rename a folder. Ownership rules:
    - Admin-created folders: only admins can rename.
    - User-created folders: any org user can rename.
    - Missing metadata: treated as admin-owned (non-admins blocked).
    Note: RW/prefix-level permission is deferred to Phase 3.
    """
    org = _get_org_for_user(payload.org_id, user, db)
    is_admin = _is_admin_user(user)

    prefix = payload.prefix
    if not prefix.endswith("/"):
        prefix += "/"

    meta = db.query(FolderMetadata).filter(
        FolderMetadata.org_id == org.id,
        FolderMetadata.key == prefix,
    ).first()

    # User who created the folder can always rename it
    is_own_folder = meta is not None and meta.created_by == user.id

    if not is_own_folder:
        # Enforce write grant
        check_prefix_access(user, org.id, prefix, db, require_write=True)

    if not is_admin and not is_own_folder:
        if not meta or meta.created_by_role == "admin":
            raise HTTPException(
                status_code=403,
                detail="Only admins can rename admin-created folders",
            )

    parent_prefix = "/".join(prefix.rstrip("/").split("/")[:-1])
    if parent_prefix:
        parent_prefix += "/"
    new_key = f"{parent_prefix}{payload.new_name}/"

    s3 = boto3.client("s3", region_name=org.region)

    existing = s3.list_objects_v2(
        Bucket=org.bucket_name, Prefix=new_key, MaxKeys=1
    )
    if existing.get("KeyCount", 0) > 0:
        raise HTTPException(
            status_code=409,
            detail="A folder with this name already exists at this location",
        )

    objects_to_move = []
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=org.bucket_name, Prefix=prefix):
        for obj in page.get("Contents", []):
            objects_to_move.append(obj["Key"])

    if not objects_to_move:
        raise HTTPException(status_code=404, detail="Folder not found or empty")

    try:
        for old_key in objects_to_move:
            new_obj_key = new_key + old_key[len(prefix):]
            s3.copy_object(
                Bucket=org.bucket_name,
                CopySource={"Bucket": org.bucket_name, "Key": old_key},
                Key=new_obj_key,
            )

        failed_keys = []
        delete_batch = [{"Key": k} for k in objects_to_move]
        for i in range(0, len(delete_batch), 1000):
            batch = delete_batch[i:i + 1000]
            resp = s3.delete_objects(
                Bucket=org.bucket_name,
                Delete={"Objects": batch},
            )
            errors = resp.get("Errors", [])
            if errors:
                failed_keys.extend(e.get("Key", "") for e in errors)

        if failed_keys:
            raise HTTPException(
                status_code=502,
                detail=f"Rename partially failed: copied to new location but could not "
                       f"delete {len(failed_keys)} old object(s). Check bucket IAM permissions.",
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=f"S3 operation failed: {str(e)}",
        )

    if meta:
        meta.key = new_key
        db.commit()

    child_metas = db.query(FolderMetadata).filter(
        FolderMetadata.org_id == org.id,
        FolderMetadata.key.like(f"{prefix}%"),
    ).all()
    for child in child_metas:
        child.key = new_key + child.key[len(prefix):]
    db.commit()

    audit_log(
        user_id=user.id, event_type="FOLDER_RENAMED",
        target_key=new_key, org_id=org.id, org_name=org.org_name,
        details={"old_key": prefix, "new_name": payload.new_name}, request=request,
    )

    return {"old_key": prefix, "new_key": new_key, "name": payload.new_name}


TRASH_BUCKET = settings.TRASH_BUCKET


@router.post("/folders/delete")
async def delete_folder(
    payload: FolderDeleteRequest,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Move a folder to trash (soft delete). Objects are copied to the
    trash bucket preserving original path/bucket in metadata for restore.
    Trash items auto-expire after 30 days (S3 lifecycle rule on trash bucket).
    Ownership rules:
    - Admin-created folders: only admins can delete.
    - User-created folders: any org user can delete.
    - Missing metadata: treated as admin-owned (non-admins blocked).
    Note: RW/prefix-level permission is deferred to Phase 3.
    """
    org = _get_org_for_user(payload.org_id, user, db)
    is_admin = _is_admin_user(user)

    prefix = payload.prefix
    if not prefix.endswith("/"):
        prefix += "/"

    meta = db.query(FolderMetadata).filter(
        FolderMetadata.org_id == org.id,
        FolderMetadata.key == prefix,
    ).first()

    # User who created the folder can always delete it
    is_own_folder = meta is not None and meta.created_by == user.id

    if not is_own_folder:
        # Enforce write grant
        check_prefix_access(user, org.id, prefix, db, require_write=True)

    if not is_admin and not is_own_folder:
        if not meta or meta.created_by_role == "admin":
            raise HTTPException(
                status_code=403,
                detail="Only admins can delete admin-created folders",
            )

    s3 = boto3.client("s3", region_name=org.region)

    objects_to_move = []
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=org.bucket_name, Prefix=prefix):
        for obj in page.get("Contents", []):
            objects_to_move.append(obj["Key"])

    if not objects_to_move:
        raise HTTPException(status_code=404, detail="Folder not found or empty")

    # Snapshot folder metadata before deletion so restore can re-create it
    folder_meta_snapshot = {}
    meta_rows = (
        db.query(FolderMetadata)
        .filter(FolderMetadata.org_id == org.id, FolderMetadata.key.like(f"{prefix}%"))
        .all()
    )
    for row in meta_rows:
        folder_meta_snapshot[row.key] = {
            "created_by": str(row.created_by),
            "created_by_role": row.created_by_role or "admin",
        }

    failed_keys = []
    try:
        for obj_key in objects_to_move:
            trash_key = f"trash/{org.id}/{user.id}/{obj_key}"
            obj_metadata = {
                "path": obj_key,
                "bucket": org.bucket_name,
                "org_id": str(org.id),
                "deleted_by": str(user.id),
            }
            fm = folder_meta_snapshot.get(obj_key) or folder_meta_snapshot.get(prefix)
            if fm:
                obj_metadata["folder_created_by"] = fm["created_by"]
                obj_metadata["folder_created_by_role"] = fm["created_by_role"]
            s3.copy_object(
                CopySource={"Bucket": org.bucket_name, "Key": obj_key},
                Bucket=TRASH_BUCKET,
                Key=trash_key,
                Metadata=obj_metadata,
                MetadataDirective="REPLACE",
            )

        delete_batch = [{"Key": k} for k in objects_to_move]
        for i in range(0, len(delete_batch), 1000):
            batch = delete_batch[i:i + 1000]
            resp = s3.delete_objects(
                Bucket=org.bucket_name,
                Delete={"Objects": batch},
            )
            errors = resp.get("Errors", [])
            if errors:
                failed_keys.extend(e.get("Key", "") for e in errors)
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=f"S3 trash operation failed: {str(e)}",
        )

    if failed_keys:
        raise HTTPException(
            status_code=502,
            detail=f"Moved to trash but could not remove {len(failed_keys)} object(s) "
                   f"from source. Check bucket IAM permissions (s3:DeleteObject).",
        )

    db.query(FolderMetadata).filter(
        FolderMetadata.org_id == org.id,
        FolderMetadata.key.like(f"{prefix}%"),
    ).delete(synchronize_session=False)

    db.commit()

    audit_log(
        user_id=user.id, event_type="FOLDER_TRASHED",
        target_key=prefix, org_id=org.id, org_name=org.org_name,
        details={"objects_moved": len(objects_to_move)}, request=request,
    )

    return {"trashed": prefix, "objects_moved": len(objects_to_move)}


# ----------------------------- Trash Endpoints --------------------------------

class TrashItem(BaseModel):
    name: str
    key: str
    trash_key: str
    type: str
    size: str
    last_modified: str
    deleted_by: Optional[str] = None


class TrashListResponse(BaseModel):
    items: List[TrashItem]
    org_id: int


@router.post("/trash")
async def list_trash(
    payload: BrowseRequest,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    List trashed items for an org. Scoped:
    - Admins see all trashed items for the org.
    - Users see only their own trashed items.
    """
    org = _get_org_for_user(payload.org_id, user, db)
    is_admin = _is_admin_user(user)

    s3 = boto3.client("s3", region_name=org.region)

    if is_admin:
        trash_prefix = f"trash/{org.id}/"
    else:
        trash_prefix = f"trash/{org.id}/{user.id}/"

    items = []
    try:
        paginator = s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=TRASH_BUCKET, Prefix=trash_prefix):
            for obj in page.get("Contents", []):
                key_parts = obj["Key"].split("/")
                filename = key_parts[-1] if key_parts[-1] else "/".join(key_parts[-2:])
                if not filename:
                    continue
                is_folder = obj["Key"].endswith("/") and obj["Size"] == 0
                items.append(TrashItem(
                    name=filename,
                    key=obj["Key"].replace(f"trash/{org.id}/", "", 1),
                    trash_key=obj["Key"],
                    type="folder" if is_folder else "file",
                    size=_convert_size(obj["Size"]),
                    last_modified=obj["LastModified"].strftime("%B %d, %Y"),
                ))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"S3 error: {str(e)}")

    return TrashListResponse(items=items, org_id=org.id)


class RestoreRequest(BaseModel):
    org_id: int
    trash_key: str


@router.post("/trash/restore")
async def restore_from_trash(
    payload: RestoreRequest,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Restore an item (or full folder subtree) from trash back to its original
    location.  Each trashed object carries its own restore metadata.
    """
    org = _get_org_for_user(payload.org_id, user, db)
    is_admin = _is_admin_user(user)

    if not is_admin:
        expected_prefix = f"trash/{org.id}/{user.id}/"
        if not payload.trash_key.startswith(expected_prefix):
            raise HTTPException(status_code=403, detail="Can only restore your own trashed items")

    s3 = boto3.client("s3", region_name=org.region)

    is_folder = payload.trash_key.endswith("/")

    if is_folder:
        trash_keys = []
        paginator = s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=TRASH_BUCKET, Prefix=payload.trash_key):
            for obj in page.get("Contents", []):
                trash_keys.append(obj["Key"])
        if not trash_keys:
            raise HTTPException(status_code=404, detail="Trashed folder not found or empty")
    else:
        try:
            s3.head_object(Bucket=TRASH_BUCKET, Key=payload.trash_key)
        except Exception:
            raise HTTPException(status_code=404, detail="Trashed item not found")
        trash_keys = [payload.trash_key]

    # Pre-check first key for immediate 403 feedback (single-file only).
    # For folders, skip pre-check — let per-object loop handle mixed grants.
    checked_prefixes: dict = {}  # prefix -> bool (allowed or not)
    if trash_keys and not is_admin and not is_folder:
        first_key = trash_keys[0]
        try:
            meta_head = s3.head_object(Bucket=TRASH_BUCKET, Key=first_key)
            original_path = meta_head.get("Metadata", {}).get("path", "")
            if original_path:
                restore_prefix = "/".join(original_path.split("/")[:-1]) + "/" if "/" in original_path else ""
                check_prefix_access(user, org.id, restore_prefix, db, require_write=True)
                checked_prefixes[restore_prefix] = True
        except HTTPException:
            raise
        except Exception:
            pass

    restored_count = 0
    failed_keys = []

    for tk in trash_keys:
        try:
            obj_meta = s3.head_object(Bucket=TRASH_BUCKET, Key=tk)
        except Exception:
            failed_keys.append(tk)
            continue

        metadata = obj_meta.get("Metadata", {})
        original_path = metadata.get("path")
        original_bucket = metadata.get("bucket")

        if not original_path or not original_bucket:
            failed_keys.append(tk)
            continue

        if original_bucket != org.bucket_name:
            failed_keys.append(tk)
            continue

        # Per-object grant check (cached by prefix to avoid redundant DB queries)
        if not is_admin:
            restore_prefix = "/".join(original_path.split("/")[:-1]) + "/" if "/" in original_path else ""
            if restore_prefix not in checked_prefixes:
                try:
                    check_prefix_access(user, org.id, restore_prefix, db, require_write=True)
                    checked_prefixes[restore_prefix] = True
                except HTTPException:
                    checked_prefixes[restore_prefix] = False
            if not checked_prefixes[restore_prefix]:
                failed_keys.append(tk)
                continue

        try:
            s3.copy_object(
                CopySource={"Bucket": TRASH_BUCKET, "Key": tk},
                Bucket=original_bucket,
                Key=original_path,
                MetadataDirective="COPY",
            )
            s3.delete_object(Bucket=TRASH_BUCKET, Key=tk)
            restored_count += 1

            # Re-create FolderMetadata if this object represents a folder
            if original_path.endswith("/") and metadata.get("folder_created_by"):
                existing = db.query(FolderMetadata).filter(
                    FolderMetadata.org_id == org.id,
                    FolderMetadata.key == original_path,
                ).first()
                if not existing:
                    db.add(FolderMetadata(
                        org_id=org.id,
                        key=original_path,
                        created_by=int(metadata["folder_created_by"]),
                        created_by_role=metadata.get("folder_created_by_role", "admin"),
                    ))
        except Exception:
            failed_keys.append(tk)

    try:
        db.commit()
    except Exception:
        db.rollback()

    if restored_count == 0:
        raise HTTPException(status_code=502, detail="Restore failed for all objects")

    audit_log(
        user_id=user.id, event_type="TRASH_RESTORED",
        target_key=payload.trash_key, org_id=org.id, org_name=org.org_name,
        details={"objects_restored": restored_count}, request=request,
    )

    result = {"restored": payload.trash_key, "objects_restored": restored_count}
    if failed_keys:
        result["failed_count"] = len(failed_keys)
    return result


class PurgeRequest(BaseModel):
    org_id: int
    trash_key: str


@router.post("/trash/purge")
async def purge_from_trash(
    payload: PurgeRequest,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Permanently delete an item from trash. Cannot be undone.
    Admins can purge any item in their org; users can only purge their own.
    """
    org = _get_org_for_user(payload.org_id, user, db)
    is_admin = _is_admin_user(user)

    if not is_admin:
        expected_prefix = f"trash/{org.id}/{user.id}/"
        if not payload.trash_key.startswith(expected_prefix):
            raise HTTPException(status_code=403, detail="Can only purge your own trashed items")

    s3 = boto3.client("s3", region_name=org.region)

    is_folder = payload.trash_key.endswith("/")

    if is_folder:
        keys_to_delete = []
        paginator = s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=TRASH_BUCKET, Prefix=payload.trash_key):
            for obj in page.get("Contents", []):
                keys_to_delete.append({"Key": obj["Key"]})
        if not keys_to_delete:
            raise HTTPException(status_code=404, detail="Trashed folder not found or empty")
    else:
        try:
            s3.head_object(Bucket=TRASH_BUCKET, Key=payload.trash_key)
        except Exception:
            raise HTTPException(status_code=404, detail="Trashed item not found")
        keys_to_delete = [{"Key": payload.trash_key}]

    for batch_start in range(0, len(keys_to_delete), 1000):
        batch = keys_to_delete[batch_start : batch_start + 1000]
        try:
            resp = s3.delete_objects(Bucket=TRASH_BUCKET, Delete={"Objects": batch})
            errors = resp.get("Errors", [])
            if errors:
                raise HTTPException(
                    status_code=502,
                    detail=f"Purge partially failed: {len(errors)} object(s) could not be deleted",
                )
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Purge failed: {str(e)}")

    audit_log(
        user_id=user.id, event_type="TRASH_PURGED",
        target_key=payload.trash_key, org_id=org.id, org_name=org.org_name,
        details={"objects_purged": len(keys_to_delete)}, request=request,
    )

    return {"purged": payload.trash_key, "objects_purged": len(keys_to_delete)}
