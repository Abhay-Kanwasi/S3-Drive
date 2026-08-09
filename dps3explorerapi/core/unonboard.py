"""
4-eyes un-onboard: requester OTP in app, approver email approve/reject.
"""

from datetime import datetime, timedelta, timezone
from typing import List, Optional

import secrets
from fastapi import HTTPException
from sqlalchemy.orm import Session, lazyload

from core.approval import (
    STATUS_PENDING as APPROVAL_PENDING,
    STATUS_REJECTED as APPROVAL_REJECTED,
    _action_url,
    _approval_base_url,
    _esc,
    _hash_token,
    _mask_email,
    _respond_post_url,
    _validity_label,
    invalidate_pending_approvals,
)
from core.auth import (
    CurrentUser,
    GLOBAL_ADMIN_ROLE_IDS,
    ROLE_MASTER_ADMIN,
    ROLE_SUPER_ADMIN,
    UAMUser,
)
from core.config import settings
from core.otp import create_and_send_otp, verify_otp
from core.smtp_email import send_smtp_html, smtp_configured
from db.models import (
    AdminApprovalRequest,
    FolderGrant,
    FolderMetadata,
    GroupMembership,
    Organization,
    UnonboardRequest,
    UserGroup,
    UserNotification,
)
from models.email_templates.unonboard_approval import unonboard_approval_email_body

STATUS_PENDING = "pending_approval"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"
STATUS_EXPIRED = "expired"

UNONBOARD_REQUEST_HOURS = 24


def unonboard_submit_purpose(org_id: int) -> str:
    return f"unonboard_submit:{org_id}"


def unonboard_approval_purpose(request_id: int) -> str:
    return f"unonboard:{request_id}"


def is_unonboard_approval_purpose(purpose: str) -> bool:
    return purpose.startswith("unonboard:") and not purpose.startswith("unonboard_submit:")


def parse_unonboard_request_id(purpose: str) -> int:
    try:
        return int(purpose.split(":", 1)[1])
    except (IndexError, ValueError) as e:
        raise HTTPException(status_code=400, detail="Invalid unonboard purpose.") from e


def list_master_admin_approvers(db: Session, requester: CurrentUser) -> List[dict]:
    """Other global master/super admins who may approve un-onboard."""
    rows = (
        db.query(UAMUser)
        .filter(
            UAMUser.active == True,
            UAMUser.role.in_([ROLE_MASTER_ADMIN, ROLE_SUPER_ADMIN]),
            UAMUser.email.isnot(None),
            UAMUser.email != "",
            UAMUser.id != requester.id,
        )
        .order_by(UAMUser.user_name, UAMUser.id)
        .all()
    )
    from core.auth import ROLE_LABELS

    return [
        {
            "id": u.id,
            "user_name": u.user_name or "",
            "email": u.email or "",
            "role_id": u.role,
            "role_label": ROLE_LABELS.get(u.role, "user"),
        }
        for u in rows
    ]


def _resolve_approver(db: Session, approver_user_id: int, requester: CurrentUser) -> UAMUser:
    if approver_user_id == requester.id:
        raise HTTPException(
            status_code=400,
            detail="Choose a different master admin; you cannot approve your own un-onboard request.",
        )
    approver = db.query(UAMUser).filter(UAMUser.id == approver_user_id).first()
    if not approver or not approver.active:
        raise HTTPException(status_code=400, detail="Approver not found or inactive.")
    if approver.role not in (ROLE_MASTER_ADMIN, ROLE_SUPER_ADMIN):
        raise HTTPException(
            status_code=400,
            detail="Approver must be a master admin or super admin.",
        )
    if not approver.email:
        raise HTTPException(status_code=400, detail="Approver has no email address.")
    return approver


def send_requester_otp(db: Session, *, org_id: int, requester: CurrentUser) -> dict:
    if requester.role_id not in GLOBAL_ADMIN_ROLE_IDS:
        raise HTTPException(status_code=403, detail="Only master or super admins can un-onboard.")

    org = db.query(Organization).filter(Organization.id == org_id, Organization.is_active == True).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found or already inactive.")

    if not smtp_configured():
        raise RuntimeError("SMTP is not configured.")

    if not requester.email:
        raise HTTPException(status_code=400, detail="Your account has no email; cannot send OTP.")

    purpose = unonboard_submit_purpose(org_id)
    result = create_and_send_otp(
        db,
        user_id=requester.id,
        email=requester.email,
        user_name=requester.user_name,
        purpose=purpose,
    )
    return result


