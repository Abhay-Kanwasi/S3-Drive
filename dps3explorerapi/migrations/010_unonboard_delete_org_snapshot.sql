-- Un-onboard deletes s3_org row; keep request history via snapshots + nullable org_id.

ALTER TABLE rhymedatapoem.s3_unonboard_request
    ADD COLUMN IF NOT EXISTS org_name VARCHAR(255),
    ADD COLUMN IF NOT EXISTS bucket_name VARCHAR(255),
    ADD COLUMN IF NOT EXISTS subscription_id VARCHAR(255);

UPDATE rhymedatapoem.s3_unonboard_request u
SET
    org_name = o.org_name,
    bucket_name = o.bucket_name,
    subscription_id = o.subscription_id
FROM rhymedatapoem.s3_org o
WHERE u.org_id = o.id
  AND u.org_name IS NULL;

ALTER TABLE rhymedatapoem.s3_unonboard_request
    ALTER COLUMN org_id DROP NOT NULL;

ALTER TABLE rhymedatapoem.s3_unonboard_request
    DROP CONSTRAINT IF EXISTS s3_unonboard_request_org_id_fkey;

ALTER TABLE rhymedatapoem.s3_unonboard_request
    ADD CONSTRAINT s3_unonboard_request_org_id_fkey
        FOREIGN KEY (org_id) REFERENCES rhymedatapoem.s3_org(id) ON DELETE SET NULL;
