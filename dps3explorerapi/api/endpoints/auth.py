"""
Google OAuth / JWT session endpoints.

POST /auth/google   — exchange Google credential for session cookies
POST /auth/refresh  — rotate access token using refresh cookie
POST /auth/logout   — clear session cookies
GET  /auth/me       — return current session user
GET  /auth/orgs     — list active orgs for onboarding picker
POST /auth/onboard  — complete self-registration via onboarding token
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from jose import JWTError, jwt
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core.auth import (
    REFRESH_COOKIE,
    CurrentUser,
    _decode_token,
    _user_to_current,
    clear_auth_cookies,
    get_current_user,
    set_auth_cookies,
)
from core.config import settings
from core.user_access import is_s3_deactivated
from db.models import Organization, User
from db.postgresdb import get_db

logger = logging.getLogger(__name__)
router = APIRouter()

ONBOARD_TOKEN_EXPIRE_MINUTES = 30
GUEST_ORG_KEY = "guest_organization"


class GoogleLoginRequest(BaseModel):
    credential: str


class OnboardRequest(BaseModel):
    onboard_token: str
    username: str
    organization_id: Optional[int] = None


def _verify_google_credential(credential: str) -> dict:
    """Verify Google ID token and return its claims."""
    if not settings.GOOGLE_CLIENT_ID:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Google authentication is not configured",
        )
    try:
        claims = id_token.verify_oauth2_token(
            credential,
            google_requests.Request(),
            settings.GOOGLE_CLIENT_ID,
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Google credential",
        )
    if claims.get("iss") not in {"accounts.google.com", "https://accounts.google.com"}:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Google issuer")
    if not claims.get("sub") or not claims.get("email"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Google credential is incomplete")
    if not claims.get("email_verified"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Google email is not verified",
        )
    return claims


def _load_and_validate_user(db: Session, user: Optional[User]) -> User:
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No account found for this Google account. Contact your administrator.",
        )
    if not user.active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated",
        )
    if is_s3_deactivated(db, user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated in S3 Explorer",
        )
    return user


def _create_onboard_token(email: str, google_sub: str, name: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=ONBOARD_TOKEN_EXPIRE_MINUTES)
    return jwt.encode(
        {"sub": google_sub, "email": email, "name": name, "exp": expire, "type": "onboard"},
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


def _decode_onboard_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired onboarding token")
    if payload.get("type") != "onboard":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Wrong token type")
    return payload


def _get_or_create_guest_org(db: Session) -> Organization:
    org = db.query(Organization).filter(Organization.org_key == GUEST_ORG_KEY).first()
    if not org:
        org = Organization(org_key=GUEST_ORG_KEY, org_name="Guest Organization", is_active=True)
        db.add(org)
        db.flush()
    return org


@router.post("/google")
def google_login(payload: GoogleLoginRequest, response: Response, db: Session = Depends(get_db)):
    claims = _verify_google_credential(payload.credential)
    google_sub: str = claims["sub"]
    email: str = claims["email"].lower()
    name: str = claims.get("given_name") or claims.get("name") or ""

    user = db.query(User).filter(User.google_subject == google_sub).first()

    if user is None:
        user = db.query(User).filter(User.email == email).first()
        if user is None:
            onboard_token = _create_onboard_token(email, google_sub, name)
            return {
                "needs_onboarding": True,
                "onboard_token": onboard_token,
                "email": email,
                "name": name,
            }

        _load_and_validate_user(db, user)
        try:
            user.google_subject = google_sub
            db.commit()
            db.refresh(user)
        except IntegrityError:
            db.rollback()
            user = db.query(User).filter(User.google_subject == google_sub).first()
            _load_and_validate_user(db, user)
    else:
        _load_and_validate_user(db, user)

    set_auth_cookies(response, user.id)
    current = _user_to_current(db, user)
    return {
        "needs_onboarding": False,
        "id": current.id,
        "email": current.email,
        "user_name": current.user_name,
        "role_label": current.role_label,
        "is_admin": current.is_admin,
        "org_key": current.org_key,
    }


@router.get("/orgs")
def list_orgs_for_onboarding(db: Session = Depends(get_db)):
    """Public endpoint — returns active orgs for the onboarding picker."""
    orgs = (
        db.query(Organization.id, Organization.org_name)
        .filter(Organization.is_active.is_(True), Organization.org_key != GUEST_ORG_KEY)
        .order_by(Organization.org_name)
        .all()
    )
    return [{"id": org.id, "org_name": org.org_name} for org in orgs]


@router.post("/onboard")
def onboard_user(payload: OnboardRequest, response: Response, db: Session = Depends(get_db)):
    """Complete self-registration. Verifies onboard token, creates user, sets session."""
    claims = _decode_onboard_token(payload.onboard_token)
    email: str = claims["email"]
    google_sub: str = claims["sub"]

    username = payload.username.strip()
    if not username:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="username is required")

    existing = db.query(User).filter(User.email == email).first()
    if existing:
        _load_and_validate_user(db, existing)
        if not existing.google_subject:
            existing.google_subject = google_sub
            db.commit()
            db.refresh(existing)
        set_auth_cookies(response, existing.id)
        current = _user_to_current(db, existing)
        return {
            "needs_onboarding": False,
            "id": current.id,
            "email": current.email,
            "user_name": current.user_name,
            "role_label": current.role_label,
            "is_admin": current.is_admin,
            "org_key": current.org_key,
        }

    if payload.organization_id:
        org = db.query(Organization).filter(Organization.id == payload.organization_id, Organization.is_active.is_(True)).first()
        if not org:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Selected organization not found or inactive")
    else:
        org = _get_or_create_guest_org(db)

    user = User(
        username=username,
        email=email,
        google_subject=google_sub,
        role=2,
        organization_id=org.id,
        active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    set_auth_cookies(response, user.id)
    current = _user_to_current(db, user)
    return {
        "needs_onboarding": False,
        "id": current.id,
        "email": current.email,
        "user_name": current.user_name,
        "role_label": current.role_label,
        "is_admin": current.is_admin,
        "org_key": current.org_key,
    }


@router.post("/refresh")
def refresh_session(request: Request, response: Response, db: Session = Depends(get_db)):
    token = request.cookies.get(REFRESH_COOKIE)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No refresh token")

    user_id = _decode_token(token, "refresh")
    user = db.query(User).filter(User.id == user_id).first()
    _load_and_validate_user(db, user)

    set_auth_cookies(response, user_id)
    return {"ok": True}


@router.post("/logout")
def logout(response: Response):
    clear_auth_cookies(response)
    return {"ok": True}


@router.get("/me")
def auth_me(user: CurrentUser = Depends(get_current_user)):
    return {
        "id": user.id,
        "email": user.email,
        "user_name": user.user_name,
        "role_label": user.role_label,
        "is_admin": user.is_admin,
        "org_key": user.org_key,
    }
