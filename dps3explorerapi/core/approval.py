"""
Email approve/reject flow for sensitive admin actions (group delete with folder grants).
"""

import html as _html_lib
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple
from urllib.parse import quote


def _esc(value: object) -> str:
    """HTML-escape a value for safe embedding in message_html / pages."""
    return _html_lib.escape(str(value), quote=True) if value is not None else ""

import bcrypt
from fastapi import HTTPException
from sqlalchemy.orm import Session

from core.auth import CurrentUser, UAMUser
from core.config import settings
from core.otp import group_delete_purpose, resolve_otp_recipient
from core.smtp_email import send_smtp_html, smtp_configured
from db.models import (
    AdminApprovalRequest,
    FolderGrant,
    GroupMembership,
    Org,
    UserGroup,
)
from models.email_templates.approval import approval_email_body

logger = logging.getLogger(__name__)

STATUS_PENDING = "pending"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"


def _hash_token(token: str) -> str:
    return bcrypt.hashpw(token.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _check_token(token: str, token_hash: str) -> bool:
    try:
        return bcrypt.checkpw(token.encode("utf-8"), token_hash.encode("utf-8"))
    except ValueError:
        return False


def _mask_email(email: str) -> str:
    if not email or "@" not in email:
        return "***"
    local, domain = email.split("@", 1)
    masked_local = local[0] + "***" if len(local) > 1 else "*"
    return f"{masked_local}@{domain}"


def _approval_base_url(request_base: Optional[str]) -> str:
    configured = (settings.APPROVAL_BASE_URL or "").strip().rstrip("/")
    if configured:
        return configured
    if request_base:
        rb = request_base.rstrip("/")
        api = settings.API_V1_STR.rstrip("/")
        if rb.endswith(api):
            return rb
        return f"{rb}{settings.API_V1_STR}"
    return settings.API_V1_STR.rstrip("/")


def _action_url(base: str, approval_id: int, token: str, action: str) -> str:
    """Email link target. Prefers the signed-in SPA route at APPROVAL_FRONTEND_URL.

    The legacy API HTML form cannot submit with Bearer auth, so we log a warning when
    falling back to it. Set APPROVAL_FRONTEND_URL in production whenever SMTP approvals
    are enabled.
    """
    fe = (settings.APPROVAL_FRONTEND_URL or "").strip().rstrip("/")
    if fe:
        return (
            f"{fe}/admin/approval"
            f"?id={approval_id}&token={quote(token, safe='')}&action={action}"
        )
    logger.warning(
        "APPROVAL_FRONTEND_URL is not set; approval email links will point at the legacy "
        "HTML form which cannot submit with Bearer auth. Set APPROVAL_FRONTEND_URL to your "
        "SPA origin (e.g. https://app.example.com) so approvers land on /admin/approval."
    )
    return (
        f"{base}/admin/approval/respond"
        f"?id={approval_id}&token={quote(token, safe='')}&action={action}"
    )


def _respond_post_url(base: str) -> str:
    return f"{base}/admin/approval/respond"


def _validity_label() -> str:
    minutes = settings.APPROVAL_VALID_MINUTES
    if minutes < 60:
        return f"{minutes} minutes"
    hours = (minutes + 59) // 60
    return f"{hours} hour{'s' if hours != 1 else ''}"


def _parse_group_id(purpose: str) -> int:
    if not purpose.startswith("group_delete:"):
        raise HTTPException(status_code=400, detail="Unsupported approval purpose.")
    try:
        return int(purpose.split(":", 1)[1])
    except (IndexError, ValueError) as e:
        raise HTTPException(status_code=400, detail="Invalid group_delete purpose.") from e


def invalidate_pending_approvals(db: Session, purpose: str) -> None:
    now = datetime.now(timezone.utc)
    (
        db.query(AdminApprovalRequest)
        .filter(
            AdminApprovalRequest.purpose == purpose,
            AdminApprovalRequest.status == STATUS_PENDING,
            AdminApprovalRequest.expires_at > now,
        )
        .update(
            {AdminApprovalRequest.status: STATUS_REJECTED, AdminApprovalRequest.resolved_at: now},
            synchronize_session=False,
        )
    )


def create_and_send_group_delete_approval(
    db: Session,
    *,
    group_id: int,
    approver: UAMUser,
    requester: CurrentUser,
    request_base_url: Optional[str] = None,
) -> dict:
    """Create pending approval and email approve/reject links to the approver."""
    if not smtp_configured():
        raise RuntimeError(
            "SMTP is not configured. Set SMTP_HOST, SMTP_USERNAME, SMTP_PASSWORD, and PORT in .env"
        )

    group = db.query(UserGroup).filter(UserGroup.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found.")

    if approver.id == requester.id:
        raise HTTPException(
            status_code=400,
            detail="Choose a different admin; you cannot send a delete approval request to yourself.",
        )

    grant_count = db.query(FolderGrant).filter(FolderGrant.group_id == group.id).count()
    if grant_count == 0 and not group.requires_delete_approval:
        raise HTTPException(
            status_code=400,
            detail="This group has no folder grants; delete it directly without approval.",
        )
    group.requires_delete_approval = True

    purpose = group_delete_purpose(group_id)
    invalidate_pending_approvals(db, purpose)

    approve_token = secrets.token_urlsafe(32)
    reject_token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.APPROVAL_VALID_MINUTES)

    row = AdminApprovalRequest(
        purpose=purpose,
        requester_user_id=requester.id,
        approver_user_id=approver.id,
        approve_token_hash=_hash_token(approve_token),
        reject_token_hash=_hash_token(reject_token),
        status=STATUS_PENDING,
        expires_at=expires_at,
    )
    db.add(row)
    db.flush()

    member_count = db.query(GroupMembership).filter(GroupMembership.group_id == group.id).count()
    org = db.query(Org).filter(Org.id == group.org_id).first()
    org_name = org.org_name if org else "—"
    base = _approval_base_url(request_base_url)
    validity = _validity_label()

    greeting = f" {_esc(approver.user_name)}" if approver.user_name else ""
    requester_label = requester.user_name or requester.email or "An admin"
    html = approval_email_body.format(
        greeting=greeting,
        requested_line="",
        requester_name=_esc(requester_label),
        group_name=_esc(group.name),
        org_name=_esc(org_name),
        member_count=member_count,
        grant_count=grant_count,
        approve_url=_action_url(base, row.id, approve_token, "approve"),
        reject_url=_action_url(base, row.id, reject_token, "reject"),
        valid_hours=validity,
    )
    send_smtp_html(
        to_email=approver.email,
        subject=f"S3 Explorer — Approve group deletion: {group.name}",
        html_body=html,
    )

    return {
        "sent": True,
        "approval_required": True,
        "expires_in_seconds": settings.APPROVAL_VALID_MINUTES * 60,
        "masked_email": _mask_email(approver.email),
        "purpose": purpose,
        "recipient_user_id": approver.id,
    }


def _find_pending_by_token(
    db: Session, approval_id: int, token: str, action: str, *, lock: bool = False
) -> Optional[AdminApprovalRequest]:
    if action not in ("approve", "reject"):
        return None
    now = datetime.now(timezone.utc)
    q = db.query(AdminApprovalRequest).filter(
        AdminApprovalRequest.id == approval_id,
        AdminApprovalRequest.status == STATUS_PENDING,
        AdminApprovalRequest.expires_at > now,
    )
    if lock:
        try:
            q = q.with_for_update()
        except Exception:
            pass
    row = q.first()
    if not row:
        return None
    h = row.approve_token_hash if action == "approve" else row.reject_token_hash
    if _check_token(token, h):
        return row
    return None


def _html_page(title: str, message: str, *, ok: bool = True) -> str:
    color = "#16a34a" if ok else "#dc2626"
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{title}</title></head>
<body style="font-family:Arial,sans-serif;padding:40px;max-width:520px;margin:0 auto;">
<h1 style="color:{color};font-size:22px;">{title}</h1>
<p style="line-height:1.6;color:#333;">{message}</p>
<p style="color:#666;font-size:13px;">You can close this window.</p>
</body></html>"""


def _group_delete_summary(db: Session, group_id: int) -> dict:
    group = db.query(UserGroup).filter(UserGroup.id == group_id).first()
    if not group:
        return {}
    org = db.query(Org).filter(Org.id == group.org_id).first()
    member_count = db.query(GroupMembership).filter(GroupMembership.group_id == group.id).count()
    grant_count = db.query(FolderGrant).filter(FolderGrant.group_id == group.id).count()
    prefixes = [
        row.prefix
        for row in (
            db.query(FolderGrant)
            .filter(FolderGrant.group_id == group.id)
            .order_by(FolderGrant.prefix)
            .limit(8)
            .all()
        )
    ]
    return {
        "group_name": group.name,
        "org_name": org.org_name if org else "—",
        "member_count": member_count,
        "grant_count": grant_count,
        "prefixes": prefixes,
    }


def build_approval_confirmation_page(
    db: Session,
    *,
    approval_id: int,
    token: str,
    action: str,
    request_base_url: Optional[str] = None,
) -> Tuple[str, int]:
    """GET handler: show review page only; destructive action requires POST."""
    if not token or not token.strip():
        return _html_page("Invalid link", "The approval link is missing or invalid.", ok=False), 400

    row = _find_pending_by_token(db, approval_id, token.strip(), action)
    if not row:
        return (
            _html_page(
                "Link expired or already used",
                "This approval link is invalid, expired, or was already used.",
                ok=False,
            ),
            400,
        )

    from core.unonboard import is_unonboard_approval_purpose, parse_unonboard_request_id, unonboard_summary

    requester = db.query(UAMUser).filter(UAMUser.id == row.requester_user_id).first()
    requester_label = (
        f"{requester.user_name} ({requester.email})" if requester and requester.email
        else (requester.user_name if requester else "Unknown")
    )
    requester_label_esc = _esc(requester_label)

    base = _approval_base_url(request_base_url)
    post_url = _respond_post_url(base)
    token_esc = _esc(token.strip())
    action_esc = _esc(action)

    if is_unonboard_approval_purpose(row.purpose):
        request_id = parse_unonboard_request_id(row.purpose)
        summary = unonboard_summary(db, request_id)
        if not summary:
            return _html_page("Request not found", "This un-onboard request no longer exists.", ok=False), 404
        if action == "approve":
            title = "Confirm un-onboard"
            lead = (
                f"<strong>{requester_label_esc}</strong> asked you to approve un-onboarding this organization. "
                "The org–bucket binding and all Explorer groups/grants will be removed. The S3 bucket in AWS is not deleted."
            )
            btn_label = "Confirm un-onboard"
        else:
            title = "Confirm rejection"
            lead = (
                f"<strong>{requester_label_esc}</strong> asked you to review an un-onboard request. "
                "Rejecting leaves the org–bucket binding unchanged."
            )
            btn_label = "Confirm rejection"
        btn_color = "#16a34a" if action == "approve" else "#dc2626"
        table_rows = f"""
<tr><td style="padding:6px 0;color:#666;">Organization</td><td><strong>{_esc(summary['org_name'])}</strong></td></tr>
<tr><td style="padding:6px 0;color:#666;">Bucket</td><td style="font-family:monospace;">{_esc(summary['bucket_name'])}</td></tr>
<tr><td style="padding:6px 0;color:#666;">Grants to revoke</td><td>{int(summary['grant_count'])}</td></tr>
<tr><td style="padding:6px 0;color:#666;">Groups (will be removed)</td><td>{int(summary['group_count'])}</td></tr>"""
        extra_block = ""
    else:
        group_id = _parse_group_id(row.purpose)
        summary = _group_delete_summary(db, group_id)
        if not summary:
            return _html_page("Group not found", "This group no longer exists.", ok=False), 404
        if action == "approve":
            title = "Confirm group deletion"
            lead = (
                f"<strong>{requester_label_esc}</strong> asked you to approve deleting this group. "
                "This cannot be undone."
            )
            btn_label = "Confirm deletion"
        else:
            title = "Confirm rejection"
            lead = (
                f"<strong>{requester_label_esc}</strong> asked you to review a group deletion request. "
                "Rejecting will leave the group unchanged."
            )
            btn_label = "Confirm rejection"
        btn_color = "#16a34a" if action == "approve" else "#dc2626"
        prefix_lines = "".join(
            f"<li style='font-family:monospace;font-size:12px;'>{_esc(p)}</li>" for p in summary["prefixes"]
        )
        if summary["grant_count"] > len(summary["prefixes"]):
            extra = summary["grant_count"] - len(summary["prefixes"])
            prefix_lines += f"<li style='color:#666;font-size:12px;'>+{int(extra)} more</li>"
        table_rows = f"""
<tr><td style="padding:6px 0;color:#666;">Group</td><td><strong>{_esc(summary['group_name'])}</strong></td></tr>
<tr><td style="padding:6px 0;color:#666;">Organization</td><td>{_esc(summary['org_name'])}</td></tr>
<tr><td style="padding:6px 0;color:#666;">Members</td><td>{int(summary['member_count'])}</td></tr>
<tr><td style="padding:6px 0;color:#666;">Folder grants</td><td>{int(summary['grant_count'])}</td></tr>"""
        extra_block = (
            f"<ul style='margin:0 0 16px 20px;padding:0;'>{prefix_lines}</ul>" if prefix_lines else ""
        )

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{_esc(title)}</title></head>
<body style="font-family:Arial,sans-serif;padding:40px;max-width:560px;margin:0 auto;">
<h1 style="font-size:22px;">{_esc(title)}</h1>
<p style="line-height:1.6;color:#333;">{lead}</p>
<table style="width:100%;font-size:14px;margin:16px 0;border-collapse:collapse;">
{table_rows}
</table>
{extra_block}
<form method="post" action="{_esc(post_url)}" style="margin-top:24px;">
  <input type="hidden" name="id" value="{int(approval_id)}" />
  <input type="hidden" name="token" value="{token_esc}" />
  <input type="hidden" name="action" value="{action_esc}" />
  <button type="submit" style="background:{btn_color};color:#fff;border:none;padding:12px 24px;border-radius:8px;font-weight:bold;cursor:pointer;">{_esc(btn_label)}</button>
</form>
<p style="color:#666;font-size:12px;margin-top:20px;">Link expires in {_esc(_validity_label())}. No changes are made until you click the button above.</p>
</body></html>"""
    return html, 200


def build_approval_review_payload(
    db: Session,
    *,
    approval_id: int,
    token: str,
    action: str,
    actor_id: Optional[int] = None,
) -> Tuple[dict, int]:
    """Return JSON-serializable review summary for the SPA confirmation page.

    Validates token + assigned-approver match without mutating any state. Returns
    ({...}, 200) on success or ({"detail": ...}, status) on failure.
    """
    if not token or not token.strip():
        return {"detail": "The approval link is missing or invalid."}, 400

    row = _find_pending_by_token(db, approval_id, token.strip(), action)
    if not row:
        return {"detail": "This approval link is invalid, expired, or was already used."}, 400

    if actor_id is not None and row.approver_user_id != actor_id:
        return {
            "detail": (
                "Only the master admin selected as approver for this request can approve or reject it."
            )
        }, 403

    from core.unonboard import is_unonboard_approval_purpose, parse_unonboard_request_id, unonboard_summary

    requester = db.query(UAMUser).filter(UAMUser.id == row.requester_user_id).first()
    requester_label = (
        f"{requester.user_name} ({requester.email})" if requester and requester.email
        else (requester.user_name if requester else "Unknown")
    )

    base_payload = {
        "approval_id": approval_id,
        "action": action,
        "requester_label": requester_label,
        "requester_user_id": row.requester_user_id,
        "approver_user_id": row.approver_user_id,
        "expires_at": row.expires_at.isoformat() if row.expires_at else None,
    }

    if is_unonboard_approval_purpose(row.purpose):
        request_id = parse_unonboard_request_id(row.purpose)
        summary = unonboard_summary(db, request_id)
        if not summary:
            return {"detail": "This un-onboard request no longer exists."}, 404
        base_payload.update({
            "kind": "unonboard",
            "summary": {
                "org_name": summary["org_name"],
                "bucket_name": summary["bucket_name"],
                "grant_count": summary["grant_count"],
                "group_count": summary["group_count"],
            },
        })
        return base_payload, 200

    group_id = _parse_group_id(row.purpose)
    summary = _group_delete_summary(db, group_id)
    if not summary:
        return {"detail": "This group no longer exists."}, 404
    base_payload.update({
        "kind": "group_delete",
        "summary": {
            "group_name": summary["group_name"],
            "org_name": summary["org_name"],
            "member_count": summary["member_count"],
            "grant_count": summary["grant_count"],
            "prefixes": summary["prefixes"],
        },
    })
    return base_payload, 200


def _delete_group_by_id(db: Session, group_id: int) -> Tuple[str, int, Optional[str]]:
    from sqlalchemy.orm import lazyload

    q = (
        db.query(UserGroup)
        .options(lazyload(UserGroup.org))
        .filter(UserGroup.id == group_id)
    )
    try:
        q = q.with_for_update(of=UserGroup)
    except Exception:
        pass
    group = q.first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found.")
    group_name = group.name
    org_id = group.org_id
    org_name = group.org.org_name if group.org else None
    db.delete(group)
    return group_name, org_id, org_name


def _execute_approval(
    db: Session,
    *,
    approval_id: int,
    token: str,
    action: str,
    actor_id: Optional[int] = None,
) -> Tuple[dict, int]:
    """Core mutation. Returns ({title, message_html, kind, ...}, status_code).

    - title/message_html are pre-formatted strings the caller can render in HTML or JSON.
    - On token/auth failure, returns {"detail": "..."} with the relevant non-200 status.
    """
    if not token or not token.strip():
        return {"detail": "The approval link is missing or invalid."}, 400

    row = _find_pending_by_token(
        db, approval_id, token.strip(), action, lock=True
    )
    if not row:
        return {"detail": "This approval link is invalid, expired, or was already used."}, 400

    if actor_id is not None and row.approver_user_id != actor_id:
        return {
            "detail": (
                "Only the master admin selected as approver for this request can approve or reject it. "
                "Sign in as that admin and click the link from their email."
            )
        }, 403

    from core.unonboard import (
        apply_unonboard,
        is_unonboard_approval_purpose,
        parse_unonboard_request_id,
        reject_unonboard_request,
    )

    now = datetime.now(timezone.utc)

    if is_unonboard_approval_purpose(row.purpose):
        request_id = parse_unonboard_request_id(row.purpose)
        if action == "reject":
            row.status = STATUS_REJECTED
            row.resolved_at = now
            name = reject_unonboard_request(db, request_id)
            db.commit()
            return (
                {
                    "kind": "unonboard",
                    "action": "reject",
                    "title": "Un-onboard rejected",
                    "message": f"You rejected un-onboarding {name}. The organization remains active.",
                    "message_html": (
                        f"You rejected un-onboarding <strong>{_esc(name)}</strong>. "
                        "The organization remains active."
                    ),
                    "org_name": name,
                },
                200,
            )
        row.status = STATUS_APPROVED
        row.resolved_at = now
        try:
            org_name, org_id, bucket_name, grants_removed = apply_unonboard(db, request_id)
        except HTTPException:
            row.status = STATUS_REJECTED
            row.resolved_at = now
            db.commit()
            return {"detail": "This un-onboard request is no longer valid."}, 404
        db.commit()
        from core.audit import audit_log

        audit_log(
            user_id=row.approver_user_id,
            event_type="ORG_UNONBOARD_APPROVED",
            target_key=bucket_name,
            org_id=org_id,
            org_name=org_name,
            details={
                "approved_via_email": True,
                "requested_by_user_id": row.requester_user_id,
                "grants_removed": grants_removed,
            },
            request=None,
        )
        return (
            {
                "kind": "unonboard",
                "action": "approve",
                "title": "Organization un-onboarded",
                "message": (
                    f"You approved un-onboarding {org_name}. "
                    f"{grants_removed} folder grant(s) were removed and the org–bucket binding was deleted. "
                    f"The bucket {bucket_name} can be onboarded again."
                ),
                "message_html": (
                    f"You approved un-onboarding <strong>{_esc(org_name)}</strong>. "
                    f"{grants_removed} folder grant(s) were removed and the org–bucket binding was deleted. "
                    f"The bucket <code>{_esc(bucket_name)}</code> can be onboarded again."
                ),
                "org_name": org_name,
                "org_id": org_id,
                "bucket_name": bucket_name,
                "grants_removed": grants_removed,
            },
            200,
        )

    group_id = _parse_group_id(row.purpose)

    if action == "reject":
        row.status = STATUS_REJECTED
        row.resolved_at = now
        db.commit()
        group = db.query(UserGroup).filter(UserGroup.id == group_id).first()
        name = group.name if group else "the group"
        return (
            {
                "kind": "group_delete",
                "action": "reject",
                "title": "Deletion rejected",
                "message": f"You rejected the request to delete {name}. No changes were made.",
                "message_html": (
                    f"You rejected the request to delete <strong>{_esc(name)}</strong>. "
                    "No changes were made."
                ),
                "group_name": name,
            },
            200,
        )

    row.status = STATUS_APPROVED
    row.resolved_at = now
    try:
        group_name, org_id, org_name = _delete_group_by_id(db, group_id)
    except HTTPException:
        row.status = STATUS_REJECTED
        row.resolved_at = now
        db.commit()
        return {"detail": "This group was already deleted or no longer exists."}, 404
    db.commit()

    from core.audit import audit_log

    audit_log(
        user_id=row.approver_user_id,
        event_type="GROUP_DELETED",
        target_key=f"org:{org_id}",
        org_id=org_id,
        org_name=org_name,
        details={
            "name": group_name,
            "approved_via_email": True,
            "requested_by_user_id": row.requester_user_id,
        },
        request=None,
    )

    return (
        {
            "kind": "group_delete",
            "action": "approve",
            "title": "Group deleted",
            "message": (
                f"You approved deletion of {group_name}. "
                "The group and its folder access have been removed."
            ),
            "message_html": (
                f"You approved deletion of <strong>{_esc(group_name)}</strong>. "
                "The group and its folder access have been removed."
            ),
            "group_name": group_name,
            "org_id": org_id,
            "org_name": org_name,
        },
        200,
    )


def _result_to_html(result: dict, status_code: int) -> Tuple[str, int]:
    if "detail" in result:
        return _html_page("Approval link", result["detail"], ok=False), status_code
    title = result.get("title") or "Done"
    msg = result.get("message_html") or ""
    return _html_page(title, msg), status_code


def process_approval_response(
    db: Session,
    *,
    approval_id: int,
    token: str,
    action: str,
    actor_id: Optional[int] = None,
    as_json: bool = False,
):
    """
    Handle approve/reject link. By default returns (html_body, http_status) for backward compat.
    With `as_json=True`, returns (dict, http_status) suitable for JSON responses.
    `actor_id` must match the assigned approver to defeat token replay.
    """
    result, status_code = _execute_approval(
        db,
        approval_id=approval_id,
        token=token,
        action=action,
        actor_id=actor_id,
    )
    if as_json:
        return result, status_code
    return _result_to_html(result, status_code)


def send_group_delete_approval_for_purpose(
    db: Session,
    *,
    purpose: str,
    recipient_user_id: int,
    actor: CurrentUser,
    request_base_url: Optional[str] = None,
) -> dict:
    group_id = _parse_group_id(purpose)
    group = db.query(UserGroup).filter(UserGroup.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found.")
    approver = resolve_otp_recipient(db, group.org_id, recipient_user_id, actor)
    return create_and_send_group_delete_approval(
        db,
        group_id=group_id,
        approver=approver,
        requester=actor,
        request_base_url=request_base_url,
    )
