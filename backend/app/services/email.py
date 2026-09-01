import logging
import smtplib
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.settings.models import EmailTemplate

log = logging.getLogger("weta.email")


def send_email(
    to: str | list[str],
    subject: str,
    body_html: str,
    attachments: list[tuple[str, bytes, str]] | None = None,  # (filename, data, mime)
) -> bool:
    recipients = [to] if isinstance(to, str) else list(to)

    if not settings.smtp_host:
        log.info("[email fallback] To: %s | Subject: %s\n%s", recipients, subject, body_html)
        return False

    msg = MIMEMultipart()
    msg["From"] = settings.smtp_from
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = subject
    msg.attach(MIMEText(body_html, "html"))
    for filename, data, mime in attachments or []:
        part = MIMEApplication(data, _subtype=mime.split("/")[-1])
        part.add_header("Content-Disposition", "attachment", filename=filename)
        msg.attach(part)

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as server:
            server.starttls()
            if settings.smtp_user:
                server.login(settings.smtp_user, settings.smtp_password)
            server.sendmail(settings.smtp_from, recipients, msg.as_string())
        return True
    except Exception:
        log.exception("Failed to send email to %s", recipients)
        return False


class _SafeDict(dict):
    def __missing__(self, key):  # leave unknown placeholders intact instead of raising
        return "{" + key + "}"


def render_template(db: Session, name: str, context: dict) -> tuple[str, str]:
    """Return (subject, body_html) for a stored template, with {placeholders} filled."""
    tpl = db.scalar(select(EmailTemplate).where(EmailTemplate.name == name))
    if not tpl:
        return name, ""
    ctx = _SafeDict(app_name=settings.app_name, **context)
    return tpl.subject.format_map(ctx), tpl.body_html.format_map(ctx)


def send_templated(db: Session, to: str | list[str], template: str, context: dict, attachments=None) -> bool:
    subject, body = render_template(db, template, context)
    if not body and not subject:
        return False
    return send_email(to, subject, body, attachments)
