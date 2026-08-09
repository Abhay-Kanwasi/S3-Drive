"""Baseline schema for owned explorer database.

Revision ID: 0001_initial
Revises:
Create Date: 2026-08-09
"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

from core.config import settings

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = settings.DB_SCHEMA


def upgrade() -> None:
    # Schema created here and also in alembic/env.py for online runs.
    op.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{SCHEMA}"'))

    op.execute(text(f"""
CREATE TABLE IF NOT EXISTS "{SCHEMA}".organizations (
    id                    BIGSERIAL PRIMARY KEY,
    org_key               VARCHAR(255) NOT NULL UNIQUE,
    org_name              VARCHAR(255) NOT NULL,
    bucket_name           VARCHAR(255) UNIQUE,
    region                VARCHAR(63)  NOT NULL DEFAULT 'us-east-1',
    max_upload_size_bytes BIGINT       NOT NULL DEFAULT 5368709120,
    onboarded_by          BIGINT,
    is_active             BOOLEAN      NOT NULL DEFAULT TRUE,
    onboarded_at          TIMESTAMPTZ,
    created_at            TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at            TIMESTAMPTZ  NOT NULL DEFAULT now()
)
"""))

    op.execute(text(f"""
CREATE INDEX IF NOT EXISTS ix_organizations_org_key
    ON "{SCHEMA}".organizations (org_key)
"""))
    op.execute(text(f"""
CREATE INDEX IF NOT EXISTS ix_organizations_is_active
    ON "{SCHEMA}".organizations (is_active)
"""))

    op.execute(text(f"""
CREATE TABLE IF NOT EXISTS "{SCHEMA}".users (
    id              BIGSERIAL PRIMARY KEY,
    username        VARCHAR(255) NOT NULL,
    email           VARCHAR(255) NOT NULL UNIQUE,
    role            SMALLINT     NOT NULL DEFAULT 2 CHECK (role IN (1, 2, 3, 4)),
    organization_id BIGINT       REFERENCES "{SCHEMA}".organizations (id) ON DELETE SET NULL,
    active          BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT now()
)
"""))

    op.execute(text(f"""
CREATE INDEX IF NOT EXISTS ix_users_email
    ON "{SCHEMA}".users (email)
"""))
    op.execute(text(f"""
CREATE INDEX IF NOT EXISTS ix_users_organization_id
    ON "{SCHEMA}".users (organization_id)
"""))
    op.execute(text(f"""
CREATE INDEX IF NOT EXISTS ix_users_role
    ON "{SCHEMA}".users (role)
"""))

    # onboarded_by FK after users exists
    op.execute(text(f"""
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_organizations_onboarded_by'
    ) THEN
        ALTER TABLE "{SCHEMA}".organizations
            ADD CONSTRAINT fk_organizations_onboarded_by
            FOREIGN KEY (onboarded_by) REFERENCES "{SCHEMA}".users (id) ON DELETE SET NULL;
    END IF;
END $$
"""))

    op.execute(text(f"""
CREATE TABLE IF NOT EXISTS "{SCHEMA}".s3_folder_metadata (
    id              BIGSERIAL PRIMARY KEY,
    org_id          BIGINT       NOT NULL REFERENCES "{SCHEMA}".organizations (id),
    key             VARCHAR(1024) NOT NULL,
    created_by      BIGINT       NOT NULL REFERENCES "{SCHEMA}".users (id),
    created_by_role VARCHAR(20)  NOT NULL,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now()
)
"""))
    op.execute(text(f"""
CREATE INDEX IF NOT EXISTS ix_s3_folder_metadata_org_id
    ON "{SCHEMA}".s3_folder_metadata (org_id)
"""))

    op.execute(text(f"""
CREATE TABLE IF NOT EXISTS "{SCHEMA}".s3_user_group (
    id                       BIGSERIAL PRIMARY KEY,
    org_id                   BIGINT       NOT NULL REFERENCES "{SCHEMA}".organizations (id),
    name                     VARCHAR(255) NOT NULL,
    created_by               BIGINT       NOT NULL REFERENCES "{SCHEMA}".users (id),
    requires_delete_approval BOOLEAN      NOT NULL DEFAULT FALSE,
    created_at               TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at               TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT uq_group_org_name UNIQUE (org_id, name)
)
"""))
    op.execute(text(f"""
CREATE INDEX IF NOT EXISTS ix_s3_user_group_org_id
    ON "{SCHEMA}".s3_user_group (org_id)
