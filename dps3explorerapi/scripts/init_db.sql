-- =============================================================================
-- S3 Explorer — greenfield database initialisation
-- Database : s3explorer
-- Schema   : explorer
-- Run once against a fresh database:
--   psql -h localhost -p 5433 -U postgres -d s3explorer -f scripts/init_db.sql
-- =============================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- Schema
-- ---------------------------------------------------------------------------
CREATE SCHEMA IF NOT EXISTS explorer;

-- ---------------------------------------------------------------------------
-- organizations  (owned tenant / bucket binding)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS explorer.organizations (
    id                    BIGSERIAL PRIMARY KEY,
    org_key               VARCHAR(255) NOT NULL UNIQUE,   -- stable external id
    org_name              VARCHAR(255) NOT NULL,
    bucket_name           VARCHAR(255) UNIQUE,
    region                VARCHAR(63)  NOT NULL DEFAULT 'us-east-1',
    max_upload_size_bytes BIGINT       NOT NULL DEFAULT 5368709120,  -- 5 GB
    onboarded_by          BIGINT,                                    -- FK added below after users
    is_active             BOOLEAN      NOT NULL DEFAULT TRUE,
    onboarded_at          TIMESTAMPTZ,
    created_at            TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at            TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_organizations_org_key  ON explorer.organizations (org_key);
CREATE INDEX IF NOT EXISTS ix_organizations_is_active ON explorer.organizations (is_active);

-- ---------------------------------------------------------------------------
-- users  (owned identity, replaces external UAM user_data)
-- role: 1=admin(org-scoped) 2=user 3=master_admin 4=super_admin
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS explorer.users (
    id              BIGSERIAL PRIMARY KEY,
    username        VARCHAR(255) NOT NULL,
    email           VARCHAR(255) NOT NULL UNIQUE,
    role            SMALLINT     NOT NULL DEFAULT 2 CHECK (role IN (1, 2, 3, 4)),
    organization_id BIGINT       REFERENCES explorer.organizations (id) ON DELETE SET NULL,
    active          BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_users_email           ON explorer.users (email);
CREATE INDEX IF NOT EXISTS ix_users_organization_id ON explorer.users (organization_id);
CREATE INDEX IF NOT EXISTS ix_users_role            ON explorer.users (role);

-- back-fill FK now that users exists
ALTER TABLE explorer.organizations
    ADD CONSTRAINT fk_organizations_onboarded_by
    FOREIGN KEY (onboarded_by) REFERENCES explorer.users (id) ON DELETE SET NULL;

-- ---------------------------------------------------------------------------
-- s3_folder_metadata
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS explorer.s3_folder_metadata (
    id              BIGSERIAL PRIMARY KEY,
    org_id          BIGINT       NOT NULL REFERENCES explorer.organizations (id),
    key             VARCHAR(1024) NOT NULL,
    created_by      BIGINT       NOT NULL REFERENCES explorer.users (id),
    created_by_role VARCHAR(20)  NOT NULL,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_s3_folder_metadata_org_id ON explorer.s3_folder_metadata (org_id);

-- ---------------------------------------------------------------------------
-- s3_user_group
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS explorer.s3_user_group (
    id                      BIGSERIAL PRIMARY KEY,
    org_id                  BIGINT       NOT NULL REFERENCES explorer.organizations (id),
    name                    VARCHAR(255) NOT NULL,
    created_by              BIGINT       NOT NULL REFERENCES explorer.users (id),
    requires_delete_approval BOOLEAN     NOT NULL DEFAULT FALSE,
    created_at              TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT uq_group_org_name UNIQUE (org_id, name)
);

CREATE INDEX IF NOT EXISTS ix_s3_user_group_org_id ON explorer.s3_user_group (org_id);

-- ---------------------------------------------------------------------------
-- s3_group_membership
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS explorer.s3_group_membership (
    id       BIGSERIAL PRIMARY KEY,
    group_id BIGINT NOT NULL REFERENCES explorer.s3_user_group (id) ON DELETE CASCADE,
    user_id  BIGINT NOT NULL REFERENCES explorer.users (id),
    added_by BIGINT NOT NULL REFERENCES explorer.users (id),
    added_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_group_user UNIQUE (group_id, user_id)
);

CREATE INDEX IF NOT EXISTS ix_s3_group_membership_group_id ON explorer.s3_group_membership (group_id);
CREATE INDEX IF NOT EXISTS ix_s3_group_membership_user_id  ON explorer.s3_group_membership (user_id);

-- ---------------------------------------------------------------------------
-- s3_folder_grant
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS explorer.s3_folder_grant (
    id           BIGSERIAL PRIMARY KEY,
    group_id     BIGINT        NOT NULL REFERENCES explorer.s3_user_group (id) ON DELETE CASCADE,
    org_id       BIGINT        NOT NULL REFERENCES explorer.organizations (id),
    prefix       VARCHAR(1024) NOT NULL,
    access_level VARCHAR(20)   NOT NULL DEFAULT 'read',
    created_by   BIGINT        NOT NULL REFERENCES explorer.users (id),
    created_at   TIMESTAMPTZ   NOT NULL DEFAULT now(),
    CONSTRAINT uq_grant_group_prefix UNIQUE (group_id, prefix)
);

CREATE INDEX IF NOT EXISTS ix_s3_folder_grant_group_id ON explorer.s3_folder_grant (group_id);
CREATE INDEX IF NOT EXISTS ix_s3_folder_grant_org_id   ON explorer.s3_folder_grant (org_id);

-- ---------------------------------------------------------------------------
-- s3_user_deactivation  (Explorer-access-only deactivation, separate from users.active)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS explorer.s3_user_deactivation (
    user_id        BIGINT      PRIMARY KEY REFERENCES explorer.users (id),
    deactivated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deactivated_by BIGINT      NOT NULL REFERENCES explorer.users (id)
);

CREATE INDEX IF NOT EXISTS ix_s3_user_deactivation_deactivated_at
    ON explorer.s3_user_deactivation (deactivated_at);

-- ---------------------------------------------------------------------------
-- s3_user_notification
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS explorer.s3_user_notification (
    id         BIGSERIAL    PRIMARY KEY,
    user_id    BIGINT       NOT NULL REFERENCES explorer.users (id),
    org_id     BIGINT       NOT NULL REFERENCES explorer.organizations (id),
    type       VARCHAR(50)  NOT NULL,
    title      VARCHAR(200) NOT NULL,
    message    VARCHAR(500) NOT NULL,
    is_read    BOOLEAN      NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_s3_user_notification_user_unread
    ON explorer.s3_user_notification (user_id, is_read, created_at DESC);

-- ---------------------------------------------------------------------------
-- s3_admin_otp
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS explorer.s3_admin_otp (
    id         BIGSERIAL    PRIMARY KEY,
    user_id    BIGINT       NOT NULL REFERENCES explorer.users (id),
    purpose    VARCHAR(64)  NOT NULL DEFAULT 'sensitive_action',
    code_hash  VARCHAR(255) NOT NULL,
    expires_at TIMESTAMPTZ  NOT NULL,
    used_at    TIMESTAMPTZ,
    created_at TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_s3_admin_otp_user_purpose ON explorer.s3_admin_otp (user_id, purpose);
CREATE INDEX IF NOT EXISTS ix_s3_admin_otp_expires_at   ON explorer.s3_admin_otp (expires_at);

-- ---------------------------------------------------------------------------
-- s3_admin_approval
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS explorer.s3_admin_approval (
    id                  BIGSERIAL    PRIMARY KEY,
    purpose             VARCHAR(64)  NOT NULL,
    requester_user_id   BIGINT       NOT NULL REFERENCES explorer.users (id),
    approver_user_id    BIGINT       NOT NULL REFERENCES explorer.users (id),
    approve_token_hash  VARCHAR(255) NOT NULL,
    reject_token_hash   VARCHAR(255) NOT NULL,
    status              VARCHAR(20)  NOT NULL DEFAULT 'pending',
    expires_at          TIMESTAMPTZ  NOT NULL,
    resolved_at         TIMESTAMPTZ,
    created_at          TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_s3_admin_approval_purpose_status
    ON explorer.s3_admin_approval (purpose, status);
CREATE INDEX IF NOT EXISTS ix_s3_admin_approval_expires_at
    ON explorer.s3_admin_approval (expires_at);

-- ---------------------------------------------------------------------------
-- s3_unonboard_request
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS explorer.s3_unonboard_request (
    id                BIGSERIAL    PRIMARY KEY,
    org_id            BIGINT       REFERENCES explorer.organizations (id) ON DELETE SET NULL,
    -- point-in-time snapshots kept as plain strings (not FKs)
    org_name          VARCHAR(255),
    bucket_name       VARCHAR(255),
    org_key           VARCHAR(255),
    requester_user_id BIGINT       NOT NULL REFERENCES explorer.users (id),
    approver_user_id  BIGINT       NOT NULL REFERENCES explorer.users (id),
    status            VARCHAR(32)  NOT NULL DEFAULT 'pending_approval',
    expires_at        TIMESTAMPTZ  NOT NULL,
    resolved_at       TIMESTAMPTZ,
    created_at        TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_s3_unonboard_request_org_status
    ON explorer.s3_unonboard_request (org_id, status);

-- ---------------------------------------------------------------------------
-- s3_platform_settings  (singleton, id always = 1)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS explorer.s3_platform_settings (
    id                 INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    allowed_extensions JSONB   NOT NULL DEFAULT '[
        {"ext":".parquet","color":"#10b981"},
        {"ext":".orc",    "color":"#10b981"},
        {"ext":".csv",    "color":"#10b981"},
        {"ext":".json",   "color":"#f59e0b"},
        {"ext":".zip",    "color":"#8b5cf6"},
        {"ext":".gz",     "color":"#8b5cf6"},
        {"ext":".xlsx",   "color":"#10b981"},
        {"ext":".txt",    "color":"#3b82f6"},
        {"ext":".pdf",    "color":"#3b82f6"},
        {"ext":".docx",   "color":"#3b82f6"},
        {"ext":".png",    "color":"#ec4899"}
    ]'::jsonb,
    max_upload_bytes   BIGINT  NOT NULL DEFAULT 5368709120,  -- 5 GB
    updated_by         BIGINT  REFERENCES explorer.users (id),
    updated_at         TIMESTAMPTZ DEFAULT now()
);

-- seed singleton row
INSERT INTO explorer.s3_platform_settings (id)
VALUES (1)
ON CONFLICT (id) DO NOTHING;

COMMIT;
