"""Send transactional email via SMTP (used for OTP)."""

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from core.config import settings

logger = logging.getLogger(__name__)


def smtp_configured() -> bool:
    return bool(
        settings.SMTP_HOST
        and settings.SMTP_USERNAME
        and settings.SMTP_PASSWORD
    )


def send_smtp_html(*, to_email: str, subject: str, html_body: str) -> None:
    """Send HTML email. Raises RuntimeError if SMTP is not configured or send fails."""
    if not to_email:
        raise RuntimeError("Recipient email is missing")
    if not smtp_configured():
        raise RuntimeError(
            "SMTP is not configured. Set SMTP_HOST, SMTP_USERNAME, SMTP_PASSWORD, and PORT in .env"
        )

    from_addr = settings.SMTP_FROM or settings.SMTP_USERNAME
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_email
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=30) as server:
            server.starttls()
            server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
            server.sendmail(from_addr, [to_email], msg.as_string())
    except Exception as e:
        logger.exception("SMTP send failed for %s", to_email)
        raise RuntimeError(f"Failed to send email: {e}") from e
