"""
User Management endpoints.

- GET    /admin/users/stats
- GET    /admin/users/export
- GET    /admin/users
- POST   /admin/users                 — create user
- GET    /admin/users/{user_id}
- PATCH  /admin/users/{user_id}       — edit username/email/role/organization
- POST   /admin/users/{user_id}/deactivate           — S3 Explorer deactivation
- POST   /admin/users/{user_id}/reactivate           — S3 Explorer reactivation
- POST   /admin/users/{user_id}/account/deactivate   — users.active = false
- POST   /admin/users/{user_id}/account/reactivate   — users.active = true

Route ordering matters: /users/stats and /users/export must be registered
before /users/{user_id}.
"""

import csv
import io
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from core.config import settings
from core.audit import audit_log, audit_actor_fields
from core.auth import (
    CurrentUser,
    GLOBAL_ADMIN_ROLE_IDS,
    ROLE_ADMIN,
    ROLE_LABELS,
    ROLE_MASTER_ADMIN,
    ROLE_SUPER_ADMIN,
    ROLE_USER,
    require_role,
)
from core.user_access import (
    clear_s3_deactivation,
    effective_s3_access,
    get_s3_deactivated_at,
    is_s3_deactivated,
    mark_s3_deactivated,
    s3_deactivated_user_ids,
)
from db.models import FolderGrant, GroupMembership, Organization, S3UserDeactivation, User, UserGroup
from db.postgresdb import get_db

router = APIRouter()

ADMIN_ROLES = ["admin", "master_admin", "super_admin"]
GLOBAL_ADMIN_ROLES = ["master_admin", "super_admin"]
REACTIVATE_ROLES = ["master_admin", "super_admin"]
DEACTIVATION_GRACE_DAYS = settings.DEACTIVATION_GRACE_DAYS
VALID_ROLES = {ROLE_ADMIN, ROLE_USER, ROLE_MASTER_ADMIN, ROLE_SUPER_ADMIN}


class UserCreateRequest(BaseModel):
    username: str = Field(..., min_length=1)
    email: str = Field(..., min_length=1)
    role: int = ROLE_USER
    organization_id: Optional[int] = None
    active: bool = True


class UserUpdateRequest(BaseModel):
    username: Optional[str] = None
    email: Optional[str] = None
    role: Optional[int] = None
    organization_id: Optional[int] = None


def _target_org_key(db: Session, target: User) -> Optional[str]:
    if not target.organization_id:
        return None
    org = db.query(Organization.org_key).filter(Organization.id == target.organization_id).first()
    return org[0] if org else None


def _scope_query(db: Session, user: CurrentUser, org_id: Optional[int]):
    """Return a base User query scoped by the caller's role."""
    is_global = user.role_id in GLOBAL_ADMIN_ROLE_IDS
    q = db.query(User)
    if is_global:
        if org_id:
            org = db.query(Organization).filter(Organization.id == org_id, Organization.is_active == True).first()
            if not org:
                raise HTTPException(
                    status_code=400,
                    detail=f"Organization {org_id} not found or inactive.",
                )
            q = q.filter(User.organization_id == org.id)
    else:
        if not user.organization_id:
            raise HTTPException(status_code=403, detail="No organization scoped for your account.")
        q = q.filter(User.organization_id == user.organization_id)
    return q


def _enrich_users(db: Session, users: list) -> tuple:
    """Batch-load org names, groups, grants, and S3 deactivation flags."""
    if not users:
        return {}, {}, {}, {}, set()

    user_ids = [u.id for u in users]
    s3_deactivated_ids = s3_deactivated_user_ids(db, user_ids)
    org_ids = list({u.organization_id for u in users if u.organization_id})

    org_map: dict[int, dict] = {}
    if org_ids:
        orgs = (
            db.query(Organization.id, Organization.org_name, Organization.org_key)
            .filter(Organization.id.in_(org_ids))
            .all()
        )
        org_map = {o.id: {"org_name": o.org_name, "org_key": o.org_key} for o in orgs}

    memberships = (
        db.query(GroupMembership.user_id, UserGroup.id, UserGroup.name)
        .join(UserGroup, GroupMembership.group_id == UserGroup.id)
        .filter(GroupMembership.user_id.in_(user_ids))
        .all()
    )
    groups_by_user: dict[int, list] = {}
    group_ids_by_user: dict[int, set] = {}
    for m in memberships:
        groups_by_user.setdefault(m.user_id, []).append({"id": m[1], "name": m[2]})
        group_ids_by_user.setdefault(m.user_id, set()).add(m[1])

    all_group_ids = set()
    for gids in group_ids_by_user.values():
        all_group_ids.update(gids)

    grants_by_group: dict[int, list] = {}
    if all_group_ids:
        grants = (
            db.query(FolderGrant.group_id, FolderGrant.prefix, FolderGrant.access_level)
            .filter(FolderGrant.group_id.in_(all_group_ids))
            .all()
        )
        for g in grants:
            grants_by_group.setdefault(g.group_id, []).append(
                {"prefix": g.prefix, "access_level": g.access_level}
            )

    return org_map, groups_by_user, group_ids_by_user, grants_by_group, s3_deactivated_ids


