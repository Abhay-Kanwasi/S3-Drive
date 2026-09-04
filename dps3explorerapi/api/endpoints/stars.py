"""
Starred files and folders (per user, per org).

- GET    /stars?org_id=           — list (newest first)
- PUT    /stars                   — star (upsert)
- DELETE /stars?org_id=&key=      — unstar
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from api.endpoints.browse import _convert_size, _get_org_for_user
from core.auth import CurrentUser, get_current_user
from core.permissions import check_prefix_access, prefix_is_accessible
from core.s3 import get_s3_client
from db.models import Organization, StarredItem
from db.postgresdb import get_db

router = APIRouter()

STAR_LIMIT = 200
VALID_TYPES = {"file", "folder"}


class StarRequest(BaseModel):
    org_id: int
    key: str = Field(..., min_length=1)
    type: str
    name: str = Field(..., min_length=1, max_length=255)
    size: Optional[str] = None
    last_modified: Optional[str] = None


def _normalize_key(key: str, item_type: str) -> str:
    key = (key or "").strip()
    if not key:
        raise HTTPException(status_code=422, detail="key is required")
    if item_type == "folder" and not key.endswith("/"):
        key += "/"
    return key


def _item_dict(row: StarredItem, accessible: bool) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "type": row.item_type,
        "key": row.object_key,
        "accessible": accessible,
        "size": row.size,
        "last_modified": row.last_modified,
    }


def _clean_meta(value: Optional[str], max_len: int) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text == "--":
        return None
    return text[:max_len]


def _fill_file_meta_from_s3(row: StarredItem, org: Organization) -> bool:
    """Backfill size/date for files starred before metadata was stored."""
    if row.item_type != "file" or row.size:
        return False
    try:
        s3 = get_s3_client(region_name=org.region)
        head = s3.head_object(Bucket=org.bucket_name, Key=row.object_key)
        row.size = _convert_size(int(head.get("ContentLength") or 0))
        lm = head.get("LastModified")
        if lm:
            row.last_modified = lm.strftime("%B %d, %Y")
        return True
    except Exception:
        return False


@router.get("")
async def list_stars(
    org_id: int = Query(...),
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    org = _get_org_for_user(org_id, user, db)
    rows = (
        db.query(StarredItem)
        .filter(StarredItem.user_id == user.id, StarredItem.org_id == org.id)
        .order_by(StarredItem.created_at.desc())
        .all()
    )
    dirty = False
    items = []
    for row in rows:
        if _fill_file_meta_from_s3(row, org):
            dirty = True
        items.append(_item_dict(row, prefix_is_accessible(user, org.id, row.object_key, db)))
    if dirty:
        db.commit()
    return {"items": items}


@router.put("")
async def star_item(
    payload: StarRequest,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    item_type = (payload.type or "").strip().lower()
    if item_type not in VALID_TYPES:
        raise HTTPException(status_code=400, detail="type must be 'file' or 'folder'")

    org = _get_org_for_user(payload.org_id, user, db)
    key = _normalize_key(payload.key, item_type)
    name = payload.name.strip()
    size = _clean_meta(payload.size, 32)
    last_modified = _clean_meta(payload.last_modified, 64)
    check_prefix_access(user, org.id, key, db, require_write=False)

    existing = (
        db.query(StarredItem)
        .filter(
            StarredItem.user_id == user.id,
            StarredItem.org_id == org.id,
            StarredItem.object_key == key,
        )
        .first()
    )
    if existing:
        existing.name = name
        existing.item_type = item_type
        if size:
            existing.size = size
        if last_modified:
            existing.last_modified = last_modified
        db.commit()
        return {"starred": True}

    count = (
        db.query(StarredItem)
        .filter(StarredItem.user_id == user.id, StarredItem.org_id == org.id)
        .count()
    )
    if count >= STAR_LIMIT:
        raise HTTPException(
            status_code=400,
            detail=f"Star limit reached ({STAR_LIMIT}/{STAR_LIMIT}). Unstar some items first.",
        )

    db.add(StarredItem(
        user_id=user.id,
        org_id=org.id,
        object_key=key,
        item_type=item_type,
        name=name,
        size=size,
        last_modified=last_modified,
    ))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
    return {"starred": True}


@router.delete("")
async def unstar_item(
    org_id: int = Query(...),
    key: str = Query(...),
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    org = _get_org_for_user(org_id, user, db)
    raw = (key or "").strip()
    if not raw:
        raise HTTPException(status_code=422, detail="key is required")
    candidates = {raw}
    if raw.endswith("/"):
        candidates.add(raw.rstrip("/"))
    else:
        candidates.add(raw + "/")

    row = (
        db.query(StarredItem)
        .filter(
            StarredItem.user_id == user.id,
            StarredItem.org_id == org.id,
            StarredItem.object_key.in_(candidates),
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Starred item not found")
    db.delete(row)
    db.commit()
    return {"starred": False}
