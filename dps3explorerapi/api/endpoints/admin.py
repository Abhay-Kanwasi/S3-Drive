"""
Admin endpoints for organization onboarding.

- GET  /admin/me                    — current admin identity
- GET  /admin/organizations         — list onboarded orgs (alias: /admin/orgs)
- POST /admin/organizations         — create/onboard org (alias: /admin/orgs/onboard)
- GET  /admin/available-buckets     — list S3 buckets not yet onboarded
"""

import re
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session

from core.audit import audit_log
from core.auth import (
    CurrentUser, require_role,
    GLOBAL_ADMIN_ROLE_IDS
)
from core.s3 import get_s3_client
from db.postgresdb import get_db
from db.models import Organization, FolderMetadata

router = APIRouter()

ONBOARD_ROLES = ["super_admin", "master_admin"]
ALL_ADMIN_ROLES = ["admin", "master_admin", "super_admin"]


# ----------------------------- Schemas ----------------------------------

class OrgOut(BaseModel):
    id: int
    org_key: str
    subscription_id: str  # compat alias of org_key
    org_name: str
    bucket_name: Optional[str] = None
    region: str
    max_upload_size_bytes: int
    is_active: bool
    created_at: Optional[str] = None

    class Config:
        from_attributes = True


class BucketOut(BaseModel):
    name: str
    region: str


class OnboardRequest(BaseModel):
    org_key: str = Field(..., min_length=1)
    org_name: str = Field(..., min_length=1)
    bucket_name: str = Field(..., min_length=1)


class OnboardResponse(BaseModel):
    id: int
    org_name: str
    bucket_name: str
    region: str
    org_key: str
    subscription_id: str  # compat alias of org_key


def _org_out(org: Organization) -> OrgOut:
    return OrgOut(
        id=org.id,
        org_key=org.org_key,
        subscription_id=org.org_key,
        org_name=org.org_name,
        bucket_name=org.bucket_name,
        region=org.region,
        max_upload_size_bytes=org.max_upload_size_bytes,
        is_active=org.is_active,
        created_at=org.created_at.isoformat() if org.created_at else None,
    )


# ----------------------------- Helpers ----------------------------------

def _ensure_org_binding_available(
    db: Session, *, org_key: str, bucket_name: str
) -> None:
    """Reject if org_key or bucket is already bound (active or legacy inactive row)."""
    rows = (
        db.query(Organization)
        .filter(
            or_(
                Organization.org_key == org_key,
                Organization.bucket_name == bucket_name,
            )
        )
        .all()
    )
    for row in rows:
        if row.is_active:
            if row.org_key == org_key:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="This organization is already onboarded",
                )
            if row.bucket_name == bucket_name:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="This bucket is already assigned to another organization",
                )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "A legacy inactive org binding still exists for this org_key or bucket. "
                "Clean up the inactive organizations row, then retry."
            ),
        )


# ----------------------------- Endpoints --------------------------------

