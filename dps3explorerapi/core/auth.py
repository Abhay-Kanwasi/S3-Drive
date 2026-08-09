"""
Temporary header-based identity + role-based authorization.

TEMPORARY stand-in for real auth: when DEV_AUTH_MODE is true (default),
identity is resolved from the X-User-Id header against the owned `users`
table. Anyone who can set the header can impersonate — internal/dev only.
Replace with real authentication before any public deployment.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, computed_field
from sqlalchemy.orm import Session

from core.config import settings
from core.user_access import is_s3_deactivated
from db.models import Organization, User
from db.postgresdb import get_db

logger = logging.getLogger(__name__)

# Role constants (same integers as before)
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


async def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
) -> CurrentUser:
    """
    Resolve the caller from X-User-Id against owned users.

    TEMPORARY: gated by settings.DEV_AUTH_MODE. Replace with real auth later.
    """
    if not settings.DEV_AUTH_MODE:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="DEV_AUTH_MODE is disabled; real auth is not configured yet",
        )

    if not x_user_id or not str(x_user_id).strip().isdigit():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid X-User-Id header",
        )

    user_id = int(str(x_user_id).strip())
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
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
