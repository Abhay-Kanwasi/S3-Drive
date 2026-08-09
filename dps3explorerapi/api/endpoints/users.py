"""
User Management endpoints.

- GET  /admin/users/stats      — aggregate counts (total, admins, active, groups)
- GET  /admin/users/export     — CSV download (same filters as list)
- GET  /admin/users            — paginated, searchable user list
- GET  /admin/users/{user_id}  — single-user detail (uncapped groups/grants)
- POST /admin/users/{user_id}/deactivate — S3 Explorer–only deactivation (not UAM)
- POST /admin/users/{user_id}/reactivate — reverse S3 deactivation within 30-day grace

UAM deactivation (user_data.active) is read on every auth request; no polling.

Route ordering matters: /users/stats and /users/export must be registered
before /users/{user_id} to avoid FastAPI matching "stats"/"export" as a user_id.
"""

import csv
import io
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from core.config import settings
from core.audit import audit_log, audit_actor_fields
from core.auth import (
    CurrentUser,
    GLOBAL_ADMIN_ROLE_IDS,
    ROLE_LABELS,
    ROLE_MASTER_ADMIN,
    ROLE_SUPER_ADMIN,
    UAMSubscriber,
    UAMUser,
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
from db.models import FolderGrant, GroupMembership, Organization, S3UserDeactivation, UserGroup
from db.postgresdb import get_db

router = APIRouter()

ADMIN_ROLES = ["admin", "master_admin", "super_admin"]
REACTIVATE_ROLES = ["master_admin", "super_admin"]
DEACTIVATION_GRACE_DAYS = settings.DEACTIVATION_GRACE_DAYS


def _scope_query(db: Session, user: CurrentUser, org_id: Optional[int]):
    """Return a base UAMUser query scoped by the caller's role.

    Raises HTTPException(400) when an invalid org_id is supplied by a
    global admin. Organization-admin callers always ignore org_id — scoped to
    their own subscription unconditionally.
    """
    is_global = user.role_id in GLOBAL_ADMIN_ROLE_IDS
    q = db.query(UAMUser)
    if is_global:
        if org_id:
            org = db.query(Organization).filter(Organization.id == org_id, Organization.is_active == True).first()
            if not org:
                raise HTTPException(
                    status_code=400,
                    detail=f"Organization {org_id} not found or inactive.",
                )
            q = q.filter(UAMUser.subscription_id == org.subscription_id)
    else:
        q = q.filter(UAMUser.subscription_id == user.subscription_id)
    return q


def _enrich_users(db: Session, users: list) -> tuple:
    """Batch-load org names, groups, grants, and S3 deactivation flags."""
    if not users:
        return {}, {}, {}, {}, set()

    user_ids = [u.id for u in users]
    s3_deactivated_ids = s3_deactivated_user_ids(db, user_ids)
    sub_ids = list({u.subscription_id for u in users if u.subscription_id})

    org_map: dict[str, str] = {}
    if sub_ids:
        subs = (
            db.query(UAMSubscriber.subscription_id, UAMSubscriber.organization)
            .filter(UAMSubscriber.subscription_id.in_(sub_ids))
            .all()
        )
        org_map = {s.subscription_id: s.organization for s in subs}

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


def _resolve_org_for_subscription(db: Session, subscription_id: Optional[str]) -> tuple:
    """Return (org_id, org_name) for audit when target belongs to an onboarded org."""
    if not subscription_id:
        return None, None
    org = (
        db.query(Organization)
        .filter(Organization.subscription_id == subscription_id, Organization.is_active == True)
        .first()
    )
    if org:
        return org.id, org.org_name
    return None, None


def _assert_may_reactivate(
    actor: CurrentUser,
    target: UAMUser,
    db: Session,
) -> None:
    if not target.active:
        raise HTTPException(
            status_code=400,
            detail="User is deactivated in UAM; reactivate the account in UAM, not S3 Explorer.",
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


def _assert_may_deactivate(actor: CurrentUser, target: UAMUser, db: Session) -> None:
    if actor.id == target.id:
        raise HTTPException(status_code=400, detail="You cannot deactivate your own account.")
    if not target.active:
        raise HTTPException(
            status_code=400,
            detail="User is deactivated in UAM; cannot change S3 Explorer access.",
        )
    if is_s3_deactivated(db, target.id):
        raise HTTPException(
            status_code=400,
            detail="User is already deactivated in S3 Explorer.",
        )

    is_global = actor.role_id in GLOBAL_ADMIN_ROLE_IDS
    if not is_global:
        if target.subscription_id != actor.subscription_id:
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


def _status_label(u: UAMUser, s3_deactivated: bool) -> str:
    if not u.active:
        return "Inactive (UAM)"
    if s3_deactivated:
        return "Inactive (S3 Explorer)"
    return "Active"


def _build_user_row(
    u: UAMUser,
    org_name: Optional[str],
    groups: List[dict],
    grants: List[dict],
    s3_deactivated: bool,
) -> dict:
    uam_active = bool(u.active)
    s3_active = effective_s3_access(uam_active, s3_deactivated)
    return {
        "id": u.id,
        "user_name": u.user_name or "",
        "email": u.email or "",
        "role_id": u.role,
        "role_label": ROLE_LABELS.get(u.role, "user"),
        "subscription_id": u.subscription_id,
        "org_name": org_name,
        "active": s3_active,
        "uam_active": uam_active,
        "s3_deactivated": s3_deactivated,
        "groups": groups[:MAX_INLINE_GROUPS],
        "groups_total": len(groups),
        "folder_access": grants[:MAX_INLINE_GRANTS],
        "folder_access_total": len(grants),
    }


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
        base_q.filter(UAMUser.active == True)
        .outerjoin(S3UserDeactivation, UAMUser.id == S3UserDeactivation.user_id)
        .filter(S3UserDeactivation.user_id.is_(None))
        .count()
    )
    master_admins = base_q.filter(
        UAMUser.role.in_([ROLE_MASTER_ADMIN, ROLE_SUPER_ADMIN])
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
        org = db.query(Organization).filter(
            Organization.subscription_id == user.subscription_id, Organization.is_active == True
        ).first()
        groups_count = (
            db.query(func.count(UserGroup.id))
            .filter(UserGroup.org_id == org.id)
            .scalar() if org else 0
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
            or_(UAMUser.user_name.ilike(term), UAMUser.email.ilike(term))
        )

    users = base_q.order_by(UAMUser.user_name, UAMUser.id).all()
    org_map, groups_by_user, group_ids_by_user, grants_by_group, s3_deactivated_ids = (
        _enrich_users(db, users)
    )

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Name", "Email", "Organization", "Role", "Groups", "Folder Access", "Status"])

    for u in users:
        org_name = org_map.get(u.subscription_id, "")
        grps = ", ".join(g["name"] for g in groups_by_user.get(u.id, []))
        grants_list = _user_grants(u.id, group_ids_by_user, grants_by_group)
        access = "; ".join(f"{g['prefix']} ({g['access_level']})" for g in grants_list)
        writer.writerow([
            u.user_name or "",
            u.email or "",
            org_name,
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
    - Organization admins are hard-scoped to their own subscription (org_id ignored).
    """
    base_q = _scope_query(db, user, org_id)

    if q:
        term = f"%{q}%"
        base_q = base_q.filter(
            or_(UAMUser.user_name.ilike(term), UAMUser.email.ilike(term))
        )

    total = base_q.count()
    users = (
        base_q
        .order_by(UAMUser.user_name, UAMUser.id)
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
            org_name=org_map.get(u.subscription_id),
            groups=groups_by_user.get(u.id, []),
            grants=_user_grants(u.id, group_ids_by_user, grants_by_group),
            s3_deactivated=u.id in s3_deactivated_ids,
        )
        for u in users
    ]

    return {"results": results, "total": total, "page": page, "page_size": page_size}


@router.get("/users/{user_id}")
async def get_user_detail(
    user_id: int,
    user: CurrentUser = Depends(require_role(ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    """Full detail for a single user — uncapped groups and folder grants."""
    target = db.query(UAMUser).filter(UAMUser.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found.")

    is_global = user.role_id in GLOBAL_ADMIN_ROLE_IDS
    if not is_global and target.subscription_id != user.subscription_id:
        raise HTTPException(status_code=403, detail="User is outside your organization.")

    org_map, groups_by_user, group_ids_by_user, grants_by_group, s3_deactivated_ids = (
        _enrich_users(db, [target])
    )

    org_name = org_map.get(target.subscription_id)
    groups = groups_by_user.get(target.id, [])
    grants = _user_grants(target.id, group_ids_by_user, grants_by_group)
    s3_deactivated = target.id in s3_deactivated_ids
    uam_active = bool(target.active)

    return {
        "id": target.id,
        "user_name": target.user_name or "",
        "email": target.email or "",
        "role_id": target.role,
        "role_label": ROLE_LABELS.get(target.role, "user"),
        "subscription_id": target.subscription_id,
        "org_name": org_name,
        "active": effective_s3_access(uam_active, s3_deactivated),
        "uam_active": uam_active,
        "s3_deactivated": s3_deactivated,
        "groups": groups,
        "folder_access": grants,
    }


@router.post("/users/{user_id}/deactivate")
async def deactivate_user(
    user_id: int,
    request: Request,
    user: CurrentUser = Depends(require_role(ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    """
    Deactivate S3 Explorer access only (s3_user_deactivation row).
    Does not modify UAM user_data.active. Group memberships remain for 30 days.
    """
    target = db.query(UAMUser).filter(UAMUser.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found.")

    _assert_may_deactivate(user, target, db)

    deactivated_at = mark_s3_deactivated(db, target.id, user.id)

    org_id, org_name = _resolve_org_for_subscription(db, target.subscription_id)
    target_label = target.user_name or target.email or f"user_{target.id}"

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
            "target_user_name": target.user_name or "",
            "target_user_email": target.email or "",
            "deactivated_at": deactivated_at.isoformat(),
        },
        request=request,
    )
    db.commit()

    return {
        "id": target.id,
        "active": False,
        "uam_active": bool(target.active),
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
    Clears s3_user_deactivation only; does not change UAM user_data.active.
    """
    target = db.query(UAMUser).filter(UAMUser.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found.")

    org_id, org_name = _resolve_org_for_subscription(db, target.subscription_id)
    _assert_may_reactivate(user, target, db)

    clear_s3_deactivation(db, target.id)
    reactivated_at = datetime.now(timezone.utc)

    target_label = target.user_name or target.email or f"user_{target.id}"

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
            "target_user_name": target.user_name or "",
            "target_user_email": target.email or "",
            "reactivated_at": reactivated_at.isoformat(),
        },
        request=request,
    )
    db.commit()

    return {
        "id": target.id,
        "active": True,
        "uam_active": bool(target.active),
        "s3_deactivated": False,
        "reactivated_at": reactivated_at.isoformat(),
    }
