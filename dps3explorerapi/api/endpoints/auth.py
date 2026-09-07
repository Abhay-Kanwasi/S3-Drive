"""
Google OAuth / JWT session endpoints.

POST /auth/google   — exchange Google credential for session cookies
POST /auth/refresh  — rotate access token using refresh cookie
POST /auth/logout   — clear session cookies
GET  /auth/me       — return current session user
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core.auth import (
    ACCESS_COOKIE,
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
from db.models import User
from db.postgresdb import get_db

logger = logging.getLogger(__name__)
router = APIRouter()


class GoogleLoginRequest(BaseModel):
    credential: str


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


@router.post("/google")
def google_login(payload: GoogleLoginRequest, response: Response, db: Session = Depends(get_db)):
    claims = _verify_google_credential(payload.credential)
    google_sub: str = claims["sub"]
    email: str = claims["email"].lower()

    # Fast path: already linked by subject
    user = db.query(User).filter(User.google_subject == google_sub).first()

    if user is None:
        # First login: link by verified email
        user = db.query(User).filter(User.email == email).first()
        _load_and_validate_user(db, user)
        # Link the Google subject to this account
        try:
            user.google_subject = google_sub
            db.commit()
            db.refresh(user)
        except IntegrityError:
            db.rollback()
            # Another request won the race — re-fetch
            user = db.query(User).filter(User.google_subject == google_sub).first()
            _load_and_validate_user(db, user)
    else:
        _load_and_validate_user(db, user)

    set_auth_cookies(response, user.id)
    current = _user_to_current(db, user)
    return {
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