def _org_unonboard_stats(db: Session, org_id: int) -> dict:
    grant_count = db.query(FolderGrant).filter(FolderGrant.org_id == org_id).count()
    group_count = db.query(UserGroup).filter(UserGroup.org_id == org_id).count()
    return {"grant_count": grant_count, "group_count": group_count}


def _purge_org_explorer_data(db: Session, org_id: int) -> None:
    """Remove grants, groups, folder metadata, and notifications before deleting s3_org."""
    group_ids = [
        row[0]
        for row in db.query(UserGroup.id).filter(UserGroup.org_id == org_id).all()
    ]
    if group_ids:
        db.query(FolderGrant).filter(FolderGrant.group_id.in_(group_ids)).delete(
            synchronize_session=False
        )
        db.query(GroupMembership).filter(GroupMembership.group_id.in_(group_ids)).delete(
            synchronize_session=False
        )
    db.query(FolderGrant).filter(FolderGrant.org_id == org_id).delete(synchronize_session=False)
    db.query(UserGroup).filter(UserGroup.org_id == org_id).delete(synchronize_session=False)
    db.query(FolderMetadata).filter(FolderMetadata.org_id == org_id).delete(
        synchronize_session=False
    )
    db.query(UserNotification).filter(UserNotification.org_id == org_id).delete(
        synchronize_session=False
    )


def _invalidate_pending_unonboard(db: Session, org_id: int) -> None:
    now = datetime.now(timezone.utc)
    (
        db.query(UnonboardRequest)
        .filter(
            UnonboardRequest.org_id == org_id,
            UnonboardRequest.status == STATUS_PENDING,
            UnonboardRequest.expires_at > now,
        )
        .update(
            {UnonboardRequest.status: STATUS_EXPIRED, UnonboardRequest.resolved_at: now},
            synchronize_session=False,
        )
    )


def create_unonboard_request(
    db: Session,
    *,
    org_id: int,
    approver_user_id: int,
    otp_code: str,
    requester: CurrentUser,
    request_base_url: Optional[str] = None,
) -> dict:
    if requester.role_id not in GLOBAL_ADMIN_ROLE_IDS:
        raise HTTPException(status_code=403, detail="Only master or super admins can un-onboard.")

    org = db.query(Organization).filter(Organization.id == org_id, Organization.is_active == True).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found or already inactive.")

    purpose = unonboard_submit_purpose(org_id)
    if not verify_otp(
        db, user_id=requester.id, code=otp_code, purpose=purpose, consume=True
    ):
        raise HTTPException(status_code=403, detail="Invalid or expired OTP.")

    approver = _resolve_approver(db, approver_user_id, requester)
    _invalidate_pending_unonboard(db, org_id)

    expires_at = datetime.now(timezone.utc) + timedelta(hours=UNONBOARD_REQUEST_HOURS)
    req = UnonboardRequest(
        org_id=org.id,
        org_name=org.org_name,
        bucket_name=org.bucket_name,
        subscription_id=org.subscription_id,
        requester_user_id=requester.id,
        approver_user_id=approver.id,
        status=STATUS_PENDING,
        expires_at=expires_at,
    )
    db.add(req)
    db.flush()

    approval_purpose = unonboard_approval_purpose(req.id)
    invalidate_pending_approvals(db, approval_purpose)

    approve_token = secrets.token_urlsafe(32)
    reject_token = secrets.token_urlsafe(32)
    approval_expires = expires_at
    approval_row = AdminApprovalRequest(
        purpose=approval_purpose,
        requester_user_id=requester.id,
        approver_user_id=approver.id,
        approve_token_hash=_hash_token(approve_token),
        reject_token_hash=_hash_token(reject_token),
        status=APPROVAL_PENDING,
        expires_at=approval_expires,
    )
    db.add(approval_row)
    db.flush()

    stats = _org_unonboard_stats(db, org.id)
    base = _approval_base_url(request_base_url)
    greeting = f" {_esc(approver.user_name)}" if approver.user_name else ""
    requester_label = requester.user_name or requester.email or "A master admin"
    html = unonboard_approval_email_body.format(
        greeting=greeting,
        requester_name=_esc(requester_label),
        org_name=_esc(org.org_name),
        bucket_name=_esc(org.bucket_name),
        grant_count=stats["grant_count"],
        group_count=stats["group_count"],
        approve_url=_action_url(base, approval_row.id, approve_token, "approve"),
        reject_url=_action_url(base, approval_row.id, reject_token, "reject"),
        valid_hours=_validity_label(),
    )
    send_smtp_html(
        to_email=approver.email,
        subject=f"S3 Explorer — Approve un-onboard: {org.org_name}",
        html_body=html,
    )

    return {
        "request_id": req.id,
        "org_id": org.id,
        "org_name": org.org_name,
        "status": req.status,
        "expires_at": expires_at.isoformat(),
        "approver_email_masked": _mask_email(approver.email),
    }


