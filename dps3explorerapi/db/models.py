"""
S3 Explorer domain models.

Tables live in the schema configured by DB_SCHEMA (default: "datapoem").
UAM tables (user_data, subscriber) are read-only from this service.
"""

from datetime import datetime
from sqlalchemy import (
    Column, Integer, BigInteger, String, Boolean, DateTime, Index, JSON,
    ForeignKey, Identity, TIMESTAMP, UniqueConstraint, func, text,
)
from sqlalchemy.orm import relationship
from db.postgresdb import Base
from core.config import settings

SCHEMA = settings.DB_SCHEMA


# ---------------------------------------------------------------------------
# New tables for the multi-tenant S3 Explorer
# ---------------------------------------------------------------------------

class Org(Base):
    """
    One row per onboarded organization.
    Maps a UAM subscriber to an S3 bucket.
    """
    __tablename__ = "s3_org"
    __table_args__ = {"schema": SCHEMA}

    id = Column(Integer, Identity(start=1), primary_key=True, autoincrement=True)
    subscription_id = Column(String(255), nullable=False, unique=True, index=True)
    org_name = Column(String(255), nullable=False)
    bucket_name = Column(String(255), nullable=False, unique=True)
    region = Column(String(63), nullable=False, server_default=text("'us-east-1'"))
    max_upload_size_bytes = Column(BigInteger, nullable=False, server_default=text("5368709120"))
    is_active = Column(Boolean, nullable=False, server_default=text("true"))
    onboarded_by = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class FolderMetadata(Base):
    """Tracks who created each folder for ownership-based permission rules."""
    __tablename__ = "s3_folder_metadata"
    __table_args__ = {"schema": SCHEMA}

    id = Column(Integer, Identity(start=1), primary_key=True, autoincrement=True)
    org_id = Column(Integer, ForeignKey(f"{SCHEMA}.s3_org.id"), nullable=False, index=True)
    key = Column(String(1024), nullable=False)
    created_by = Column(Integer, nullable=False)
    created_by_role = Column(String(20), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class UserGroup(Base):
    """
    Permission group scoped to an org.
    Name is always dp- prefixed (enforced by API, not DB).
    """
    __tablename__ = "s3_user_group"
    __table_args__ = (
        UniqueConstraint("org_id", "name", name="uq_group_org_name"),
        {"schema": SCHEMA},
    )

    id = Column(Integer, Identity(start=1), primary_key=True, autoincrement=True)
    org_id = Column(Integer, ForeignKey(f"{SCHEMA}.s3_org.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    created_by = Column(Integer, nullable=False)
    requires_delete_approval = Column(
        Boolean, nullable=False, server_default=text("false"),
        doc="Set when group ever had folder grants; delete requires email approval.",
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    org = relationship("Org", backref="groups", lazy="joined")
    members = relationship("GroupMembership", back_populates="group", cascade="all, delete-orphan")
    grants = relationship("FolderGrant", back_populates="group", cascade="all, delete-orphan")


class GroupMembership(Base):
    """Links users to groups. A user can belong to multiple groups."""
    __tablename__ = "s3_group_membership"
    __table_args__ = (
        UniqueConstraint("group_id", "user_id", name="uq_group_user"),
        {"schema": SCHEMA},
    )

    id = Column(Integer, Identity(start=1), primary_key=True, autoincrement=True)
    group_id = Column(Integer, ForeignKey(f"{SCHEMA}.s3_user_group.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    added_by = Column(Integer, nullable=False)
    added_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    group = relationship("UserGroup", back_populates="members")


class FolderGrant(Base):
    """
    Maps a group to a folder prefix with an access level.
    Grant on 'A/' recursively covers 'A/B/', 'A/B/C/', etc.
    """
    __tablename__ = "s3_folder_grant"
    __table_args__ = (
        UniqueConstraint("group_id", "prefix", name="uq_grant_group_prefix"),
        {"schema": SCHEMA},
    )

    id = Column(Integer, Identity(start=1), primary_key=True, autoincrement=True)
    group_id = Column(Integer, ForeignKey(f"{SCHEMA}.s3_user_group.id", ondelete="CASCADE"), nullable=False, index=True)
    org_id = Column(Integer, ForeignKey(f"{SCHEMA}.s3_org.id"), nullable=False, index=True)
    prefix = Column(String(1024), nullable=False)
    access_level = Column(String(20), nullable=False, server_default=text("'read'"))
    created_by = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    group = relationship("UserGroup", back_populates="grants")
    org = relationship("Org")



class S3UserDeactivation(Base):
    """
    S3 Explorer–scoped deactivation only.
    Does not change UAM user_data.active; UAM deactivation is read from user_data on auth.
    """
    __tablename__ = "s3_user_deactivation"
    __table_args__ = {"schema": SCHEMA}

    user_id = Column(Integer, primary_key=True)
    deactivated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    deactivated_by = Column(Integer, nullable=False)


class AdminOtpChallenge(Base):
    """Hashed OTP for sensitive admin actions (e.g. group delete with active grants)."""
    __tablename__ = "s3_admin_otp"
    __table_args__ = {"schema": SCHEMA}

    id = Column(Integer, Identity(start=1), primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    purpose = Column(String(64), nullable=False, server_default=text("'sensitive_action'"))
    code_hash = Column(String(255), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class UnonboardRequest(Base):
    """4-eyes workflow to remove an onboarded org binding (org row deleted on approve)."""
    __tablename__ = "s3_unonboard_request"
    __table_args__ = {"schema": SCHEMA}

    id = Column(Integer, Identity(start=1), primary_key=True, autoincrement=True)
    org_id = Column(Integer, ForeignKey(f"{SCHEMA}.s3_org.id", ondelete="SET NULL"), nullable=True, index=True)
    org_name = Column(String(255), nullable=True)
    bucket_name = Column(String(255), nullable=True)
    subscription_id = Column(String(255), nullable=True)
    requester_user_id = Column(Integer, nullable=False)
    approver_user_id = Column(Integer, nullable=False)
    status = Column(String(32), nullable=False, server_default=text("'pending_approval'"))
    expires_at = Column(DateTime(timezone=True), nullable=False)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    org = relationship("Org", lazy="joined")


class AdminApprovalRequest(Base):
    """Email approve/reject links for sensitive admin actions."""
    __tablename__ = "s3_admin_approval"
    __table_args__ = {"schema": SCHEMA}

    id = Column(Integer, Identity(start=1), primary_key=True, autoincrement=True)
    purpose = Column(String(64), nullable=False)
    requester_user_id = Column(Integer, nullable=False)
    approver_user_id = Column(Integer, nullable=False)
    approve_token_hash = Column(String(255), nullable=False)
    reject_token_hash = Column(String(255), nullable=False)
    status = Column(String(20), nullable=False, server_default=text("'pending'"))
    expires_at = Column(DateTime(timezone=True), nullable=False)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class UserNotification(Base):
    """In-app notifications for folder access grants and group membership."""
    __tablename__ = "s3_user_notification"
    __table_args__ = {"schema": SCHEMA}

    id = Column(Integer, Identity(start=1), primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    org_id = Column(Integer, ForeignKey(f"{SCHEMA}.s3_org.id"), nullable=False)
    type = Column(String(50), nullable=False)
    title = Column(String(200), nullable=False)
    message = Column(String(500), nullable=False)
    is_read = Column(Boolean, nullable=False, server_default=text("false"))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


# ---------------------------------------------------------------------------
# Legacy tables (kept for backward compatibility during migration)
# ---------------------------------------------------------------------------

class Explorer(Base):
    __tablename__ = "s3_explorer"
    __table_args__ = {"schema": "rhymedatapoem"}

    id = Column(Integer, Identity(start=1), primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False)
    bucket_name = Column(String, nullable=False)
    folder_name = Column(String, nullable=False)
    folder_path = Column(String, nullable=False)
    relative_path = Column(String, nullable=False)
    is_admin = Column(Boolean, nullable=False, default=False)


class ExplorerAction(Base):
    __tablename__ = "s3_explorer_logs"
    __table_args__ = {"schema": "rhymedatapoem"}

    id = Column(Integer, Identity(start=2), primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False)
    action = Column(String, nullable=False)
    path = Column(String, nullable=False)
    filename = Column(String, nullable=False)
    timestamp = Column(TIMESTAMP(timezone=False), server_default=func.now())


class TokenRepository(Base):
    __tablename__ = "s3_access"
    __table_args__ = {"schema": "rhymedatapoem"}

    id = Column(Integer, Identity(start=1), primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False)
    token = Column(String, nullable=False)
    timestamp = Column(TIMESTAMP(timezone=False), server_default=func.now())
    is_expired = Column(Boolean, nullable=False)


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
