-- Migration 001: Create S3 Explorer org management tables
-- Run this against the shared database (mydatabase on 172.16.3.106:5432)
-- Schema: rhymedatapoem (same schema as UAM's user_data/subscriber tables)
-- These are NEW tables, no existing tables are modified.

-- 1. Organization onboarding table
CREATE TABLE IF NOT EXISTS rhymedatapoem.s3_org (
    id              SERIAL PRIMARY KEY,
    subscription_id VARCHAR(255) NOT NULL UNIQUE,
    org_name        VARCHAR(255) NOT NULL,
    bucket_name     VARCHAR(255) NOT NULL,
    region          VARCHAR(63)  NOT NULL DEFAULT 'us-east-1',
    max_upload_size_bytes BIGINT NOT NULL DEFAULT 5368709120,  -- 5 GB
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    onboarded_by    INTEGER NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_s3_org_subscription_id ON rhymedatapoem.s3_org(subscription_id);

-- 2. Folder ownership tracking table
CREATE TABLE IF NOT EXISTS rhymedatapoem.s3_folder_metadata (
    id              SERIAL PRIMARY KEY,
    org_id          INTEGER NOT NULL REFERENCES rhymedatapoem.s3_org(id),
    key             VARCHAR(1024) NOT NULL,
    created_by      INTEGER NOT NULL,
    created_by_role VARCHAR(20) NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_s3_folder_metadata_org_id ON rhymedatapoem.s3_folder_metadata(org_id);