def _resolve_org_for_user(db: Session, target: User) -> tuple:
    """Return (org_id, org_name) for audit."""
    if not target.organization_id:
        return None, None
    org = (
        db.query(Organization)
        .filter(Organization.id == target.organization_id, Organization.is_active == True)
        .first()
    )
    if org:
        return org.id, org.org_name
    return target.organization_id, None


def _assert_may_reactivate(
    actor: CurrentUser,
    target: User,
    db: Session,
) -> None:
    if not target.active:
        raise HTTPException(
            status_code=400,
            detail="User account is deactivated; reactivate the account first, not S3 Explorer.",
        )

    deactivated_at = get_s3_deactivated_at(db, target.id)
    if deactivated_at is None:
        raise HTTPException(
            status_code=400,
            detail="User is not deactivated in S3 Explorer.",
        )

    if actor.role_id not in GLOBAL_ADMIN_ROLE_IDS:
        raise HTTPException(
            status_code=403,
            detail="Only master or super admins can reactivate users.",
        )

    if target.role == ROLE_SUPER_ADMIN and actor.role_id != ROLE_SUPER_ADMIN:
        raise HTTPException(
            status_code=403,
            detail="Only a super admin can reactivate a super admin.",
        )

    cutoff = datetime.now(timezone.utc) - timedelta(days=DEACTIVATION_GRACE_DAYS)
    if deactivated_at < cutoff:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Reactivation window expired ({DEACTIVATION_GRACE_DAYS} days "
                "since deactivation)."
            ),
        )


def _assert_may_deactivate(actor: CurrentUser, target: User, db: Session) -> None:
    if actor.id == target.id:
        raise HTTPException(status_code=400, detail="You cannot deactivate your own account.")
    if not target.active:
        raise HTTPException(
            status_code=400,
            detail="User account is deactivated; cannot change S3 Explorer access.",
        )
    if is_s3_deactivated(db, target.id):
        raise HTTPException(
            status_code=400,
            detail="User is already deactivated in S3 Explorer.",
        )

    is_global = actor.role_id in GLOBAL_ADMIN_ROLE_IDS
    if not is_global:
        if target.organization_id != actor.organization_id:
            raise HTTPException(status_code=403, detail="User is outside your organization.")
        if target.role in GLOBAL_ADMIN_ROLE_IDS:
            raise HTTPException(
                status_code=403,
                detail="You cannot deactivate a global administrator.",
            )

    if target.role == ROLE_SUPER_ADMIN and actor.role_id != ROLE_SUPER_ADMIN:
        raise HTTPException(
            status_code=403,
            detail="Only a super admin can deactivate a super admin.",
        )


def _assert_may_manage_account(actor: CurrentUser, target: User) -> None:
    if actor.role_id not in GLOBAL_ADMIN_ROLE_IDS:
        raise HTTPException(status_code=403, detail="Only master or super admins can manage accounts.")
    if actor.id == target.id:
        raise HTTPException(status_code=400, detail="You cannot change your own account status.")
    if target.role == ROLE_SUPER_ADMIN and actor.role_id != ROLE_SUPER_ADMIN:
        raise HTTPException(
            status_code=403,
            detail="Only a super admin can change a super admin account.",
        )


def _user_grants(uid: int, group_ids_by_user: dict, grants_by_group: dict) -> list:
    seen = set()
    result = []
    for gid in group_ids_by_user.get(uid, set()):
        for grant in grants_by_group.get(gid, []):
            key = (grant["prefix"], grant["access_level"])
            if key not in seen:
                seen.add(key)
                result.append(grant)
    return result


