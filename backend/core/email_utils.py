"""Email sending utilities using user-configured Gmail SMTP."""

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from django.utils import timezone

from .encryption import decrypt_value

logger = logging.getLogger(__name__)


def test_smtp_connection(sender_email: str, app_password: str) -> tuple[bool, str]:
    """Test SMTP connection with provided credentials. Returns (success, message)."""
    try:
        server = smtplib.SMTP("smtp.gmail.com", 587, timeout=10)
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(sender_email, app_password)
        server.quit()
        return True, "SMTP connection successful."
    except smtplib.SMTPAuthenticationError:
        return False, "Authentication failed. Check your email and app password."
    except smtplib.SMTPException as e:
        return False, f"SMTP error: {e}"
    except Exception as e:
        return False, f"Connection error: {e}"


def render_template(template_str: str, context: dict) -> str:
    """Replace {{placeholder}} tokens in a template string with context values."""
    result = template_str
    for key, value in context.items():
        result = result.replace("{{" + key + "}}", str(value))
    return result


def build_fields_html(payload: dict) -> str:
    """Build an HTML representation of form submission fields."""
    lines = []
    for key, value in payload.items():
        if key in ("access_key", "_honeypot"):
            continue
        lines.append(f"<p><strong>{key}:</strong> {value}</p>")
    return "\n".join(lines)


def build_fields_text(payload: dict) -> str:
    """Build a plain-text representation of form submission fields."""
    lines = []
    for key, value in payload.items():
        if key in ("access_key", "_honeypot"):
            continue
        lines.append(f"{key}: {value}")
    return "\n".join(lines)


def send_submission_email(submission, gmail_config, email_template=None):
    """
    Send an email notification for a form submission.

    Args:
        submission: Submission model instance
        gmail_config: GmailConfig model instance
        email_template: EmailTemplate model instance (optional, uses default if None)

    Returns:
        tuple: (success: bool, error_message: str)
    """
    try:
        # Decrypt the app password
        app_password = decrypt_value(gmail_config.encrypted_password)

        # Build template context
        payload = submission.payload_json or {}
        context = {
            "form_name": submission.form.name,
            "submission_time": submission.created_at.strftime("%Y-%m-%d %H:%M:%S UTC"),
            "ip_address": submission.ip_address or "Unknown",
            "fields_html": build_fields_html(payload),
            "fields_text": build_fields_text(payload),
        }

        # Add all payload fields to context
        for key, value in payload.items():
            if key not in ("access_key", "_honeypot"):
                context[key] = str(value)

        # Use template or defaults
        if email_template:
            subject = render_template(email_template.subject, context)
            body_html = render_template(email_template.body_html, context)
            body_text = render_template(email_template.body_text, context) if email_template.body_text else ""
        else:
            subject = f"New Form Submission - {submission.form.name}"
            body_html = (
                f"<h2>New Form Submission</h2>"
                f"<p><strong>Form:</strong> {submission.form.name}</p>"
                f"<p><strong>Time:</strong> {context['submission_time']}</p>"
                f"<p><strong>IP:</strong> {context['ip_address']}</p>"
                f"<hr>{context['fields_html']}"
            )
            body_text = (
                f"New Form Submission\n\n"
                f"Form: {submission.form.name}\n"
                f"Time: {context['submission_time']}\n"
                f"IP: {context['ip_address']}\n\n"
                f"{context['fields_text']}"
            )

        # Build the email
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = gmail_config.sender_email
        msg["To"] = submission.form.email_to

        if body_text:
            msg.attach(MIMEText(body_text, "plain"))
        msg.attach(MIMEText(body_html, "html"))

        # Send via SMTP
        server = smtplib.SMTP("smtp.gmail.com", 587, timeout=15)
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(gmail_config.sender_email, app_password)
        server.sendmail(gmail_config.sender_email, [submission.form.email_to], msg.as_string())
        server.quit()

        return True, ""

    except Exception as e:
        logger.exception("Failed to send submission email for submission #%s", submission.pk)
        return False, str(e)

def render_preview(email_template, sample_payload: dict | None = None, *, form_name: str = "Sample Form") -> dict:
    """Render an EmailTemplate with sample data WITHOUT sending. Returns a dict with subject/html/text."""
    sample_payload = sample_payload or {
        "name": "Ada Lovelace",
        "email": "ada@example.com",
        "message": "Hello! This is a preview of your form notification.",
    }
    context = {
        "form_name": form_name,
        "submission_time": "2025-01-01 12:00:00 UTC",
        "ip_address": "203.0.113.7",
        "fields_html": build_fields_html(sample_payload),
        "fields_text": build_fields_text(sample_payload),
    }
    for k, v in sample_payload.items():
        context[k] = str(v)

    if email_template is None:
        # Match the defaults used by send_submission_email when no template.
        subject = f"New Form Submission - {form_name}"
        body_html = (
            f"<h2>New Form Submission</h2>"
            f"<p><strong>Form:</strong> {form_name}</p>"
            f"<p><strong>Time:</strong> {context['submission_time']}</p>"
            f"<p><strong>IP:</strong> {context['ip_address']}</p>"
            f"<hr>{context['fields_html']}"
        )
        body_text = (
            f"New Form Submission\n\nForm: {form_name}\nTime: {context['submission_time']}\n"
            f"IP: {context['ip_address']}\n\n{context['fields_text']}"
        )
    else:
        subject = render_template(email_template.subject, context)
        body_html = render_template(email_template.body_html, context)
        body_text = render_template(email_template.body_text or "", context)

    return {"subject": subject, "html": body_html, "text": body_text}