@router.get("/me")
async def admin_me(
    user: CurrentUser = Depends(require_role(ALL_ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    """Return the current admin's role and resolved org (if org-scoped)."""
    result = {
        "id": user.id,
        "user_name": user.user_name,
        "email": user.email,
        "role_id": user.role_id,
        "role_label": user.role_label,
        "organization_id": user.organization_id,
        "org_key": user.org_key,
        "subscription_id": user.subscription_id,
        "is_global_admin": user.role_id in GLOBAL_ADMIN_ROLE_IDS,
        "org": None,
    }
    if user.role_id not in GLOBAL_ADMIN_ROLE_IDS and user.organization_id:
        org = db.query(Organization).filter(
            Organization.id == user.organization_id,
            Organization.is_active == True,
        ).first()
        if org:
            result["org"] = {
                "id": org.id,
                "org_name": org.org_name,
                "org_key": org.org_key,
                "subscription_id": org.org_key,
            }
    return result


async def _list_onboarded_orgs(
    user: CurrentUser,
    db: Session,
) -> List[OrgOut]:
    """Return onboarded organizations. Global admins see all; org admins see their own."""
    q = db.query(Organization).filter(Organization.is_active == True)
    if user.role_id not in GLOBAL_ADMIN_ROLE_IDS:
        if user.organization_id:
            q = q.filter(Organization.id == user.organization_id)
        elif user.org_key:
            q = q.filter(Organization.org_key == user.org_key)
        else:
            return []
    return [_org_out(org) for org in q.all()]


@router.get("/organizations", response_model=List[OrgOut])
async def list_organizations(
    user: CurrentUser = Depends(require_role(ALL_ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    return await _list_onboarded_orgs(user, db)


@router.get("/orgs", response_model=List[OrgOut])
async def list_onboarded_orgs(
    user: CurrentUser = Depends(require_role(ALL_ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    """Alias of GET /admin/organizations."""
    return await _list_onboarded_orgs(user, db)


@router.get("/available-buckets", response_model=List[BucketOut])
async def list_available_buckets(
    user: CurrentUser = Depends(require_role(ONBOARD_ROLES)),
    db: Session = Depends(get_db),
):
    """
    List S3 buckets from the AWS account that are NOT yet onboarded.
    Region is resolved from AWS, not client-supplied.
    """
    s3 = get_s3_client()
    try:
        response = s3.list_buckets()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to list S3 buckets: {str(e)}",
        )

    all_buckets = response.get("Buckets", [])

    already_onboarded = {
        row.bucket_name
        for row in db.query(Organization.bucket_name).filter(Organization.is_active == True).all()
        if row.bucket_name
    }

    available = []
    for bucket in all_buckets:
        bucket_name = bucket["Name"]
        if bucket_name not in already_onboarded:
            region = _get_bucket_region(s3, bucket_name)
            available.append(BucketOut(name=bucket_name, region=region))

    return available


async def _create_onboard_org(
    payload: OnboardRequest,
    request: Request,
    user: CurrentUser,
    db: Session,
) -> OnboardResponse:
    """
    Create/onboard an organization by binding org_key + name to an S3 bucket.

    - Validates no duplicate org_key or bucket_name
    - Validates the bucket exists in AWS (head_bucket)
    - Resolves region from AWS (not client-supplied)
    """
    org_key = payload.org_key.strip()
    org_name = payload.org_name.strip()
    bucket_name = payload.bucket_name.strip()
    if not org_key or not org_name or not bucket_name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="org_key, org_name, and bucket_name are required",
        )

    _ensure_org_binding_available(
        db,
        org_key=org_key,
        bucket_name=bucket_name,
    )

    s3 = get_s3_client()
    try:
        s3.head_bucket(Bucket=bucket_name)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Bucket does not exist or is not accessible",
        )

    region = _get_bucket_region(s3, bucket_name)

    new_org = Organization(
        org_key=org_key,
        org_name=org_name,
        bucket_name=bucket_name,
        region=region,
        onboarded_by=user.id,
    )
    db.add(new_org)
    db.commit()
    db.refresh(new_org)

    audit_log(
        user_id=user.id, event_type="ORG_ONBOARDED",
        target_key=bucket_name, org_id=new_org.id, org_name=org_name,
        details={"org_name": org_name, "org_key": org_key, "subscription_id": org_key},
        request=request,
    )

    _backfill_folder_metadata(s3, new_org, user, db)

    return OnboardResponse(
        id=new_org.id,
        org_name=new_org.org_name,
        bucket_name=new_org.bucket_name,
        region=new_org.region,
        org_key=new_org.org_key,
        subscription_id=new_org.org_key,
    )


@router.post("/organizations", response_model=OnboardResponse, status_code=status.HTTP_201_CREATED)
async def create_organization(
    payload: OnboardRequest,
    request: Request,
    user: CurrentUser = Depends(require_role(ONBOARD_ROLES)),
    db: Session = Depends(get_db),
):
    return await _create_onboard_org(payload, request, user, db)


@router.post("/orgs/onboard", response_model=OnboardResponse, status_code=status.HTTP_201_CREATED)
async def onboard_org(
    payload: OnboardRequest,
    request: Request,
    user: CurrentUser = Depends(require_role(ONBOARD_ROLES)),
    db: Session = Depends(get_db),
):
    """Alias of POST /admin/organizations."""
    return await _create_onboard_org(payload, request, user, db)


# ----------------------------- Helpers ----------------------------------

def _backfill_folder_metadata(s3_client, org: Organization, user: CurrentUser, db: Session):
    """Scan existing top-level folders in the bucket and create FolderMetadata
    rows so they appear with admin icons immediately after onboarding.
    Non-fatal — silently continues if anything fails."""
    try:
        resp = s3_client.list_objects_v2(
            Bucket=org.bucket_name, Prefix="", Delimiter="/",
        )
        for cp in resp.get("CommonPrefixes", []):
            folder_key = cp["Prefix"]
            existing = db.query(FolderMetadata).filter(
                FolderMetadata.org_id == org.id,
                FolderMetadata.key == folder_key,
            ).first()
            if not existing:
                db.add(FolderMetadata(
                    org_id=org.id,
                    key=folder_key,
                    created_by=user.id,
                    created_by_role="admin",
                ))
        db.commit()
    except Exception:
        db.rollback()


def _get_bucket_region(s3_client, bucket_name: str) -> str:
    """Get the region of a bucket. Returns 'us-east-1' if None (AWS default)."""
    try:
        location = s3_client.get_bucket_location(Bucket=bucket_name)
        region = location.get("LocationConstraint")
        return region if region else "us-east-1"
    except Exception:
        return "us-east-1"


# ========================= Platform Settings =============================

from db.models import PlatformSettings

MASTER_ONLY_ROLES = ["master_admin", "super_admin"]

DEFAULT_EXTENSIONS = [
    {"ext": ".parquet", "color": "#10b981"},
    {"ext": ".orc", "color": "#10b981"},
    {"ext": ".csv", "color": "#10b981"},
    {"ext": ".json", "color": "#f59e0b"},
    {"ext": ".zip", "color": "#8b5cf6"},
    {"ext": ".gz", "color": "#8b5cf6"},
    {"ext": ".xlsx", "color": "#10b981"},
    {"ext": ".txt", "color": "#3b82f6"},
    {"ext": ".pdf", "color": "#3b82f6"},
    {"ext": ".docx", "color": "#3b82f6"},
    {"ext": ".png", "color": "#ec4899"},
]
DEFAULT_MAX_UPLOAD_BYTES = 5 * 1024 * 1024 * 1024  # 5 GB


def _get_or_create_settings(db: Session) -> PlatformSettings:
    """Return the singleton settings row, creating it if missing. Migrates old string-array format to objects."""
    row = db.query(PlatformSettings).filter(PlatformSettings.id == 1).first()
    if not row:
        row = PlatformSettings(
            id=1,
            allowed_extensions=DEFAULT_EXTENSIONS,
            max_upload_bytes=DEFAULT_MAX_UPLOAD_BYTES,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
    elif row.allowed_extensions and isinstance(row.allowed_extensions[0], str):
        default_color_map = {e["ext"]: e["color"] for e in DEFAULT_EXTENSIONS}
        migrated = []
        for ext in row.allowed_extensions:
            migrated.append({"ext": ext, "color": default_color_map.get(ext, "#6b7280")})
        row.allowed_extensions = migrated
        db.commit()
        db.refresh(row)
    return row


@router.get("/settings")
async def get_platform_settings(
    user: CurrentUser = Depends(require_role(MASTER_ONLY_ROLES)),
    db: Session = Depends(get_db),
):
    """Get current platform settings (MASTER_ADMIN only)."""
    row = _get_or_create_settings(db)
    return {
        "allowed_extensions": row.allowed_extensions,
        "max_upload_bytes": row.max_upload_bytes,
        "max_upload_display": _format_bytes(row.max_upload_bytes),
        "updated_by": row.updated_by,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


class ExtensionEntry(BaseModel):
    ext: str
    color: str


class UpdateSettingsRequest(BaseModel):
    allowed_extensions: Optional[List[ExtensionEntry]] = None
    max_upload_bytes: Optional[int] = None


@router.put("/settings")
async def update_platform_settings(
    payload: UpdateSettingsRequest,
    request: Request,
    user: CurrentUser = Depends(require_role(MASTER_ONLY_ROLES)),
    db: Session = Depends(get_db),
):
    """Update platform settings (MASTER_ADMIN only)."""
    row = _get_or_create_settings(db)
    changes = {}

    if payload.allowed_extensions is not None:
        cleaned = []
        for entry in payload.allowed_extensions:
            ext = entry.ext.strip().lower()
            if not ext.startswith("."):
                ext = f".{ext}"
            color = entry.color.strip()
            if not re.fullmatch(r"#[0-9a-fA-F]{3}([0-9a-fA-F]{3})?", color):
                color = "#6b7280"
            cleaned.append({"ext": ext, "color": color})
        if not cleaned:
            raise HTTPException(status_code=422, detail="At least one extension is required")
        row.allowed_extensions = cleaned
        changes["allowed_extensions"] = cleaned

    if payload.max_upload_bytes is not None:
        if payload.max_upload_bytes < 1024 * 1024:  # min 1 MB
            raise HTTPException(status_code=422, detail="Max upload size must be at least 1 MB")
        if payload.max_upload_bytes > 50 * 1024 * 1024 * 1024:  # max 50 GB
            raise HTTPException(status_code=422, detail="Max upload size cannot exceed 50 GB")
        row.max_upload_bytes = payload.max_upload_bytes
        changes["max_upload_bytes"] = payload.max_upload_bytes

    row.updated_by = user.id
    db.commit()
    db.refresh(row)

    if changes:
        audit_log(
            user_id=user.id,
            event_type="ALLOWLIST_UPDATED",
            target_key="platform_settings",
            org_id=None,
            org_name=None,
            details=changes,
            request=request,
        )

    return {
        "allowed_extensions": row.allowed_extensions,
        "max_upload_bytes": row.max_upload_bytes,
        "max_upload_display": _format_bytes(row.max_upload_bytes),
        "updated_by": row.updated_by,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _format_bytes(size: int) -> str:
    if size >= 1024 * 1024 * 1024:
        return f"{size / (1024**3):.1f} GB"
    if size >= 1024 * 1024:
        return f"{size / (1024**2):.0f} MB"
    return f"{size / 1024:.0f} KB"