MAX_INLINE_GROUPS = 5
MAX_INLINE_GRANTS = 5


def _status_label(u: User, s3_deactivated: bool) -> str:
    if not u.active:
        return "Inactive (account)"
    if s3_deactivated:
        return "Inactive (S3 Explorer)"
    return "Active"


def _build_user_row(
    u: User,
    org_info: Optional[dict],
    groups: List[dict],
    grants: List[dict],
    s3_deactivated: bool,
) -> dict:
    account_active = bool(u.active)
    s3_active = effective_s3_access(account_active, s3_deactivated)
    org_key = (org_info or {}).get("org_key")
    return {
        "id": u.id,
        "user_name": u.username or "",
        "username": u.username or "",
        "email": u.email or "",
        "role_id": u.role,
        "role_label": ROLE_LABELS.get(u.role, "user"),
        "organization_id": u.organization_id,
        "org_key": org_key,
        "subscription_id": org_key,
        "org_name": (org_info or {}).get("org_name"),
        "active": s3_active,
        "account_active": account_active,
        "s3_deactivated": s3_deactivated,
        "groups": groups[:MAX_INLINE_GROUPS],
        "groups_total": len(groups),
        "folder_access": grants[:MAX_INLINE_GRANTS],
        "folder_access_total": len(grants),
    }


def _validate_role_change(actor: CurrentUser, new_role: int) -> None:
    if new_role not in VALID_ROLES:
        raise HTTPException(status_code=422, detail=f"Invalid role. Allowed: {sorted(VALID_ROLES)}")
    if new_role in GLOBAL_ADMIN_ROLE_IDS and actor.role_id not in GLOBAL_ADMIN_ROLE_IDS:
        raise HTTPException(status_code=403, detail="Only global admins can assign global roles.")
    if new_role == ROLE_SUPER_ADMIN and actor.role_id != ROLE_SUPER_ADMIN:
        raise HTTPException(status_code=403, detail="Only a super admin can assign super_admin.")


def _role_requires_organization(role: int) -> bool:
    """Org-scoped roles (admin/user) must belong to an organization."""
    return role in {ROLE_ADMIN, ROLE_USER}


def _validate_organization_id(db: Session, organization_id: Optional[int]) -> Optional[Organization]:
    if organization_id is None:
        return None
    org = db.query(Organization).filter(Organization.id == organization_id, Organization.is_active == True).first()
    if not org:
        raise HTTPException(status_code=400, detail=f"Organization {organization_id} not found or inactive.")
    return org


def _assert_org_matches_role(role: int, organization_id: Optional[int]) -> None:
    if _role_requires_organization(role) and organization_id is None:
        raise HTTPException(
            status_code=422,
            detail="organization_id is required for admin and user roles",
        )


