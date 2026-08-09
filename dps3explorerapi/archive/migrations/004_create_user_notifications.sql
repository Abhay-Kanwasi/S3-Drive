-- Phase 3.6: In-app notifications for folder access grants
-- Run against the shared rhymedatapoem schema

BEGIN;

CREATE TABLE IF NOT EXISTS rhymedatapoem.s3_user_notification (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    org_id INTEGER NOT NULL REFERENCES rhymedatapoem.s3_org(id),
    type VARCHAR(50) NOT NULL,
    title VARCHAR(200) NOT NULL,
    message VARCHAR(500) NOT NULL,
    is_read BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_notif_user_unread
    ON rhymedatapoem.s3_user_notification(user_id, is_read, created_at DESC);

COMMIT;
