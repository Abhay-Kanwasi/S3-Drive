approval_email_body = """
<!DOCTYPE html>
<html>
<body style="font-family: Arial, sans-serif; color: #1a1a1a; line-height: 1.5; max-width: 560px;">
  <p>Hello{greeting},</p>
  {requested_line}
  <p><strong>{requester_name}</strong> is requesting your approval to delete the following group in <strong>S3 Explorer</strong>:</p>
  <table style="width:100%; border-collapse: collapse; margin: 16px 0; font-size: 14px;">
    <tr><td style="padding: 6px 0; color: #666;">Group</td><td style="padding: 6px 0;"><strong>{group_name}</strong></td></tr>
    <tr><td style="padding: 6px 0; color: #666;">Organization</td><td style="padding: 6px 0;">{org_name}</td></tr>
    <tr><td style="padding: 6px 0; color: #666;">Members</td><td style="padding: 6px 0;">{member_count}</td></tr>
    <tr><td style="padding: 6px 0; color: #666;">Folder access</td><td style="padding: 6px 0;">{grant_count} grant(s)</td></tr>
  </table>
  <p style="color: #b45309; font-size: 13px;">Deleting this group removes all members and revokes folder access. This cannot be undone.</p>
  <p style="margin: 24px 0;">
    <a href="{approve_url}" style="display:inline-block; background:#16a34a; color:#fff; text-decoration:none; padding:12px 24px; border-radius:8px; font-weight:bold; margin-right:12px;">Review and approve</a>
    <a href="{reject_url}" style="display:inline-block; background:#dc2626; color:#fff; text-decoration:none; padding:12px 24px; border-radius:8px; font-weight:bold;">Review and reject</a>
  </p>
  <p style="color: #666; font-size: 12px;">These links expire in <strong>{valid_hours}</strong>. You will see a confirmation page before anything is changed. If you did not expect this request, ignore this email.</p>
</body>
</html>
"""