@router.get("/users/stats")
async def user_stats(
    org_id: Optional[int] = Query(None),
    user: CurrentUser = Depends(require_role(ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    """Aggregate counts for the stats strip."""
    base_q = _scope_query(db, user, org_id)

    total = base_q.count()
    active = (
        base_q.filter(User.active == True)
        .outerjoin(S3UserDeactivation, User.id == S3UserDeactivation.user_id)
        .filter(S3UserDeactivation.user_id.is_(None))
        .count()
    )
    master_admins = base_q.filter(
        User.role.in_([ROLE_MASTER_ADMIN, ROLE_SUPER_ADMIN])
    ).count()

    is_global = user.role_id in GLOBAL_ADMIN_ROLE_IDS
    if is_global and not org_id:
        groups_count = db.query(func.count(UserGroup.id)).scalar() or 0
    elif org_id:
        groups_count = (
            db.query(func.count(UserGroup.id))
            .filter(UserGroup.org_id == org_id)
            .scalar() or 0
        )
    else:
        groups_count = (
            db.query(func.count(UserGroup.id))
            .filter(UserGroup.org_id == user.organization_id)
            .scalar() if user.organization_id else 0
        )

    return {
        "total_users": total,
        "master_admins": master_admins,
        "active": active,
        "groups": groups_count,
    }


@router.get("/users/export")
async def export_users_csv(
    request: Request,
    q: str = Query(""),
    org_id: Optional[int] = Query(None),
    user: CurrentUser = Depends(require_role(ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    """Stream all matching users as CSV (no pagination)."""
    base_q = _scope_query(db, user, org_id)

    if q:
        term = f"%{q}%"
        base_q = base_q.filter(
            or_(User.username.ilike(term), User.email.ilike(term))
        )

    users = base_q.order_by(User.username, User.id).all()
    org_map, groups_by_user, group_ids_by_user, grants_by_group, s3_deactivated_ids = (
        _enrich_users(db, users)
    )

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Name", "Email", "Organization", "Role", "Groups", "Folder Access", "Status"])

    for u in users:
        org_info = org_map.get(u.organization_id) or {}
        grps = ", ".join(g["name"] for g in groups_by_user.get(u.id, []))
        grants_list = _user_grants(u.id, group_ids_by_user, grants_by_group)
        access = "; ".join(f"{g['prefix']} ({g['access_level']})" for g in grants_list)
        writer.writerow([
            u.username or "",
            u.email or "",
            org_info.get("org_name", ""),
            ROLE_LABELS.get(u.role, "user"),
            grps,
            access,
            _status_label(u, u.id in s3_deactivated_ids),
        ])

    buf.seek(0)

    audit_log(
        user_id=user.id,
        event_type="USERS_EXPORTED",
        target_key="users_export.csv",
        org_id=org_id,
        org_name=None,
        details={"row_count": len(users), "search": q or None, "org_id_filter": org_id},
        request=request,
    )

    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=users_export.csv"},
    )


@router.get("/users")
async def list_users(
    q: str = Query("", description="Search by name or email"),
    org_id: Optional[int] = Query(None, description="Filter by onboarded org"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    user: CurrentUser = Depends(require_role(ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    """
    Paginated user list for admin panel.

    - Global admins see all users across all orgs. Optional org_id filter.
    - Organization admins are hard-scoped to their own organization (org_id ignored).
    """
    base_q = _scope_query(db, user, org_id)

    if q:
        term = f"%{q}%"
        base_q = base_q.filter(
            or_(User.username.ilike(term), User.email.ilike(term))
        )

    total = base_q.count()
    users = (
        base_q
        .order_by(User.username, User.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    if not users:
        return {"results": [], "total": total, "page": page, "page_size": page_size}

    org_map, groups_by_user, group_ids_by_user, grants_by_group, s3_deactivated_ids = (
        _enrich_users(db, users)
    )

    results = [
        _build_user_row(
            u,
            org_info=org_map.get(u.organization_id),
            groups=groups_by_user.get(u.id, []),
            grants=_user_grants(u.id, group_ids_by_user, grants_by_group),
            s3_deactivated=u.id in s3_deactivated_ids,
        )
        for u in users
    ]

    return {"results": results, "total": total, "page": page, "page_size": page_size}


@router.post("/users", status_code=201)
async def create_user(
    payload: UserCreateRequest,
    request: Request,
    user: CurrentUser = Depends(require_role(GLOBAL_ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    """Create an owned user (global admins only)."""
    username = payload.username.strip()
    email = payload.email.strip().lower()
    if not username or not email:
        raise HTTPException(status_code=422, detail="username and email are required")

    _validate_role_change(user, payload.role)
    org = _validate_organization_id(db, payload.organization_id)
    _assert_org_matches_role(payload.role, org.id if org else None)

    existing = db.query(User).filter(User.email == email).first()
    if existing:
        raise HTTPException(status_code=409, detail="A user with this email already exists.")

    row = User(
        username=username,
        email=email,
        role=payload.role,
        organization_id=org.id if org else None,
        active=bool(payload.active),
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    audit_log(
        **audit_actor_fields(user),
        event_type="USER_CREATED",
        target_key=f"usr_{row.id}",
        org_id=row.organization_id,
        org_name=org.org_name if org else None,
        details={
            "summary": f"{user.user_name or user.email} created user {username}",
            "target_user_id": row.id,
            "email": email,
            "role": payload.role,
            "organization_id": row.organization_id,
        },
        request=request,
    )

    org_map, groups_by_user, group_ids_by_user, grants_by_group, s3_deactivated_ids = (
        _enrich_users(db, [row])
    )
    return _build_user_row(
        row,
        org_info=org_map.get(row.organization_id),
        groups=groups_by_user.get(row.id, []),
        grants=_user_grants(row.id, group_ids_by_user, grants_by_group),
        s3_deactivated=row.id in s3_deactivated_ids,
    )


@router.get("/users/{user_id}")
async def get_user_detail(
    user_id: int,
    user: CurrentUser = Depends(require_role(ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    """Full detail for a single user — uncapped groups and folder grants."""
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found.")

    is_global = user.role_id in GLOBAL_ADMIN_ROLE_IDS
    if not is_global and target.organization_id != user.organization_id:
        raise HTTPException(status_code=403, detail="User is outside your organization.")

    org_map, groups_by_user, group_ids_by_user, grants_by_group, s3_deactivated_ids = (
        _enrich_users(db, [target])
    )

    org_info = org_map.get(target.organization_id) or {}
    groups = groups_by_user.get(target.id, [])
    grants = _user_grants(target.id, group_ids_by_user, grants_by_group)
    s3_deactivated = target.id in s3_deactivated_ids
    account_active = bool(target.active)
    org_key = org_info.get("org_key") or _target_org_key(db, target)

    return {
        "id": target.id,
        "user_name": target.username or "",
        "username": target.username or "",
        "email": target.email or "",
        "role_id": target.role,
        "role_label": ROLE_LABELS.get(target.role, "user"),
        "organization_id": target.organization_id,
        "org_key": org_key,
        "subscription_id": org_key,
        "org_name": org_info.get("org_name"),
        "active": effective_s3_access(account_active, s3_deactivated),
        "account_active": account_active,
        "s3_deactivated": s3_deactivated,
        "groups": groups,
        "folder_access": grants,
    }


@router.patch("/users/{user_id}")
async def update_user(
    user_id: int,
    payload: UserUpdateRequest,
    request: Request,
    user: CurrentUser = Depends(require_role(GLOBAL_ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    """Edit username/email/role/organization_id (global admins only)."""
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found.")

    changes = {}

    if payload.username is not None:
        username = payload.username.strip()
        if not username:
            raise HTTPException(status_code=422, detail="username cannot be empty")
        if username != target.username:
            target.username = username
            changes["username"] = username

    if payload.email is not None:
        email = payload.email.strip().lower()
        if not email:
            raise HTTPException(status_code=422, detail="email cannot be empty")
        if email != (target.email or "").lower():
            clash = db.query(User).filter(User.email == email, User.id != target.id).first()
            if clash:
                raise HTTPException(status_code=409, detail="A user with this email already exists.")
            target.email = email
            changes["email"] = email

    if payload.role is not None:
        _validate_role_change(user, payload.role)
        if target.role == ROLE_SUPER_ADMIN and user.role_id != ROLE_SUPER_ADMIN:
            raise HTTPException(status_code=403, detail="Only a super admin can edit a super admin.")
        if payload.role != target.role:
            target.role = payload.role
            changes["role"] = payload.role

    # Allow explicit null via organization_id=null when the field was provided.
    fields_set = getattr(payload, "model_fields_set", set())
    if "organization_id" in fields_set:
        org = _validate_organization_id(db, payload.organization_id)
        new_org_id = org.id if org else None
        if new_org_id != target.organization_id:
            target.organization_id = new_org_id
            changes["organization_id"] = new_org_id

    if not changes:
        raise HTTPException(status_code=400, detail="No changes provided.")

    # Validate final state: org-scoped roles must keep an organization.
    _assert_org_matches_role(int(target.role or ROLE_USER), target.organization_id)

    db.commit()
    db.refresh(target)

    org_id, org_name = _resolve_org_for_user(db, target)
    audit_log(
        **audit_actor_fields(user),
        event_type="USER_UPDATED",
        target_key=f"usr_{target.id}",
        org_id=org_id,
        org_name=org_name,
        details={
            "summary": f"{user.user_name or user.email} updated user {target.username}",
            "target_user_id": target.id,
            "changes": changes,
        },
        request=request,
    )

    org_map, groups_by_user, group_ids_by_user, grants_by_group, s3_deactivated_ids = (
        _enrich_users(db, [target])
    )
    return _build_user_row(
        target,
        org_info=org_map.get(target.organization_id),
        groups=groups_by_user.get(target.id, []),
        grants=_user_grants(target.id, group_ids_by_user, grants_by_group),
        s3_deactivated=target.id in s3_deactivated_ids,
    )


@router.post("/users/{user_id}/deactivate")
async def deactivate_user(
    user_id: int,
    request: Request,
    user: CurrentUser = Depends(require_role(ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    """
    Deactivate S3 Explorer access only (s3_user_deactivation row).
    Does not modify users.active. Group memberships remain for 30 days.
    """
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found.")

    _assert_may_deactivate(user, target, db)

    deactivated_at = mark_s3_deactivated(db, target.id, user.id)

    org_id, org_name = _resolve_org_for_user(db, target)
    target_label = target.username or target.email or f"user_{target.id}"

    audit_log(
        **audit_actor_fields(user),
        event_type="USER_DEACTIVATED",
        target_key=f"usr_{target.id}",
        org_id=org_id,
        org_name=org_name,
        details={
            "summary": f"{user.user_name or user.email} deactivated {target_label} in S3 Explorer",
            "scope": "s3_explorer",
            "target_user_id": target.id,
            "target_user_name": target.username or "",
            "target_user_email": target.email or "",
            "deactivated_at": deactivated_at.isoformat(),
        },
        request=request,
    )
    db.commit()

    return {
        "id": target.id,
        "active": False,
        "account_active": bool(target.active),
        "s3_deactivated": True,
        "deactivated_at": deactivated_at.isoformat(),
    }


@router.post("/users/{user_id}/reactivate")
async def reactivate_user(
    user_id: int,
    request: Request,
    user: CurrentUser = Depends(require_role(REACTIVATE_ROLES)),
    db: Session = Depends(get_db),
):
    """
    Restore S3 Explorer access within the 30-day grace period.
    Clears s3_user_deactivation only; does not change users.active.
    """
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found.")

    org_id, org_name = _resolve_org_for_user(db, target)
    _assert_may_reactivate(user, target, db)

    clear_s3_deactivation(db, target.id)
    reactivated_at = datetime.now(timezone.utc)

    target_label = target.username or target.email or f"user_{target.id}"

    audit_log(
        **audit_actor_fields(user),
        event_type="USER_REACTIVATED",
        target_key=f"usr_{target.id}",
        org_id=org_id,
        org_name=org_name,
        details={
            "summary": f"{user.user_name or user.email} reactivated {target_label} in S3 Explorer",
            "scope": "s3_explorer",
            "target_user_id": target.id,
            "target_user_name": target.username or "",
            "target_user_email": target.email or "",
            "reactivated_at": reactivated_at.isoformat(),
        },
        request=request,
    )
    db.commit()

    return {
        "id": target.id,
        "active": True,
        "account_active": bool(target.active),
        "s3_deactivated": False,
        "reactivated_at": reactivated_at.isoformat(),
    }


@router.post("/users/{user_id}/account/deactivate")
async def deactivate_account(
    user_id: int,
    request: Request,
    user: CurrentUser = Depends(require_role(GLOBAL_ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    """Account-level deactivate (users.active = false). Global admins only."""
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found.")
    _assert_may_manage_account(user, target)
    if not target.active:
        raise HTTPException(status_code=400, detail="User account is already deactivated.")

    target.active = False
    org_id, org_name = _resolve_org_for_user(db, target)
    target_label = target.username or target.email or f"user_{target.id}"

    audit_log(
        **audit_actor_fields(user),
        event_type="USER_ACCOUNT_DEACTIVATED",
        target_key=f"usr_{target.id}",
        org_id=org_id,
        org_name=org_name,
        details={
            "summary": f"{user.user_name or user.email} deactivated account for {target_label}",
            "scope": "account",
            "target_user_id": target.id,
        },
        request=request,
    )
    db.commit()
    return {
        "id": target.id,
        "account_active": False,
        "s3_deactivated": is_s3_deactivated(db, target.id),
    }


@router.post("/users/{user_id}/account/reactivate")
async def reactivate_account(
    user_id: int,
    request: Request,
    user: CurrentUser = Depends(require_role(GLOBAL_ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    """Account-level reactivate (users.active = true). Global admins only."""
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found.")
    _assert_may_manage_account(user, target)
    if target.active:
        raise HTTPException(status_code=400, detail="User account is already active.")

    target.active = True
    org_id, org_name = _resolve_org_for_user(db, target)
    target_label = target.username or target.email or f"user_{target.id}"

    audit_log(
        **audit_actor_fields(user),
        event_type="USER_ACCOUNT_REACTIVATED",
        target_key=f"usr_{target.id}",
        org_id=org_id,
        org_name=org_name,
        details={
            "summary": f"{user.user_name or user.email} reactivated account for {target_label}",
            "scope": "account",
            "target_user_id": target.id,
        },
        request=request,
    )
    db.commit()
    return {
        "id": target.id,
        "account_active": True,
        "s3_deactivated": is_s3_deactivated(db, target.id),
    }
