-- Phase 3: Group management tables
-- Run against the shared rhymedatapoem schema

BEGIN;

CREATE TABLE IF NOT EXISTS rhymedatapoem.s3_user_group (
    id          SERIAL PRIMARY KEY,
    org_id      INTEGER NOT NULL REFERENCES rhymedatapoem.s3_org(id),
    name        VARCHAR(255) NOT NULL,
    created_by  INTEGER NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_group_org_name UNIQUE (org_id, name)
);
CREATE INDEX IF NOT EXISTS ix_s3_user_group_org_id ON rhymedatapoem.s3_user_group(org_id);

CREATE TABLE IF NOT EXISTS rhymedatapoem.s3_group_membership (
    id          SERIAL PRIMARY KEY,
    group_id    INTEGER NOT NULL REFERENCES rhymedatapoem.s3_user_group(id) ON DELETE CASCADE,
    user_id     INTEGER NOT NULL,
    added_by    INTEGER NOT NULL,
    added_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_group_user UNIQUE (group_id, user_id)
);
CREATE INDEX IF NOT EXISTS ix_s3_group_membership_group_id ON rhymedatapoem.s3_group_membership(group_id);
CREATE INDEX IF NOT EXISTS ix_s3_group_membership_user_id ON rhymedatapoem.s3_group_membership(user_id);

CREATE TABLE IF NOT EXISTS rhymedatapoem.s3_folder_grant (
    id              SERIAL PRIMARY KEY,
    group_id        INTEGER NOT NULL REFERENCES rhymedatapoem.s3_user_group(id) ON DELETE CASCADE,
    org_id          INTEGER NOT NULL REFERENCES rhymedatapoem.s3_org(id),
    prefix          VARCHAR(1024) NOT NULL,
    access_level    VARCHAR(20) NOT NULL DEFAULT 'read',
    created_by      INTEGER NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_grant_group_prefix UNIQUE (group_id, prefix)
);
CREATE INDEX IF NOT EXISTS ix_s3_folder_grant_group_id ON rhymedatapoem.s3_folder_grant(group_id);
CREATE INDEX IF NOT EXISTS ix_s3_folder_grant_org_id ON rhymedatapoem.s3_folder_grant(org_id);

COMMIT;
