-- One-time: remove legacy soft-un-onboard rows (is_active = false) that block re-onboard
-- due to UNIQUE on subscription_id / bucket_name. New un-onboard deletes s3_org instead.
-- Safe to re-run (no-op when no inactive orgs remain).

BEGIN;

DELETE FROM rhymedatapoem.s3_folder_grant
WHERE group_id IN (
    SELECT id FROM rhymedatapoem.s3_user_group
    WHERE org_id IN (SELECT id FROM rhymedatapoem.s3_org WHERE is_active = false)
);

DELETE FROM rhymedatapoem.s3_group_membership
WHERE group_id IN (
    SELECT id FROM rhymedatapoem.s3_user_group
    WHERE org_id IN (SELECT id FROM rhymedatapoem.s3_org WHERE is_active = false)
);

DELETE FROM rhymedatapoem.s3_folder_grant
WHERE org_id IN (SELECT id FROM rhymedatapoem.s3_org WHERE is_active = false);

DELETE FROM rhymedatapoem.s3_user_group
WHERE org_id IN (SELECT id FROM rhymedatapoem.s3_org WHERE is_active = false);

DELETE FROM rhymedatapoem.s3_folder_metadata
WHERE org_id IN (SELECT id FROM rhymedatapoem.s3_org WHERE is_active = false);

DELETE FROM rhymedatapoem.s3_user_notification
WHERE org_id IN (SELECT id FROM rhymedatapoem.s3_org WHERE is_active = false);

DELETE FROM rhymedatapoem.s3_org
WHERE is_active = false;

COMMIT;
