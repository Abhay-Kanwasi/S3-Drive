-- Groups that ever had folder grants must use email approval to delete (prevents grant-stripping bypass).

ALTER TABLE rhymedatapoem.s3_user_group
    ADD COLUMN IF NOT EXISTS requires_delete_approval BOOLEAN NOT NULL DEFAULT false;

UPDATE rhymedatapoem.s3_user_group g
SET requires_delete_approval = true
WHERE EXISTS (
    SELECT 1 FROM rhymedatapoem.s3_folder_grant fg WHERE fg.group_id = g.id
);