"""))

    op.execute(text(f"""
CREATE TABLE IF NOT EXISTS "{SCHEMA}".s3_group_membership (
    id       BIGSERIAL PRIMARY KEY,
    group_id BIGINT NOT NULL REFERENCES "{SCHEMA}".s3_user_group (id) ON DELETE CASCADE,
    user_id  BIGINT NOT NULL REFERENCES "{SCHEMA}".users (id),
    added_by BIGINT NOT NULL REFERENCES "{SCHEMA}".users (id),
    added_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_group_user UNIQUE (group_id, user_id)
)
"""))
    op.execute(text(f"""
CREATE INDEX IF NOT EXISTS ix_s3_group_membership_group_id
    ON "{SCHEMA}".s3_group_membership (group_id)
"""))
    op.execute(text(f"""
CREATE INDEX IF NOT EXISTS ix_s3_group_membership_user_id
    ON "{SCHEMA}".s3_group_membership (user_id)
"""))

    op.execute(text(f"""
CREATE TABLE IF NOT EXISTS "{SCHEMA}".s3_folder_grant (
    id           BIGSERIAL PRIMARY KEY,
    group_id     BIGINT        NOT NULL REFERENCES "{SCHEMA}".s3_user_group (id) ON DELETE CASCADE,
    org_id       BIGINT        NOT NULL REFERENCES "{SCHEMA}".organizations (id),
    prefix       VARCHAR(1024) NOT NULL,
    access_level VARCHAR(20)   NOT NULL DEFAULT 'read',
    created_by   BIGINT        NOT NULL REFERENCES "{SCHEMA}".users (id),
    created_at   TIMESTAMPTZ   NOT NULL DEFAULT now(),
    CONSTRAINT uq_grant_group_prefix UNIQUE (group_id, prefix)
)
"""))
    op.execute(text(f"""
CREATE INDEX IF NOT EXISTS ix_s3_folder_grant_group_id
    ON "{SCHEMA}".s3_folder_grant (group_id)
"""))
    op.execute(text(f"""
CREATE INDEX IF NOT EXISTS ix_s3_folder_grant_org_id
    ON "{SCHEMA}".s3_folder_grant (org_id)
"""))

    op.execute(text(f"""
CREATE TABLE IF NOT EXISTS "{SCHEMA}".s3_user_deactivation (
    user_id        BIGINT      PRIMARY KEY REFERENCES "{SCHEMA}".users (id),
    deactivated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deactivated_by BIGINT      NOT NULL REFERENCES "{SCHEMA}".users (id)
)
"""))
    op.execute(text(f"""
CREATE INDEX IF NOT EXISTS ix_s3_user_deactivation_deactivated_at
    ON "{SCHEMA}".s3_user_deactivation (deactivated_at)
"""))

    op.execute(text(f"""
CREATE TABLE IF NOT EXISTS "{SCHEMA}".s3_user_notification (
    id         BIGSERIAL    PRIMARY KEY,
    user_id    BIGINT       NOT NULL REFERENCES "{SCHEMA}".users (id),
    org_id     BIGINT       NOT NULL REFERENCES "{SCHEMA}".organizations (id),
    type       VARCHAR(50)  NOT NULL,
    title      VARCHAR(200) NOT NULL,
    message    VARCHAR(500) NOT NULL,
    is_read    BOOLEAN      NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ  NOT NULL DEFAULT now()
)
"""))
    op.execute(text(f"""
CREATE INDEX IF NOT EXISTS ix_s3_user_notification_user_unread
    ON "{SCHEMA}".s3_user_notification (user_id, is_read, created_at DESC)
"""))

    op.execute(text(f"""
CREATE TABLE IF NOT EXISTS "{SCHEMA}".s3_admin_otp (
    id         BIGSERIAL    PRIMARY KEY,
    user_id    BIGINT       NOT NULL REFERENCES "{SCHEMA}".users (id),
    purpose    VARCHAR(64)  NOT NULL DEFAULT 'sensitive_action',
    code_hash  VARCHAR(255) NOT NULL,
    expires_at TIMESTAMPTZ  NOT NULL,
    used_at    TIMESTAMPTZ,
    created_at TIMESTAMPTZ  NOT NULL DEFAULT now()
)
"""))
    op.execute(text(f"""
CREATE INDEX IF NOT EXISTS ix_s3_admin_otp_user_purpose
    ON "{SCHEMA}".s3_admin_otp (user_id, purpose)
"""))
    op.execute(text(f"""
