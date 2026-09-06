"""
JWT cookie-based identity + role-based authorization.

Sessions are issued as HttpOnly cookies after Google OAuth verification.
Access tokens are short-lived; refresh tokens support rotation.
"""

from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import Depends, HTTPException, Request, status
from jose import JWTError, jwt
from pydantic import BaseModel, computed_field
from sqlalchemy.orm import Session

from core.config import settings
from core.user_access import is_s3_deactivated
from db.models import Organization, User
from db.postgresdb import get_db

logger = logging.getLogger(__name__)

# Role constants
ROLE_ADMIN = 1
ROLE_USER = 2
ROLE_MASTER_ADMIN = 3
ROLE_SUPER_ADMIN = 4

ROLE_LABELS = {
    ROLE_ADMIN: "admin",
    ROLE_USER: "user",
    ROLE_MASTER_ADMIN: "master_admin",
    ROLE_SUPER_ADMIN: "super_admin",
}

ADMIN_ROLE_IDS = {ROLE_ADMIN, ROLE_MASTER_ADMIN, ROLE_SUPER_ADMIN}
GLOBAL_ADMIN_ROLE_IDS = {ROLE_MASTER_ADMIN, ROLE_SUPER_ADMIN}

ACCESS_COOKIE = "s3exp_access"
REFRESH_COOKIE = "s3exp_refresh"
CSRF_COOKIE = "s3exp_csrf"


class CurrentUser(BaseModel):
    """Lightweight auth context passed to endpoint handlers."""

    id: int
    email: str
    user_name: Optional[str] = None
    role_id: int
    role_label: str
    organization_id: Optional[int] = None
    org_key: Optional[str] = None
    is_admin: bool = False

    @computed_field  # type: ignore[prop-decorator]
    @property
    def subscription_id(self) -> Optional[str]:
        """Compat alias — formerly UAM subscription_id, now org_key."""
        return self.org_key

    class Config:
        from_attributes = True


def _resolve_org_key(db: Session, organization_id: Optional[int]) -> Optional[str]:
    if not organization_id:
        return None
    org = (
        db.query(Organization.org_key)
        .filter(Organization.id == organization_id)
        .first()
    )
    return org[0] if org else None


def _user_to_current(db: Session, user: User) -> CurrentUser:
    role_id = int(user.role or ROLE_USER)
    return CurrentUser(
        id=int(user.id),
        email=user.email or "",
        user_name=user.username,
        role_id=role_id,
        role_label=ROLE_LABELS.get(role_id, "user"),
        organization_id=user.organization_id,
        org_key=_resolve_org_key(db, user.organization_id),
        is_admin=role_id in ADMIN_ROLE_IDS,
    )


# ── JWT helpers ──────────────────────────────────────────────────────────────

def create_access_token(user_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    return jwt.encode(
        {"sub": str(user_id), "exp": expire, "type": "access"},
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


def create_refresh_token(user_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        days=settings.REFRESH_TOKEN_EXPIRE_DAYS
    )
    return jwt.encode(
        {"sub": str(user_id), "exp": expire, "type": "refresh"},
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


def _decode_token(token: str, expected_type: str) -> int:
    """Decode and validate a JWT; return user_id or raise 401."""
    try:
        payload = jwt.decode(
            token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    if payload.get("type") != expected_type:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Wrong token type")
    sub = payload.get("sub")
    if not sub:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    return int(sub)


def _cookie_kwargs(max_age: int) -> dict:
    return {
        "httponly": True,
        "secure": settings.COOKIE_SECURE,
        "samesite": settings.COOKIE_SAMESITE,
        "max_age": max_age,
    }


def set_auth_cookies(response, user_id: int) -> None:
    access = create_access_token(user_id)
    refresh = create_refresh_token(user_id)
    response.set_cookie(
        ACCESS_COOKIE, access,
        **_cookie_kwargs(settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60),
    )
    response.set_cookie(
        REFRESH_COOKIE, refresh,
        **_cookie_kwargs(settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400),
    )
    response.set_cookie(
        CSRF_COOKIE,
        secrets.token_urlsafe(32),
        httponly=False,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
    )


def clear_auth_cookies(response) -> None:
    response.delete_cookie(ACCESS_COOKIE)
    response.delete_cookie(REFRESH_COOKIE)
    response.delete_cookie(CSRF_COOKIE)


# ── Dependency ───────────────────────────────────────────────────────────────

async def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> CurrentUser:
    """Resolve the caller from the HttpOnly access cookie."""
    token = request.cookies.get(ACCESS_COOKIE)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    user_id = _decode_token(token, "access")
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    if not user.active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User account is deactivated")

    if is_s3_deactivated(db, user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated in S3 Explorer",
        )

    current = _user_to_current(db, user)
    request.state.current_user = current
    request.state.db = db
    return current


def require_role(allowed_roles: List[str]):
    """Dependency factory that enforces role-based access."""

    async def _check(user: CurrentUser = Depends(get_current_user)):
        if user.role_label not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires one of: {', '.join(allowed_roles)}",
            )
        return user

    return _check
