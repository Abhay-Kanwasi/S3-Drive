"""
Un-onboard org (4-eyes): requester OTP in app, approver email approve/reject.
"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from core.auth import CurrentUser, require_role
from core.smtp_email import smtp_configured
from core.unonboard import (
    create_unonboard_request,
    list_master_admin_approvers,
    send_requester_otp,
)
from db.postgresdb import get_db

router = APIRouter()

UNONBOARD_ROLES = ["master_admin", "super_admin"]


class ApproverOut(BaseModel):
    id: int
    user_name: str
    email: str
    role_id: int
    role_label: str


class UnonboardRequestBody(BaseModel):
    approver_user_id: int
    otp_code: str = Field(..., min_length=6, max_length=6)

    @field_validator("otp_code")
    @classmethod
    def digits_only(cls, v: str) -> str:
        if not v.isdigit():
            raise ValueError("OTP must be 6 digits")
        return v


class UnonboardRequestOut(BaseModel):
    request_id: int
    org_id: int
    org_name: str
    status: str
    expires_at: str
    approver_email_masked: str


@router.get("/unonboard/approvers", response_model=List[ApproverOut])
async def get_unonboard_approvers(
    user: CurrentUser = Depends(require_role(UNONBOARD_ROLES)),
    db: Session = Depends(get_db),
):
    """Other master/super admins who may approve an un-onboard request."""
    return list_master_admin_approvers(db, user)


@router.post("/orgs/{org_id}/unonboard/send-otp")
async def send_unonboard_otp(
    org_id: int,
    request: Request,
    user: CurrentUser = Depends(require_role(UNONBOARD_ROLES)),
    db: Session = Depends(get_db),
):
    """Email a 6-digit OTP to the requesting master admin."""
    if not smtp_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SMTP is not configured.",
        )
    try:
        result = send_requester_otp(db, org_id=org_id, requester=user)
        db.commit()
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e

    from core.audit import audit_log

    audit_log(
        user_id=user.id,
        event_type="ORG_UNONBOARD_OTP_SENT",
        target_key=f"org:{org_id}",
        org_id=org_id,
        details={"masked_email": result.get("masked_email")},
        request=request,
    )
    return result


@router.post("/orgs/{org_id}/unonboard/request", response_model=UnonboardRequestOut)
async def submit_unonboard_request(
    org_id: int,
    body: UnonboardRequestBody,
    request: Request,
    user: CurrentUser = Depends(require_role(UNONBOARD_ROLES)),
    db: Session = Depends(get_db),
):
    """Verify requester OTP and email the approver approve/reject links."""
    if not smtp_configured():
        raise HTTPException(status_code=503, detail="SMTP is not configured.")
    try:
        result = create_unonboard_request(
            db,
            org_id=org_id,
            approver_user_id=body.approver_user_id,
            otp_code=body.otp_code,
            requester=user,
            request_base_url=str(request.base_url),
        )
        db.commit()
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e

    from core.audit import audit_log

    audit_log(
        user_id=user.id,
        event_type="ORG_UNONBOARD_INITIATED",
        target_key=f"org:{org_id}",
        org_id=org_id,
        org_name=result.get("org_name"),
        details={
            "request_id": result["request_id"],
            "approver_user_id": body.approver_user_id,
        },
        request=request,
    )
    return UnonboardRequestOut(**result)
