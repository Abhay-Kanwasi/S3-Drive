"""
S3 Explorer domain models — explorer schema.
"""

from datetime import datetime
from sqlalchemy import (
    Column, Integer, BigInteger, String, Boolean, DateTime, JSON,
    ForeignKey, Identity, UniqueConstraint, func, text,
)
from sqlalchemy.orm import relationship
from db.postgresdb import Base
from core.config import settings

SCHEMA = settings.DB_SCHEMA


class Organization(Base):
    """One row per onboarded organization / S3 bucket binding."""
    __tablename__ = "organizations"
    __table_args__ = {"schema": SCHEMA}

    id                    = Column(BigInteger, Identity(start=1), primary_key=True)
    org_key               = Column(String(255), nullable=False, unique=True, index=True)
    org_name              = Column(String(255), nullable=False)
    bucket_name           = Column(String(255), unique=True, nullable=True)
    region                = Column(String(63),  nullable=False, server_default=text("'us-east-1'"))
    max_upload_size_bytes = Column(BigInteger,   nullable=False, server_default=text("5368709120"))
    onboarded_by          = Column(BigInteger,   ForeignKey(f"{SCHEMA}.users.id", ondelete="SET NULL"), nullable=True)
    is_active             = Column(Boolean,      nullable=False, server_default=text("true"))
    onboarded_at          = Column(DateTime(timezone=True), nullable=True)
    created_at            = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at            = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class User(Base):
    """Owned identity. role: 1=admin 2=user 3=master_admin 4=super_admin."""
    __tablename__ = "users"
    __table_args__ = {"schema": SCHEMA}

    id              = Column(BigInteger, Identity(start=1), primary_key=True)
    username        = Column(String(255), nullable=False)
    email           = Column(String(255), nullable=False, unique=True, index=True)
    role            = Column(Integer, nullable=False, server_default=text("2"))
    organization_id = Column(BigInteger, ForeignKey(f"{SCHEMA}.organizations.id", ondelete="SET NULL"), nullable=True, index=True)
    active          = Column(Boolean, nullable=False, server_default=text("true"))
    created_at      = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at      = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class FolderMetadata(Base):
    """Tracks who created each folder for ownership-based permission rules."""
    __tablename__ = "s3_folder_metadata"
    __table_args__ = {"schema": SCHEMA}

    id              = Column(BigInteger, Identity(start=1), primary_key=True)
    org_id          = Column(BigInteger, ForeignKey(f"{SCHEMA}.organizations.id"), nullable=False, index=True)
    key             = Column(String(1024), nullable=False)
    created_by      = Column(BigInteger, ForeignKey(f"{SCHEMA}.users.id"), nullable=False)
    created_by_role = Column(String(20), nullable=False)
    created_at      = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class UserGroup(Base):
    """Permission group scoped to an org."""
    __tablename__ = "s3_user_group"
    __table_args__ = (
        UniqueConstraint("org_id", "name", name="uq_group_org_name"),
        {"schema": SCHEMA},
    )

    id                       = Column(BigInteger, Identity(start=1), primary_key=True)
    org_id                   = Column(BigInteger, ForeignKey(f"{SCHEMA}.organizations.id"), nullable=False, index=True)
    name                     = Column(String(255), nullable=False)
    created_by               = Column(BigInteger, ForeignKey(f"{SCHEMA}.users.id"), nullable=False)
    requires_delete_approval = Column(Boolean, nullable=False, server_default=text("false"))
    created_at               = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at               = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    org     = relationship("Organization", backref="groups", lazy="joined")
    members = relationship("GroupMembership", back_populates="group", cascade="all, delete-orphan")
    grants  = relationship("FolderGrant",     back_populates="group", cascade="all, delete-orphan")


