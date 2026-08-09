"""
OTP generation, storage (bcrypt hash), verification, and email delivery.
"""

import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import bcrypt
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from core.auth import (
    CurrentUser,
    ROLE_ADMIN,
    ROLE_LABELS,
    UAMUser,
)
from core.config import settings
from core.smtp_email import send_smtp_html, smtp_configured
from db.models import AdminOtpChallenge, Organization
from models.email_templates.otp import otp_email_body

logger = logging.getLogger(__name__)

DEFAULT_PURPOSE = "sensitive_action"
OTP_LENGTH = 6
def group_delete_purpose(group_id: int) -> str:
    return f"group_delete:{group_id}"


def _approver_dict(u: UAMUser, *, is_onboarder: bool = False) -> dict:
    return {
        "id": u.id,
        "user_name": u.user_name or "",
        "email": u.email or "",
        "role_id": u.role,
        "role_label": ROLE_LABELS.get(u.role, "user"),
        "is_onboarder": is_onboarder,
    }


def list_otp_approvers(db: Session, org_id: int, actor: CurrentUser) -> List[dict]:
    """Organization admins for this org + the user who onboarded it (not all global master admins)."""
    org = db.query(Organization).filter(Organization.id == org_id, Organization.is_active == True).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found.")

    if actor.role_id == ROLE_ADMIN and actor.subscription_id != org.subscription_id:
        raise HTTPException(status_code=403, detail="Organization is outside your scope.")

    seen: set[int] = set()
    result: List[dict] = []

    if org.onboarded_by:
        onboarder = (
            db.query(UAMUser)
            .filter(
                UAMUser.id == org.onboarded_by,
                UAMUser.active == True,
                UAMUser.email.isnot(None),
                UAMUser.email != "",
            )
            .first()
        )
        if onboarder:
            seen.add(onboarder.id)
            result.append(_approver_dict(onboarder, is_onboarder=True))

    org_admins = (
        db.query(UAMUser)
        .filter(
            UAMUser.active == True,
            UAMUser.role == ROLE_ADMIN,
            UAMUser.subscription_id == org.subscription_id,
            UAMUser.email.isnot(None),
            UAMUser.email != "",
        )
        .order_by(UAMUser.user_name, UAMUser.id)
        .all()
    )
    for u in org_admins:
        if u.id not in seen:
            seen.add(u.id)
            result.append(_approver_dict(u, is_onboarder=False))

    return result


def resolve_otp_recipient(
    db: Session, org_id: int, recipient_user_id: int, actor: CurrentUser
) -> UAMUser:
    approvers = {a["id"]: a for a in list_otp_approvers(db, org_id, actor)}
    if recipient_user_id not in approvers:
        raise HTTPException(
            status_code=400,
            detail="Invalid approver. Choose the org onboarding admin or an org admin for this organization.",
        )
    user = db.query(UAMUser).filter(UAMUser.id == recipient_user_id).first()
    if not user or not user.email:
        raise HTTPException(status_code=400, detail="Approver has no email address.")
    return user


def _mask_email(email: str) -> str:
    if not email or "@" not in email:
        return "***"
    local, domain = email.split("@", 1)
    if len(local) <= 1:
        masked_local = "*"
    else:
        masked_local = local[0] + "***"
    return f"{masked_local}@{domain}"


def _purpose_label(purpose: str) -> str:
    if purpose == DEFAULT_PURPOSE:
        return ""
    if purpose.startswith("group_delete:"):
        return " (group deletion)"
    return f" ({purpose.replace('_', ' ')})"


def _generate_code() -> str:
    return "".join(secrets.choice("0123456789") for _ in range(OTP_LENGTH))


def _hash_code(code: str) -> str:
    return bcrypt.hashpw(code.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _check_code(code: str, code_hash: str) -> bool:
    try:
        return bcrypt.checkpw(code.encode("utf-8"), code_hash.encode("utf-8"))
    except ValueError:
        return False


def invalidate_pending(db: Session, user_id: int, purpose: str) -> None:
    now = datetime.now(timezone.utc)
    (
        db.query(AdminOtpChallenge)
        .filter(
            AdminOtpChallenge.user_id == user_id,
            AdminOtpChallenge.purpose == purpose,
            AdminOtpChallenge.used_at.is_(None),
            AdminOtpChallenge.expires_at > now,
        )
        .update({AdminOtpChallenge.used_at: now}, synchronize_session=False)
    )


def create_and_send_otp(
    db: Session,
    *,
    user_id: int,
    email: str,
    user_name: Optional[str],
    purpose: str = DEFAULT_PURPOSE,
    requested_by: Optional[str] = None,
) -> dict:
    """
    Invalidate prior codes for this user+purpose, store new bcrypt hash, send email.
    Returns metadata for API response. Caller must commit.
    """
    if not smtp_configured():
        raise RuntimeError(
            "SMTP is not configured. Set SMTP_HOST, SMTP_USERNAME, SMTP_PASSWORD, and PORT in .env"
        )

    code = _generate_code()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.OTP_VALID_MINUTES)

    invalidate_pending(db, user_id, purpose)

    row = AdminOtpChallenge(
        user_id=user_id,
        purpose=purpose,
        code_hash=_hash_code(code),
        expires_at=expires_at,
    )
    db.add(row)
    db.flush()

    greeting = f" {user_name}" if user_name else ""
    requested_line = ""
    if requested_by:
        requested_line = (
            f"<p style=\"color:#666;font-size:13px;\">"
            f"Requested by <strong>{requested_by}</strong> for your approval.</p>"
        )
    html = otp_email_body.format(
        greeting=greeting,
        action_label=_purpose_label(purpose),
        code=code,
        valid_minutes=settings.OTP_VALID_MINUTES,
        requested_line=requested_line,
    )
    send_smtp_html(
        to_email=email,
        subject="S3 Explorer — Verification Code",
        html_body=html,
    )

    return {
        "sent": True,
        "expires_in_seconds": settings.OTP_VALID_MINUTES * 60,
        "masked_email": _mask_email(email),
        "purpose": purpose,
    }


def verify_otp(
    db: Session,
    *,
    user_id: int,
    code: str,
    purpose: str = DEFAULT_PURPOSE,
    consume: bool = True,
) -> bool:
    """Return True if code matches a valid, unexpired challenge for user+purpose."""
    if not code or not code.strip().isdigit() or len(code.strip()) != OTP_LENGTH:
        return False

    normalized = code.strip()
    now = datetime.now(timezone.utc)

    rows = (
        db.query(AdminOtpChallenge)
        .filter(
            AdminOtpChallenge.user_id == user_id,
            AdminOtpChallenge.purpose == purpose,
            AdminOtpChallenge.used_at.is_(None),
            AdminOtpChallenge.expires_at > now,
        )
        .order_by(AdminOtpChallenge.created_at.desc())
        .all()
    )

    for row in rows:
        if _check_code(normalized, row.code_hash):
            if consume:
                row.used_at = now
                db.flush()
            return True
    return False
