"""
Email approve/reject for sensitive admin actions.

- GET  /admin/approval/respond — legacy HTML review page (no state change; safe for email prefetch)
- POST /admin/approval/respond — JSON confirm; requires signed-in approver (Bearer)
- GET  /admin/approval/review  — JSON review (signed-in approver only)
"""

from pydantic import BaseModel, Field, ValidationError

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session

from core.approval import (
    build_approval_confirmation_page,
    build_approval_review_payload,
    process_approval_response,
)
from core.auth import CurrentUser, get_current_user
from db.postgresdb import get_db

router = APIRouter()


class ApprovalRespondBody(BaseModel):
    id: int = Field(..., ge=1)
    token: str = Field(..., min_length=16)
    action: str = Field(..., pattern="^(approve|reject)$")


@router.get("/approval/respond")
async def review_approval_html(
    request: Request,
    id: int = Query(..., alias="id", ge=1),
    token: str = Query(..., min_length=16),
    action: str = Query(..., pattern="^(approve|reject)$"),
    db: Session = Depends(get_db),
):
    """Legacy: HTML preview page. Kept for environments without APPROVAL_FRONTEND_URL."""
    html, status_code = build_approval_confirmation_page(
        db,
        approval_id=id,
        token=token,
        action=action,
        request_base_url=str(request.base_url),
    )
    return HTMLResponse(content=html, status_code=status_code)


@router.get("/approval/review")
async def review_approval_json(
    id: int = Query(..., ge=1),
    token: str = Query(..., min_length=16),
    action: str = Query(..., pattern="^(approve|reject)$"),
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """JSON review for the SPA confirmation page. Approver must be signed in."""
    payload, status_code = build_approval_review_payload(
        db,
        approval_id=id,
        token=token,
        action=action,
        actor_id=user.id,
    )
    if status_code != 200:
        raise HTTPException(status_code=status_code, detail=payload.get("detail", "Approval link invalid"))
    return payload


@router.post("/approval/respond")
async def confirm_approval(
    request: Request,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Execute approve/reject. Requires the assigned approver to be signed in.

    Accepts either:
    - `application/json` body `{id, token, action}` (preferred; used by the SPA)
    - `application/x-www-form-urlencoded` form (legacy HTML page)

    Returns JSON for JSON requests, HTML for form submissions.
    """
    content_type = (request.headers.get("content-type") or "").lower()
    is_json_request = content_type.startswith("application/json")

    if is_json_request:
        try:
            raw = await request.json()
        except Exception as exc:
            raise HTTPException(status_code=400, detail="Invalid JSON body.") from exc
        return_json = True
    else:
        form = await request.form()
        raw = {k: form.get(k) for k in ("id", "token", "action")}
        return_json = "application/json" in (request.headers.get("accept") or "")

    try:
        body = ApprovalRespondBody.model_validate(raw)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc

    payload, status_code = process_approval_response(
        db,
        approval_id=body.id,
        token=body.token,
        action=body.action,
        actor_id=user.id,
        as_json=return_json,
    )
    if return_json:
        return JSONResponse(content=payload, status_code=status_code)
    return HTMLResponse(content=payload, status_code=status_code)
