"""
OTP for sensitive admin actions.

- GET  /admin/otp/approvers — org admins + master admins for dropdown
- POST /admin/otp/send      — email code (optional recipient_user_id for approver)
- POST /admin/otp/verify    — check code
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from core.auth import CurrentUser, ROLE_ADMIN, require_role
from core.approval import send_group_delete_approval_for_purpose
from core.otp import (
    DEFAULT_PURPOSE,
    create_and_send_otp,
    list_otp_approvers,
    verify_otp,
)
from core.smtp_email import smtp_configured
from db.models import Org, UserGroup
from db.postgresdb import get_db

router = APIRouter()

OTP_ROLES = ["admin", "master_admin", "super_admin"]


class ApproverOut(BaseModel):
    id: int
    user_name: str
    email: str
    role_id: int
    role_label: str
    is_onboarder: bool = False


class OtpSendRequest(BaseModel):
    purpose: str = Field(default=DEFAULT_PURPOSE)
    recipient_user_id: Optional[int] = Field(
        None,
        description="Approver who receives the code (org admin or master admin). Defaults to caller.",
    )

    @field_validator("purpose")
    @classmethod
    def validate_purpose(cls, v: str) -> str:
        base = v.split(":", 1)[0]
        if not base.replace("_", "").isalnum() or not base[0].isalpha():
            raise ValueError("Invalid purpose format")
        if len(v) > 64:
            raise ValueError("Purpose too long")
        return v


class OtpSendResponse(BaseModel):
    sent: bool
    expires_in_seconds: int
    masked_email: str
    purpose: str
    recipient_user_id: int
    approval_required: bool = False


class OtpVerifyRequest(BaseModel):
    code: str = Field(..., min_length=6, max_length=6)
    purpose: str = DEFAULT_PURPOSE
    approver_user_id: Optional[int] = Field(
        None,
        description="User who received the code (required when verifying on behalf of an approver).",
    )
    consume: bool = False

    @field_validator("code")
    @classmethod
    def digits_only(cls, v: str) -> str:
        if not v.isdigit():
            raise ValueError("Code must be 6 digits")
        return v


class OtpVerifyResponse(BaseModel):
    valid: bool


@router.get("/otp/approvers", response_model=List[ApproverOut])
async def get_otp_approvers(
    org_id: int = Query(..., description="Onboarded org id"),
    user: CurrentUser = Depends(require_role(OTP_ROLES)),
    db: Session = Depends(get_db),
):
    """List the org onboarding admin and org admins who may receive an OTP for this org."""
    return list_otp_approvers(db, org_id, user)


@router.post("/otp/send", response_model=OtpSendResponse)
async def send_otp(
    body: OtpSendRequest,
    request: Request,
    user: CurrentUser = Depends(require_role(OTP_ROLES)),
    db: Session = Depends(get_db),
):
    """Send OTP for generic actions, or approve/reject email for group_delete."""
    if not smtp_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SMTP is not configured. Set SMTP_HOST, SMTP_USERNAME, SMTP_PASSWORD, and PORT in .env",
        )

    recipient_id = body.recipient_user_id or user.id
    recipient_email = user.email
    recipient_name = user.user_name
    requested_by = None

    if body.purpose.startswith("group_delete:"):
        if not body.recipient_user_id:
            raise HTTPException(
                status_code=400,
                detail="recipient_user_id is required for group delete approval.",
            )
        try:
            group_id = int(body.purpose.split(":", 1)[1])
        except (IndexError, ValueError) as e:
            raise HTTPException(status_code=400, detail="Invalid group_delete purpose.") from e

        group = db.query(UserGroup).filter(UserGroup.id == group_id).first()
        if not group:
            raise HTTPException(status_code=404, detail="Group not found.")
        if user.role_id == ROLE_ADMIN and user.subscription_id:
            org_row = db.query(Org).filter(Org.id == group.org_id).first()
            if not org_row or org_row.subscription_id != user.subscription_id:
                raise HTTPException(status_code=403, detail="Group is outside your organization.")

        try:
            result = send_group_delete_approval_for_purpose(
                db,
                purpose=body.purpose,
                recipient_user_id=body.recipient_user_id,
                actor=user,
                request_base_url=str(request.base_url),
            )
            db.commit()
        except RuntimeError as e:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(e),
            ) from e
        return OtpSendResponse(**result)

    if body.recipient_user_id and body.recipient_user_id != user.id:
        raise HTTPException(
            status_code=400,
            detail="recipient_user_id is only supported for group_delete purposes.",
        )

    if not recipient_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Recipient has no email address; cannot send OTP.",
        )

    try:
        result = create_and_send_otp(
            db,
            user_id=recipient_id,
            email=recipient_email,
            user_name=recipient_name,
            purpose=body.purpose,
            requested_by=requested_by,
        )
        db.commit()
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e),
        ) from e

    return OtpSendResponse(**result, recipient_user_id=recipient_id)


@router.post("/otp/verify", response_model=OtpVerifyResponse)
async def verify_otp_endpoint(
    body: OtpVerifyRequest,
    user: CurrentUser = Depends(require_role(OTP_ROLES)),
    db: Session = Depends(get_db),
):
    """Verify a code for the approver who received it (approver_user_id) or the caller."""
    otp_user_id = body.approver_user_id or user.id
    valid = verify_otp(
        db,
        user_id=otp_user_id,
        code=body.code,
        purpose=body.purpose,
        consume=body.consume,
    )
    if body.consume and valid:
        db.commit()
    return OtpVerifyResponse(valid=valid)