def unonboard_summary(db: Session, request_id: int) -> dict:
    req = db.query(UnonboardRequest).filter(UnonboardRequest.id == request_id).first()
    if not req:
        return {}
    org = None
    if req.org_id:
        org = req.org or db.query(Organization).filter(Organization.id == req.org_id).first()
    org_name = (org.org_name if org else None) or req.org_name
    bucket_name = (org.bucket_name if org else None) or req.bucket_name
    if not org_name or not bucket_name:
        return {}
    if org:
        stats = _org_unonboard_stats(db, org.id)
    else:
        stats = {"grant_count": 0, "group_count": 0}
    requester = db.query(UAMUser).filter(UAMUser.id == req.requester_user_id).first()
    return {
        "org_name": org_name,
        "bucket_name": bucket_name,
        "grant_count": stats["grant_count"],
        "group_count": stats["group_count"],
        "requester_name": (requester.user_name or requester.email) if requester else "Unknown",
    }


def apply_unonboard(db: Session, request_id: int) -> tuple:
    """Remove Explorer data and delete s3_org binding. Returns (org_name, org_id, bucket, grants_removed)."""
    now = datetime.now(timezone.utc)
    q = (
        db.query(UnonboardRequest)
        .options(lazyload(UnonboardRequest.org))
        .filter(
            UnonboardRequest.id == request_id,
            UnonboardRequest.status == STATUS_PENDING,
            UnonboardRequest.expires_at > now,
        )
    )
    try:
        q = q.with_for_update(of=UnonboardRequest)
    except Exception:
        pass
    req = q.first()
    if not req:
        raise HTTPException(
            status_code=404,
            detail="Un-onboard request not found, expired, or already resolved.",
        )

    org = (
        db.query(Organization)
        .filter(Organization.id == req.org_id, Organization.is_active == True)
        .first()
        if req.org_id
        else None
    )
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found or already un-onboarded.")

    org_name = org.org_name
    org_id = org.id
    bucket_name = org.bucket_name
    grant_count = db.query(FolderGrant).filter(FolderGrant.org_id == org.id).count()

    req.org_name = org.org_name
    req.bucket_name = org.bucket_name
    req.subscription_id = org.subscription_id

    _purge_org_explorer_data(db, org.id)
    db.delete(org)
    req.status = STATUS_APPROVED
    req.resolved_at = now
    return org_name, org_id, bucket_name, grant_count


def reject_unonboard_request(db: Session, request_id: int) -> str:
    req = db.query(UnonboardRequest).filter(UnonboardRequest.id == request_id).first()
    if not req:
        return "the organization"
    now = datetime.now(timezone.utc)
    if req.status == STATUS_PENDING:
        req.status = STATUS_REJECTED
        req.resolved_at = now
    org = req.org or (db.query(Organization).filter(Organization.id == req.org_id).first() if req.org_id else None)
    return (org.org_name if org else None) or req.org_name or "the organization"
