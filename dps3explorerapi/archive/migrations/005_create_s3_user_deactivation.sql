-- S3 Explorer–only deactivation (does not modify UAM user_data.active).
-- UAM deactivation is detected via shared user_data.active on each auth request.

CREATE TABLE IF NOT EXISTS rhymedatapoem.s3_user_deactivation (
    user_id INTEGER PRIMARY KEY,
    deactivated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deactivated_by INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_s3_user_deactivation_deactivated_at
    ON rhymedatapoem.s3_user_deactivation (deactivated_at);
