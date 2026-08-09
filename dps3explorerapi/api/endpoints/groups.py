"""
Group Management endpoints (Phase 3).

- POST   /admin/groups                  — create group
- GET    /admin/groups?org_id=          — list groups for org
- GET    /admin/groups/{id}             — get group detail
- PUT    /admin/groups/{id}             — rename group
- DELETE /admin/groups/{id}             — delete group
- POST   /admin/groups/{id}/members     — add members
- DELETE /admin/groups/{id}/members/{uid} — remove member
- GET    /admin/groups/{id}/members     — list members
- POST   /admin/groups/{id}/grants      — create folder grant
- DELETE /admin/groups/{id}/grants/{gid} — remove folder grant
- GET    /admin/groups/{id}/grants      — list grants
- GET    /admin/orgs/{id}/users         — search org users (for member picker)
- GET    /admin/orgs/{id}/folder-tree   — list S3 folders (for folder picker)
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

import logging

from core.audit import audit_log, audit_actor_fields
from core.auth import (
    CurrentUser, get_current_user, require_role,
    GLOBAL_ADMIN_ROLE_IDS,
)
from core.s3 import get_s3_client
from db.postgresdb import get_db, Session as DBSession
from db.models import Organization, User, UserGroup, GroupMembership, FolderGrant, UserNotification

logger = logging.getLogger(__name__)

router = APIRouter()

GROUP_ADMIN_ROLES = ["admin", "master_admin", "super_admin"]


# ----------------------------- Helpers ------------------------------------

def _get_org_for_admin(org_id: int, user: CurrentUser, db: Session) -> Organization:
    """Verify the org exists, is active, and the admin has access."""
    org = db.query(Organization).filter(Organization.id == org_id, Organization.is_active == True).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    if user.role_id not in GLOBAL_ADMIN_ROLE_IDS:
        if user.organization_id != org.id and user.subscription_id != org.org_key:
            raise HTTPException(status_code=403, detail="No access to this organization")
    return org


def _get_group(group_id: int, user: CurrentUser, db: Session) -> UserGroup:
    """Fetch group and verify admin has access to its org."""
    group = db.query(UserGroup).filter(UserGroup.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    _get_org_for_admin(group.org_id, user, db)
    return group


NOTIF_CAP = 50


def _send_notifications(user_ids: list, org_id: int, org_name: str, grants: list):
    """Bulk-insert notifications in an isolated session. Runs inline (~20-30ms typical).
    Never raises — logs errors and returns silently."""
    if not user_ids or not grants:
        return
    try:
        notif_db = DBSession()
        try:
            rows = []
            for uid in user_ids:
                for grant in grants:
                    rows.append(UserNotification(
                        user_id=uid,
                        org_id=org_id,
                        type="folder_access",
                        title="New folder access granted",
                        message=f"You now have {grant.access_level} access to '{grant.prefix}' in {org_name}",
                    ))
            # add_all (not bulk_save_objects) so Identity/PK defaults and ORM
            # events fire — required for SQLite test Identity polyfill and Postgres.
            notif_db.add_all(rows)
            notif_db.flush()
            for uid in user_ids:
                count = notif_db.query(UserNotification).filter_by(user_id=uid).count()
                if count > NOTIF_CAP:
                    oldest = (
                        notif_db.query(UserNotification)
                        .filter_by(user_id=uid)
                        .order_by(UserNotification.created_at.asc())
                        .limit(count - NOTIF_CAP)
                        .all()
                    )
                    for n in oldest:
                        notif_db.delete(n)
            notif_db.commit()
        except Exception:
            notif_db.rollback()
            logger.error("Failed to create notifications", exc_info=True)
        finally:
            notif_db.close()
    except Exception:
        logger.error("Notification session creation failed", exc_info=True)


def _audit_folder_access_notified(
    actor: CurrentUser,
    org,
    recipient_ids: list,
    grants: list,
    request: Request,
) -> None:
    """Audit in-app notifications sent for folder access (admin action)."""
    if not recipient_ids or not grants:
        return
    prefixes = [g.prefix for g in grants]
    audit_log(
        event_type="FOLDER_ACCESS_NOTIFIED",
        target_key=f"org:{org.id}",
        org_id=org.id,
        org_name=org.org_name,
        details={
            "summary": (
                f"{actor.user_name or 'Admin'} notified {len(recipient_ids)} user(s) "
                f"about access to {', '.join(prefixes)}"
            ),
            "recipient_user_ids": recipient_ids,
            "grant_prefixes": prefixes,
            "access_levels": [g.access_level for g in grants],
            "notification_count": len(recipient_ids) * len(grants),
        },
        request=request,
        **audit_actor_fields(actor),
    )


# ----------------------------- Schemas ------------------------------------

class GroupCreateRequest(BaseModel):
    org_id: int
    name: str
    member_user_ids: List[int] = []

    @field_validator("name")
    @classmethod
    def validate_name(cls, v):
        v = v.strip()
        if not v:
            raise ValueError("Group name cannot be empty")
        if len(v) > 200:
            raise ValueError("Group name too long (max 200 chars)")
        return v


class GroupUpdateRequest(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def validate_name(cls, v):
        v = v.strip()
        if not v:
            raise ValueError("Group name cannot be empty")
        if len(v) > 200:
            raise ValueError("Group name too long (max 200 chars)")
        return v


class AddMembersRequest(BaseModel):
    user_ids: List[int]


class CreateGrantRequest(BaseModel):
    prefix: str
    access_level: str = "read"

    @field_validator("access_level")
    @classmethod
    def validate_access(cls, v):
        if v not in ("read", "read_write"):
            raise ValueError("access_level must be 'read' or 'read_write'")
        return v

    @field_validator("prefix")
    @classmethod
    def validate_prefix(cls, v):
        v = v.strip()
        if not v:
            raise ValueError("Prefix cannot be empty")
        if not v.endswith("/"):
            v += "/"
        return v


class GroupOut(BaseModel):
    id: int
    org_id: int
    name: str
    member_count: int = 0
    grant_count: int = 0
    requires_delete_approval: bool = False
    created_at: Optional[str] = None

    class Config:
        from_attributes = True


class MemberOut(BaseModel):
    id: int
    user_id: int
    user_name: Optional[str] = None
    email: Optional[str] = None
    added_at: Optional[str] = None


class GrantOut(BaseModel):
    id: int
    prefix: str
    access_level: str
    created_at: Optional[str] = None


class GroupDetailOut(BaseModel):
    id: int
    org_id: int
    org_name: Optional[str] = None
    name: str
    member_count: int = 0
    grant_count: int = 0
    requires_delete_approval: bool = False
    members: List[MemberOut] = []
    grants: List[GrantOut] = []
    created_at: Optional[str] = None


# ----------------------------- Group CRUD ---------------------------------

@router.post("/groups", response_model=GroupOut, status_code=201)
async def create_group(
    payload: GroupCreateRequest,
    request: Request,
    user: CurrentUser = Depends(require_role(GROUP_ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    org = _get_org_for_admin(payload.org_id, user, db)

    full_name = payload.name.strip()

    existing = db.query(UserGroup).filter(
        UserGroup.org_id == org.id, UserGroup.name == full_name,
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"Group '{full_name}' already exists in this org")

    group = UserGroup(org_id=org.id, name=full_name, created_by=user.id)
    db.add(group)
    db.flush()

    added_count = 0
    if payload.member_user_ids:
        unique_ids = list(dict.fromkeys(payload.member_user_ids))
        org_users = db.query(User.id).filter(
            User.organization_id == org.id,
            User.active == True,
            User.id.in_(unique_ids),
        ).all()
        valid_ids = {u.id for u in org_users}
        for uid in unique_ids:
            if uid in valid_ids:
                db.add(GroupMembership(group_id=group.id, user_id=uid, added_by=user.id))
                added_count += 1

    db.commit()
    db.refresh(group)

    audit_log(
        user_id=user.id, event_type="GROUP_CREATED",
        target_key=f"org:{org.id}", org_id=org.id, org_name=org.org_name,
        details={"name": full_name, "members_added": added_count}, request=request,
    )

    return GroupOut(
        id=group.id, org_id=group.org_id, name=group.name,
        member_count=added_count, grant_count=0,
        requires_delete_approval=bool(group.requires_delete_approval),
        created_at=group.created_at.isoformat() if group.created_at else None,
    )


@router.get("/groups", response_model=List[GroupOut])
async def list_groups(
    org_id: int = Query(...),
    user: CurrentUser = Depends(require_role(GROUP_ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    org = _get_org_for_admin(org_id, user, db)
    groups = db.query(UserGroup).filter(UserGroup.org_id == org.id).order_by(UserGroup.name).all()

    result = []
    for g in groups:
        mc = db.query(GroupMembership).filter(GroupMembership.group_id == g.id).count()
        gc = db.query(FolderGrant).filter(FolderGrant.group_id == g.id).count()
        result.append(GroupOut(
            id=g.id, org_id=g.org_id, name=g.name,
            member_count=mc, grant_count=gc,
            requires_delete_approval=bool(g.requires_delete_approval),
            created_at=g.created_at.isoformat() if g.created_at else None,
        ))
    return result


@router.get("/groups/{group_id}", response_model=GroupDetailOut)
async def get_group_detail(
    group_id: int,
    user: CurrentUser = Depends(require_role(GROUP_ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    group = _get_group(group_id, user, db)

    memberships = db.query(GroupMembership).filter(GroupMembership.group_id == group.id).all()
    members = []
    for m in memberships:
        member = db.query(User).filter(User.id == m.user_id).first()
        members.append(MemberOut(
            id=m.id, user_id=m.user_id,
            user_name=member.username if member else None,
            email=member.email if member else None,
            added_at=m.added_at.isoformat() if m.added_at else None,
        ))

    grants_rows = db.query(FolderGrant).filter(FolderGrant.group_id == group.id).all()
    grants = [
        GrantOut(
            id=g.id, prefix=g.prefix, access_level=g.access_level,
            created_at=g.created_at.isoformat() if g.created_at else None,
        )
        for g in grants_rows
    ]

    mc = len(members)
    gc = len(grants)
    return GroupDetailOut(
        id=group.id, org_id=group.org_id,
        org_name=group.org.org_name if group.org else None,
        name=group.name,
        member_count=mc,
        grant_count=gc,
        requires_delete_approval=bool(group.requires_delete_approval),
        members=members, grants=grants,
        created_at=group.created_at.isoformat() if group.created_at else None,
    )


@router.put("/groups/{group_id}", response_model=GroupOut)
async def rename_group(
    group_id: int,
    payload: GroupUpdateRequest,
    request: Request,
    user: CurrentUser = Depends(require_role(GROUP_ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    group = _get_group(group_id, user, db)
    new_name = payload.name.strip()

    if new_name != group.name:
        conflict = db.query(UserGroup).filter(
            UserGroup.org_id == group.org_id,
            UserGroup.name == new_name,
            UserGroup.id != group.id,
        ).first()
        if conflict:
            raise HTTPException(status_code=409, detail=f"Group '{new_name}' already exists")

    old_name = group.name
    group.name = new_name
    db.commit()
    db.refresh(group)

    audit_log(
        user_id=user.id, event_type="GROUP_RENAMED",
        target_key=f"group:{group.id}", org_id=group.org_id,
        org_name=group.org.org_name if group.org else None,
        details={"old_name": old_name, "new_name": new_name}, request=request,
    )

    mc = db.query(GroupMembership).filter(GroupMembership.group_id == group.id).count()
    gc = db.query(FolderGrant).filter(FolderGrant.group_id == group.id).count()
    return GroupOut(
        id=group.id, org_id=group.org_id, name=group.name,
        member_count=mc, grant_count=gc,
        requires_delete_approval=bool(group.requires_delete_approval),
        created_at=group.created_at.isoformat() if group.created_at else None,
    )


@router.delete("/groups/{group_id}", status_code=200)
async def delete_group(
    group_id: int,
    request: Request,
    user: CurrentUser = Depends(require_role(GROUP_ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    group = _get_group(group_id, user, db)
    grant_count = db.query(FolderGrant).filter(FolderGrant.group_id == group.id).count()
    needs_approval = grant_count > 0 or bool(group.requires_delete_approval)

    if needs_approval:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Email approval required: this group has or previously had folder access. "
                "Select an approver and send the approval email; they must confirm Approve or Reject in that email."
            ),
        )

    group_name = group.name
    org_id = group.org_id
    org_name = group.org.org_name if group.org else None

    db.delete(group)
    db.commit()

    audit_log(
        user_id=user.id, event_type="GROUP_DELETED",
        target_key=f"org:{org_id}", org_id=org_id, org_name=org_name,
        details={"name": group_name}, request=request,
    )
    return {"deleted": group_name}


# ----------------------------- Members ------------------------------------

@router.get("/groups/{group_id}/members", response_model=List[MemberOut])
async def list_members(
    group_id: int,
    user: CurrentUser = Depends(require_role(GROUP_ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    group = _get_group(group_id, user, db)
    memberships = db.query(GroupMembership).filter(GroupMembership.group_id == group.id).all()
    result = []
    for m in memberships:
        member = db.query(User).filter(User.id == m.user_id).first()
        result.append(MemberOut(
            id=m.id, user_id=m.user_id,
            user_name=member.username if member else None,
            email=member.email if member else None,
            added_at=m.added_at.isoformat() if m.added_at else None,
        ))
    return result


@router.post("/groups/{group_id}/members", status_code=201)
async def add_members(
    group_id: int,
    payload: AddMembersRequest,
    request: Request,
    user: CurrentUser = Depends(require_role(GROUP_ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    group = _get_group(group_id, user, db)
    org = db.query(Organization).filter(Organization.id == group.org_id).first()

    unique_ids = list(dict.fromkeys(payload.user_ids))

    org_users = db.query(User.id).filter(
        User.organization_id == org.id,
        User.active == True,
        User.id.in_(unique_ids),
    ).all()
    valid_ids = {u.id for u in org_users}

    existing = {
        m.user_id for m in
        db.query(GroupMembership.user_id).filter(
            GroupMembership.group_id == group.id,
            GroupMembership.user_id.in_(unique_ids),
        ).all()
    }

    added = []
    skipped = []
    for uid in unique_ids:
        if uid not in valid_ids:
            skipped.append({"user_id": uid, "reason": "not in org or inactive"})
        elif uid in existing:
            skipped.append({"user_id": uid, "reason": "already a member"})
        else:
            db.add(GroupMembership(group_id=group.id, user_id=uid, added_by=user.id))
            added.append(uid)

    db.commit()

    if added:
        audit_log(
            user_id=user.id, event_type="MEMBER_ADDED",
            target_key=f"group:{group.id}", org_id=group.org_id, org_name=org.org_name,
            details={"user_ids": added}, request=request,
        )

        # Trigger B: notify newly added members about existing grants
        existing_grants = db.query(FolderGrant).filter(FolderGrant.group_id == group.id).all()
        if existing_grants:
            _send_notifications(added, org.id, org.org_name, existing_grants)
            _audit_folder_access_notified(user, org, added, existing_grants, request)

    return {"added": added, "skipped": skipped}


@router.delete("/groups/{group_id}/members/{user_id}", status_code=200)
async def remove_member(
    group_id: int,
    user_id: int,
    request: Request,
    user: CurrentUser = Depends(require_role(GROUP_ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    group = _get_group(group_id, user, db)
    membership = db.query(GroupMembership).filter(
        GroupMembership.group_id == group.id,
        GroupMembership.user_id == user_id,
    ).first()
    if not membership:
        raise HTTPException(status_code=404, detail="User is not a member of this group")

    db.delete(membership)
    db.commit()

    audit_log(
        user_id=user.id, event_type="MEMBER_REMOVED",
        target_key=f"group:{group.id}", org_id=group.org_id,
        org_name=group.org.org_name if group.org else None,
        details={"removed_user_id": user_id}, request=request,
    )
    return {"removed": user_id}


# ----------------------------- Grants -------------------------------------

@router.get("/groups/{group_id}/grants", response_model=List[GrantOut])
async def list_grants(
    group_id: int,
    user: CurrentUser = Depends(require_role(GROUP_ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    group = _get_group(group_id, user, db)
    grants = db.query(FolderGrant).filter(FolderGrant.group_id == group.id).all()
    return [
        GrantOut(
            id=g.id, prefix=g.prefix, access_level=g.access_level,
            created_at=g.created_at.isoformat() if g.created_at else None,
        )
        for g in grants
    ]


@router.post("/groups/{group_id}/grants", status_code=201)
async def create_grant(
    group_id: int,
    payload: CreateGrantRequest,
    request: Request,
    user: CurrentUser = Depends(require_role(GROUP_ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    group = _get_group(group_id, user, db)
    org = db.query(Organization).filter(Organization.id == group.org_id).first()

    s3 = get_s3_client()
    try:
        resp = s3.list_objects_v2(
            Bucket=org.bucket_name, Prefix=payload.prefix, MaxKeys=1,
        )
        has_objects = resp.get("KeyCount", 0) > 0 or len(resp.get("CommonPrefixes", [])) > 0
        if not has_objects:
            resp2 = s3.list_objects_v2(
                Bucket=org.bucket_name, Prefix=payload.prefix, Delimiter="/", MaxKeys=1,
            )
            has_objects = resp2.get("KeyCount", 0) > 0 or len(resp2.get("CommonPrefixes", [])) > 0
        if not has_objects:
            raise HTTPException(
                status_code=400,
                detail=f"Prefix '{payload.prefix}' does not exist in bucket '{org.bucket_name}'",
            )
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=502, detail="Failed to validate prefix in S3")

    existing = db.query(FolderGrant).filter(
        FolderGrant.group_id == group.id,
        FolderGrant.prefix == payload.prefix,
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="Grant already exists for this prefix")

    grant = FolderGrant(
        group_id=group.id, org_id=org.id,
        prefix=payload.prefix, access_level=payload.access_level,
        created_by=user.id,
    )
    db.add(grant)
    group.requires_delete_approval = True
    db.commit()
    db.refresh(grant)

    audit_log(
        user_id=user.id, event_type="GRANT_CREATED",
        target_key=f"group:{group.id}", org_id=org.id, org_name=org.org_name,
        details={"prefix": payload.prefix, "access_level": payload.access_level},
        request=request,
    )

    # Trigger A: notify all current group members about new grant
    member_ids = [
        m.user_id for m in
        db.query(GroupMembership.user_id).filter(GroupMembership.group_id == group.id).all()
    ]
    _send_notifications(member_ids, org.id, org.org_name, [grant])
    _audit_folder_access_notified(user, org, member_ids, [grant], request)

    return GrantOut(
        id=grant.id, prefix=grant.prefix, access_level=grant.access_level,
        created_at=grant.created_at.isoformat() if grant.created_at else None,
    )


@router.delete("/groups/{group_id}/grants/{grant_id}", status_code=200)
async def remove_grant(
    group_id: int,
    grant_id: int,
    request: Request,
    user: CurrentUser = Depends(require_role(GROUP_ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    group = _get_group(group_id, user, db)
    grant = db.query(FolderGrant).filter(
        FolderGrant.id == grant_id, FolderGrant.group_id == group.id,
    ).first()
    if not grant:
        raise HTTPException(status_code=404, detail="Grant not found")

    prefix = grant.prefix
    db.delete(grant)
    db.commit()

    audit_log(
        user_id=user.id, event_type="GRANT_REMOVED",
        target_key=f"group:{group.id}", org_id=group.org_id,
        org_name=group.org.org_name if group.org else None,
        details={"prefix": prefix}, request=request,
    )
    return {"removed": grant_id}


# ----------------------------- Organization User Search ----------------------------

@router.get("/orgs/{org_id}/users")
async def search_org_users(
    org_id: int,
    search: str = Query("", min_length=0),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    user: CurrentUser = Depends(require_role(GROUP_ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    """Paginated user search within an org for the member picker UI."""
    org = _get_org_for_admin(org_id, user, db)

    q = db.query(User).filter(
        User.organization_id == org.id,
        User.active == True,
    )
    if search:
        term = f"%{search}%"
        q = q.filter(
            (User.username.ilike(term)) | (User.email.ilike(term))
        )

    total = q.count()
    users = q.order_by(User.username).offset((page - 1) * page_size).limit(page_size).all()

    return {
        "users": [
            {
                "id": u.id,
                "user_name": u.username,
                "email": u.email,
                "role": u.role,
            }
            for u in users
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
        "has_more": (page * page_size) < total,
    }


# ----------------------------- Organization Folder Tree ----------------------------

@router.get("/orgs/{org_id}/folder-tree")
async def get_folder_tree(
    org_id: int,
    prefix: str = Query("", description="Parent prefix to list children of"),
    user: CurrentUser = Depends(require_role(GROUP_ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    """
    List immediate child folders of a prefix in the org bucket.
    Used by the folder mapping modal for lazy-loaded drill-down.
    """
    org = _get_org_for_admin(org_id, user, db)

    s3 = get_s3_client()
    folders = []
    continuation = None

    while True:
        kwargs = {
            "Bucket": org.bucket_name,
            "Prefix": prefix,
            "Delimiter": "/",
            "MaxKeys": 1000,
        }
        if continuation:
            kwargs["ContinuationToken"] = continuation

        try:
            resp = s3.list_objects_v2(**kwargs)
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"S3 error: {str(e)}")

        for cp in resp.get("CommonPrefixes", []):
            p = cp["Prefix"]
            name = p[len(prefix):].rstrip("/")
            if name:
                folders.append({"name": name, "prefix": p})

        if resp.get("IsTruncated"):
            continuation = resp.get("NextContinuationToken")
        else:
            break

    return {"prefix": prefix, "folders": folders}
