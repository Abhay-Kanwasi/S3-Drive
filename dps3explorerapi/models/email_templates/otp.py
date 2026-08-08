otp_email_body = """
<!DOCTYPE html>
<html>
<body style="font-family: Arial, sans-serif; color: #1a1a1a; line-height: 1.5;">
  <p>Hello{greeting},</p>
  {requested_line}
  <p>Your verification code for <strong>S3 Explorer</strong>{action_label} is:</p>
  <p style="font-size: 28px; font-weight: bold; letter-spacing: 4px; margin: 24px 0;">{code}</p>
  <p>This code expires in <strong>{valid_minutes} minutes</strong>. Do not share it with anyone.</p>
  <p style="color: #666; font-size: 12px;">If you did not request this code, you can ignore this email.</p>
</body>
</html>
"""
