"""
JWT authentication and role-based authorization.

Validates tokens issued by UAM (shared JWT_SECRET_KEY, HS256).
Looks up user and role from the shared `datapoem.user_data` table.
"""

from typing import List, Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel
from sqlalchemy import Integer, String, Boolean
from sqlalchemy.orm import Session, Mapped, mapped_column

from core.config import settings
from core.user_access import is_s3_deactivated
from db.postgresdb import Base, get_db

SCHEMA = settings.DB_SCHEMA

bearer_scheme = HTTPBearer(auto_error=True)


# Read-only ORM mapping onto UAM's user_data table
class UAMUser(Base):
    __tablename__ = "user_data"
    __table_args__ = {"schema": SCHEMA, "extend_existing": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_name: Mapped[Optional[str]] = mapped_column("user_name", String(255))
    email: Mapped[Optional[str]] = mapped_column("email_id", String(255))
    role: Mapped[Optional[int]] = mapped_column("role", Integer)
    subscription_id: Mapped[Optional[str]] = mapped_column("subscription_id", String(255))
    active: Mapped[Optional[bool]] = mapped_column("active", Boolean)


# Read-only ORM mapping onto UAM's subscriber table
class UAMSubscriber(Base):
    __tablename__ = "subscriber"
    __table_args__ = {"schema": SCHEMA, "extend_existing": True}

    subscription_id: Mapped[str] = mapped_column("subscription_id", String(255), primary_key=True)
    name: Mapped[Optional[str]] = mapped_column("name", String(255))
    organization: Mapped[Optional[str]] = mapped_column("organization_name", String(255))
    active: Mapped[Optional[bool]] = mapped_column("active", Boolean)


# Role constants mirroring UAM
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

# Global admins can access any org (cross-org). Org admins (role 1) are org-scoped.
GLOBAL_ADMIN_ROLE_IDS = {ROLE_MASTER_ADMIN, ROLE_SUPER_ADMIN}


class CurrentUser(BaseModel):
    """Lightweight auth context passed to endpoint handlers."""
    id: int
    email: str
    user_name: Optional[str] = None
    role_id: int
    role_label: str
    subscription_id: Optional[str] = None
    is_admin: bool = False

    class Config:
        from_attributes = True


def _load_uam_user_from_token(token: str, db: Session) -> UAMUser:
    """Decode JWT and load UAM user. Raises HTTPException 401 only."""
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token_type = payload.get("type")
    if token_type != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("user_id")
    email = payload.get("email") or payload.get("sub")

    if user_id is None and email is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing user identity",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user: Optional[UAMUser] = None
    if user_id is not None:
        user = db.query(UAMUser).filter(UAMUser.id == user_id).first()
    if user is None and email is not None:
        user = db.query(UAMUser).filter(UAMUser.email == email).first()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> CurrentUser:
    """Decode UAM JWT and resolve user from shared DB."""
    user = _load_uam_user_from_token(credentials.credentials, db)

    if not user.active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated in UAM",
        )

    if is_s3_deactivated(db, user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated in S3 Explorer",
        )

    role_label = ROLE_LABELS.get(user.role, "user")

    current = CurrentUser(
        id=user.id,
        email=user.email or "",
        user_name=user.user_name,
        role_id=user.role or ROLE_USER,
        role_label=role_label,
        subscription_id=user.subscription_id,
        is_admin=user.role in ADMIN_ROLE_IDS,
    )

    request.state.current_user = current
    request.state.db = db
    return current


def require_role(allowed_roles: List[str]):
    """
    Dependency factory that enforces role-based access.

    Usage:
        @router.post("/admin/orgs/onboard",
                      dependencies=[Depends(require_role(["super_admin", "master_admin", "admin"]))])
    """
    async def _check(user: CurrentUser = Depends(get_current_user)):
        if user.role_label not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires one of: {', '.join(allowed_roles)}",
            )
        return user
    return _check
