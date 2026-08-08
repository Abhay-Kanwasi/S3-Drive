unonboard_approval_email_body = """
<!DOCTYPE html>
<html>
<body style="font-family: Arial, sans-serif; color: #1a1a1a; line-height: 1.5; max-width: 560px;">
  <p>Hello{greeting},</p>
  <p><strong>{requester_name}</strong> is requesting your approval to <strong>un-onboard</strong> an organization in <strong>S3 Explorer</strong>:</p>
  <table style="width:100%; border-collapse: collapse; margin: 16px 0; font-size: 14px;">
    <tr><td style="padding: 6px 0; color: #666;">Organization</td><td style="padding: 6px 0;"><strong>{org_name}</strong></td></tr>
    <tr><td style="padding: 6px 0; color: #666;">S3 bucket</td><td style="padding: 6px 0; font-family: monospace;">{bucket_name}</td></tr>
    <tr><td style="padding: 6px 0; color: #666;">Folder grants</td><td style="padding: 6px 0;">{grant_count} (will be revoked)</td></tr>
    <tr><td style="padding: 6px 0; color: #666;">Groups</td><td style="padding: 6px 0;">{group_count} (will be removed)</td></tr>
  </table>
  <p style="color: #b45309; font-size: 13px;">The S3 bucket and objects in AWS are <strong>not</strong> deleted. The org–bucket binding and all Explorer groups, grants, and folder mappings will be removed so this subscriber and bucket can be onboarded again.</p>
  <p style="margin: 24px 0;">
    <a href="{approve_url}" style="display:inline-block; background:#16a34a; color:#fff; text-decoration:none; padding:12px 24px; border-radius:8px; font-weight:bold; margin-right:12px;">Review and approve</a>
    <a href="{reject_url}" style="display:inline-block; background:#dc2626; color:#fff; text-decoration:none; padding:12px 24px; border-radius:8px; font-weight:bold;">Review and reject</a>
  </p>
  <p style="color: #666; font-size: 12px;">These links expire in <strong>{valid_hours}</strong>. You will see a confirmation page before anything is changed.</p>
</body>
</html>
"""