CREATE INDEX IF NOT EXISTS ix_s3_admin_otp_expires_at
    ON "{SCHEMA}".s3_admin_otp (expires_at)
"""))

    op.execute(text(f"""
CREATE TABLE IF NOT EXISTS "{SCHEMA}".s3_admin_approval (
    id                  BIGSERIAL    PRIMARY KEY,
    purpose             VARCHAR(64)  NOT NULL,
    requester_user_id   BIGINT       NOT NULL REFERENCES "{SCHEMA}".users (id),
    approver_user_id    BIGINT       NOT NULL REFERENCES "{SCHEMA}".users (id),
    approve_token_hash  VARCHAR(255) NOT NULL,
    reject_token_hash   VARCHAR(255) NOT NULL,
    status              VARCHAR(20)  NOT NULL DEFAULT 'pending',
    expires_at          TIMESTAMPTZ  NOT NULL,
    resolved_at         TIMESTAMPTZ,
    created_at          TIMESTAMPTZ  NOT NULL DEFAULT now()
)
"""))
    op.execute(text(f"""
CREATE INDEX IF NOT EXISTS ix_s3_admin_approval_purpose_status
    ON "{SCHEMA}".s3_admin_approval (purpose, status)
"""))
    op.execute(text(f"""
CREATE INDEX IF NOT EXISTS ix_s3_admin_approval_expires_at
    ON "{SCHEMA}".s3_admin_approval (expires_at)
"""))

    op.execute(text(f"""
CREATE TABLE IF NOT EXISTS "{SCHEMA}".s3_unonboard_request (
    id                BIGSERIAL    PRIMARY KEY,
    org_id            BIGINT       REFERENCES "{SCHEMA}".organizations (id) ON DELETE SET NULL,
    org_name          VARCHAR(255),
    bucket_name       VARCHAR(255),
    org_key           VARCHAR(255),
    requester_user_id BIGINT       NOT NULL REFERENCES "{SCHEMA}".users (id),
    approver_user_id  BIGINT       NOT NULL REFERENCES "{SCHEMA}".users (id),
    status            VARCHAR(32)  NOT NULL DEFAULT 'pending_approval',
    expires_at        TIMESTAMPTZ  NOT NULL,
    resolved_at       TIMESTAMPTZ,
    created_at        TIMESTAMPTZ  NOT NULL DEFAULT now()
)
"""))
    op.execute(text(f"""
CREATE INDEX IF NOT EXISTS ix_s3_unonboard_request_org_status
    ON "{SCHEMA}".s3_unonboard_request (org_id, status)
"""))

    op.execute(text(f"""
CREATE TABLE IF NOT EXISTS "{SCHEMA}".s3_platform_settings (
    id                 INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    allowed_extensions JSONB   NOT NULL DEFAULT '[
        {{"ext":".parquet","color":"#10b981"}},
        {{"ext":".orc","color":"#10b981"}},
        {{"ext":".csv","color":"#10b981"}},
        {{"ext":".json","color":"#f59e0b"}},
        {{"ext":".zip","color":"#8b5cf6"}},
        {{"ext":".gz","color":"#8b5cf6"}},
        {{"ext":".xlsx","color":"#10b981"}},
        {{"ext":".txt","color":"#3b82f6"}},
        {{"ext":".pdf","color":"#3b82f6"}},
        {{"ext":".docx","color":"#3b82f6"}},
        {{"ext":".png","color":"#ec4899"}}
    ]'::jsonb,
    max_upload_bytes   BIGINT  NOT NULL DEFAULT 5368709120,
    updated_by         BIGINT  REFERENCES "{SCHEMA}".users (id),
    updated_at         TIMESTAMPTZ DEFAULT now()
)
"""))

    op.execute(text(f"""
INSERT INTO "{SCHEMA}".s3_platform_settings (id)
VALUES (1)
ON CONFLICT (id) DO NOTHING
"""))


def downgrade() -> None:
    for table in (
        "s3_platform_settings",
        "s3_unonboard_request",
        "s3_admin_approval",
        "s3_admin_otp",
        "s3_user_notification",
        "s3_user_deactivation",
        "s3_folder_grant",
        "s3_group_membership",
        "s3_user_group",
        "s3_folder_metadata",
        "users",
        "organizations",
    ):
        op.execute(text(f'DROP TABLE IF EXISTS "{SCHEMA}".{table} CASCADE'))
    op.execute(text(f'DROP SCHEMA IF EXISTS "{SCHEMA}" CASCADE'))