class GroupMembership(Base):
    """Links users to groups."""
    __tablename__ = "s3_group_membership"
    __table_args__ = (
        UniqueConstraint("group_id", "user_id", name="uq_group_user"),
        {"schema": SCHEMA},
    )

    id       = Column(BigInteger, Identity(start=1), primary_key=True)
    group_id = Column(BigInteger, ForeignKey(f"{SCHEMA}.s3_user_group.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id  = Column(BigInteger, ForeignKey(f"{SCHEMA}.users.id"), nullable=False, index=True)
    added_by = Column(BigInteger, ForeignKey(f"{SCHEMA}.users.id"), nullable=False)
    added_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    group = relationship("UserGroup", back_populates="members")


class FolderGrant(Base):
    """Maps a group to a folder prefix with an access level."""
    __tablename__ = "s3_folder_grant"
    __table_args__ = (
        UniqueConstraint("group_id", "prefix", name="uq_grant_group_prefix"),
        {"schema": SCHEMA},
    )

    id           = Column(BigInteger, Identity(start=1), primary_key=True)
    group_id     = Column(BigInteger, ForeignKey(f"{SCHEMA}.s3_user_group.id", ondelete="CASCADE"), nullable=False, index=True)
    org_id       = Column(BigInteger, ForeignKey(f"{SCHEMA}.organizations.id"), nullable=False, index=True)
    prefix       = Column(String(1024), nullable=False)
    access_level = Column(String(20), nullable=False, server_default=text("'read'"))
    created_by   = Column(BigInteger, ForeignKey(f"{SCHEMA}.users.id"), nullable=False)
    created_at   = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    group = relationship("UserGroup", back_populates="grants")
    org   = relationship("Organization")


class S3UserDeactivation(Base):
    """Explorer-scoped deactivation only (separate from users.active)."""
    __tablename__ = "s3_user_deactivation"
    __table_args__ = {"schema": SCHEMA}

    user_id        = Column(BigInteger, ForeignKey(f"{SCHEMA}.users.id"), primary_key=True)
    deactivated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    deactivated_by = Column(BigInteger, ForeignKey(f"{SCHEMA}.users.id"), nullable=False)


class AdminOtpChallenge(Base):
    """Hashed OTP for sensitive admin actions."""
    __tablename__ = "s3_admin_otp"
    __table_args__ = {"schema": SCHEMA}

    id         = Column(BigInteger, Identity(start=1), primary_key=True)
    user_id    = Column(BigInteger, ForeignKey(f"{SCHEMA}.users.id"), nullable=False, index=True)
    purpose    = Column(String(64),  nullable=False, server_default=text("'sensitive_action'"))
    code_hash  = Column(String(255), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used_at    = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class UnonboardRequest(Base):
    """4-eyes workflow to remove an onboarded org binding."""
    __tablename__ = "s3_unonboard_request"
    __table_args__ = {"schema": SCHEMA}

    id                = Column(BigInteger, Identity(start=1), primary_key=True)
    org_id            = Column(BigInteger, ForeignKey(f"{SCHEMA}.organizations.id", ondelete="SET NULL"), nullable=True, index=True)
    org_name          = Column(String(255), nullable=True)
    bucket_name       = Column(String(255), nullable=True)
    org_key           = Column(String(255), nullable=True)
    requester_user_id = Column(BigInteger, ForeignKey(f"{SCHEMA}.users.id"), nullable=False)
    approver_user_id  = Column(BigInteger, ForeignKey(f"{SCHEMA}.users.id"), nullable=False)
    status            = Column(String(32), nullable=False, server_default=text("'pending_approval'"))
    expires_at        = Column(DateTime(timezone=True), nullable=False)
    resolved_at       = Column(DateTime(timezone=True), nullable=True)
    created_at        = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    org = relationship("Organization", lazy="joined")


class AdminApprovalRequest(Base):
    """Email approve/reject tokens for sensitive admin actions."""
    __tablename__ = "s3_admin_approval"
    __table_args__ = {"schema": SCHEMA}

    id                 = Column(BigInteger, Identity(start=1), primary_key=True)
    purpose            = Column(String(64),  nullable=False)
    requester_user_id  = Column(BigInteger, ForeignKey(f"{SCHEMA}.users.id"), nullable=False)
    approver_user_id   = Column(BigInteger, ForeignKey(f"{SCHEMA}.users.id"), nullable=False)
    approve_token_hash = Column(String(255), nullable=False)
    reject_token_hash  = Column(String(255), nullable=False)
    status             = Column(String(20),  nullable=False, server_default=text("'pending'"))
    expires_at         = Column(DateTime(timezone=True), nullable=False)
    resolved_at        = Column(DateTime(timezone=True), nullable=True)
    created_at         = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class UserNotification(Base):
    """In-app notifications for folder access grants and group membership."""
    __tablename__ = "s3_user_notification"
    __table_args__ = {"schema": SCHEMA}

    id         = Column(BigInteger, Identity(start=1), primary_key=True)
    user_id    = Column(BigInteger, ForeignKey(f"{SCHEMA}.users.id"), nullable=False, index=True)
    org_id     = Column(BigInteger, ForeignKey(f"{SCHEMA}.organizations.id"), nullable=False)
    type       = Column(String(50),  nullable=False)
    title      = Column(String(200), nullable=False)
    message    = Column(String(500), nullable=False)
    is_read    = Column(Boolean, nullable=False, server_default=text("false"))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class PlatformSettings(Base):
    """
    Global platform configuration (singleton row, id=1).
    Managed by MASTER_ADMIN via admin panel.
    """
    __tablename__ = "s3_platform_settings"
    __table_args__ = {"schema": SCHEMA}

    id = Column(Integer, primary_key=True, default=1)
    allowed_extensions = Column(JSON, nullable=False, server_default=text(
        """'[{"ext":".parquet","color":"#10b981"},{"ext":".orc","color":"#10b981"},{"ext":".csv","color":"#10b981"},{"ext":".json","color":"#f59e0b"},{"ext":".zip","color":"#8b5cf6"},{"ext":".gz","color":"#8b5cf6"},{"ext":".xlsx","color":"#10b981"},{"ext":".txt","color":"#3b82f6"},{"ext":".pdf","color":"#3b82f6"},{"ext":".docx","color":"#3b82f6"},{"ext":".png","color":"#ec4899"}]'"""
    ))
    max_upload_bytes = Column(BigInteger, nullable=False, server_default=text("5368709120"))  # 5GB
    updated_by = Column(Integer, nullable=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
